"""Reminder delivery (plan P5).

Every `reminder_poll_seconds` the server looks for reminders that are due.
If the user has a conversation open, the reminder is claimed (a conditional
update, so it is delivered once even with two workers), sent as
reminder.due and spoken. If not, it stays scheduled and the page delivers
it: the open page polls GET /api/reminders and shows a notification.

On Render's free plan the server sleeps after 15 idle minutes, so a reminder
due while it sleeps is delivered by the page, or shown as missed on the
next visit (README: limits of the free plan).
"""

import asyncio
import logging

from .config import Settings
from .db.repo import Conflict, In, IsNull, Lte
from .planner import Planner
from .protocol import ReminderDue
from .session import registry
from .stores import stores_for, system_repo
from .timeutil import iso, now_utc

log = logging.getLogger("talkback.scheduler")


async def deliver_due(settings: Settings) -> int:
    """Deliver due reminders to open conversations. Returns how many."""
    live_users = tuple({s.user_id for s in list(registry.live.values())})
    if not live_users:
        return 0  # nobody to tell: the pages deliver
    reminders = system_repo(settings, "reminders")  # every user's: server job only
    # Only users with a conversation open, so reminders of people who are
    # away never crowd out the ones that can be delivered now.
    due = await asyncio.to_thread(
        reminders.select,
        {"status": "scheduled", "deleted_at": IsNull(), "due_at": Lte(iso(now_utc())), "user_id": In(live_users)},
        "due_at.asc", 50,
    )
    delivered = 0
    for row in due:
        sessions = [s for s in list(registry.live.values()) if s.user_id == row["user_id"]]
        if not sessions:
            continue  # the page delivers it
        try:
            claimed = await asyncio.to_thread(
                reminders.update, row["id"],
                {"status": "delivered", "delivered_at": iso(now_utc()), "delivered_via": "session"},
                row["updated_at"],
            )
        except Conflict:
            continue  # another worker (or the page) took it
        timezone = (await asyncio.to_thread(stores_for(settings, row["user_id"]).prefs.load)).timezone
        item = Planner(None, timezone).reminder(claimed)
        for session in sessions:
            try:
                await session.send(ReminderDue(reminder=item))
                announce = getattr(session.engine, "announce", None)
                if announce is not None:
                    await announce(f"Reminder: {item.text}")
            except Exception:
                log.warning("reminder not sent to a session", extra={"session_id": session.session_id})
        delivered += 1
    return delivered


async def run(settings_source) -> None:
    """The background loop, started with the app (main.py lifespan)."""
    while True:
        settings = settings_source()
        await asyncio.sleep(settings.reminder_poll_seconds)
        try:
            count = await deliver_due(settings)
            if count:
                log.info("reminders delivered", extra={"event": str(count)})
        except Exception:
            log.exception("reminder check failed")
