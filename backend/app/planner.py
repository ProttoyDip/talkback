"""Tasks, calendar blocks and reminders for one user (plan P5).

Used by the voice tools and the Plan panel routes alike, so both record the
same actions with the same undo. Times come in as local ISO strings (or with
an offset) and are stored in UTC; items go out in the user's local time.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .actions import ActionLedger
from .db.repo import Gte, In, IsNull, Lte, Repo
from .protocol import EventItem, PlanItem, ReminderItem, TaskItem

PLAN_LIFETIME = timedelta(minutes=30)  # an unanswered plan expires
from .planning import free_slots, schedule
from .timeutil import day_bounds, iso, local, now_utc, parse, spoken, to_storage, zone

MAX_ITEMS = 500  # per list; plenty for one person


@dataclass
class Change:
    """What a change did: the item, and the action recorded for undo."""

    item: TaskItem | EventItem | ReminderItem
    action_id: str | None
    note: str = ""  # e.g. overlaps, for the model


class Planner:
    def __init__(self, tables, timezone: str, ledger: ActionLedger | None = None) -> None:
        self.tables = tables  # table name -> this user's Repo
        self.tz = timezone
        self.ledger = ledger

    def repo(self, name: str) -> Repo:
        return self.tables(name)

    # Shapes for the API and the model (local times)

    def task(self, row: dict) -> TaskItem:
        return TaskItem(
            id=row["id"], title=row["title"], notes=row.get("notes"), status=row["status"],
            due_at=local(row.get("due_at"), self.tz), priority=row["priority"],
            created_at=row["created_at"], updated_at=row.get("updated_at"), completed_at=row.get("completed_at"),
        )

    def event(self, row: dict) -> EventItem:
        return EventItem(
            id=row["id"], title=row["title"], starts_at=local(row["starts_at"], self.tz),
            ends_at=local(row["ends_at"], self.tz), kind=row["kind"], status=row["status"],
            task_id=row.get("task_id"), created_at=row["created_at"], updated_at=row.get("updated_at"),
        )

    def reminder(self, row: dict) -> ReminderItem:
        return ReminderItem(
            id=row["id"], text=row["text"], due_at=local(row["due_at"], self.tz), status=row["status"],
            delivered_at=row.get("delivered_at"), snooze_count=row.get("snooze_count") or 0,
            created_at=row["created_at"],
        )

    # Recording

    def _record(self, tool: str, summary: str, table: str, row: dict, undo: dict, key: str | None) -> str | None:
        if self.ledger is None:
            return None
        action = self.ledger.record(
            tool, "done", summary, target_kind=table, target_id=row["id"], undo=undo, key=key,
        )
        return action["id"]

    def _add(self, table: str, tool: str, values: dict, summary: str, key: str | None) -> tuple[dict, str | None]:
        row = self.repo(table).insert(values)
        # Undo checks the fields it would change, so undo works newest-first as a stack.
        name = "text" if "text" in row else "title"  # renamed since? then undo would lose that
        undo = {"op": "row.unadd", "table": table, "id": row["id"], "after": {"deleted_at": None, name: row[name]}}
        return row, self._record(tool, summary, table, row, undo, key)

    def _change(
        self, table: str, tool: str, identifier: str, changes: dict, summary: str, key: str | None,
    ) -> tuple[dict, str | None]:
        repo = self.repo(table)
        before = repo.get(identifier)
        if before is None or before.get("deleted_at"):
            raise LookupError(identifier)
        row = repo.update(identifier, changes)
        undo = {
            "op": "row.restore", "table": table, "id": identifier,
            "after": {k: row.get(k) for k in changes}, "before": {k: before.get(k) for k in changes},
        }
        name = before.get("title") or before.get("text") or ""
        return row, self._record(tool, summary.replace("{title}", name), table, row, undo, key)

    # Tasks

    def tasks(self, status: str | None = "open") -> list[TaskItem]:
        where = {"deleted_at": IsNull()}
        if status:
            where["status"] = status
        rows = self.repo("tasks").select(where, order="due_at.asc,created_at.asc", limit=MAX_ITEMS)
        return [self.task(row) for row in rows]

    def add_task(self, title: str, due_at: str | None = None, priority: str = "normal",
                 notes: str | None = None, key: str | None = None) -> Change:
        due = to_storage(due_at, self.tz, end_of_day=True)
        when = f" for {spoken(due, self.tz)}" if due else ""
        row, action = self._add("tasks", "task_add", {
            "title": title, "notes": notes, "status": "open", "due_at": due, "priority": priority,
        }, f"Added the task “{title}”{when}", key)
        return Change(self.task(row), action)

    def update_task(self, identifier: str, *, title: str | None = None, due_at: str | None = None,
                    status: str | None = None, priority: str | None = None, notes: str | None = None,
                    key: str | None = None) -> Change:
        changes: dict = {}
        if title is not None:
            changes["title"] = title
        if notes is not None:
            changes["notes"] = notes
        if priority is not None:
            changes["priority"] = priority
        if due_at is not None:
            changes["due_at"] = to_storage(due_at, self.tz, end_of_day=True)
        if status is not None:
            changes["status"] = status
            changes["completed_at"] = iso(now_utc()) if status == "done" else None
        verb = "Completed" if status == "done" else "Moved" if due_at else "Changed"
        row, action = self._change("tasks", "task_update", identifier, changes, verb + " the task “{title}”", key)
        return Change(self.task(row), action)

    def delete_task(self, identifier: str, key: str | None = None) -> Change:
        row, action = self._change("tasks", "task_delete", identifier, {"deleted_at": iso(now_utc())},
                                   "Deleted the task “{title}”", key)
        return Change(self.task(row), action)

    # Calendar

    def events(self, start: str, end: str) -> list[EventItem]:
        start_utc, end_utc = to_storage(start, self.tz), to_storage(end, self.tz)
        rows = self.repo("events").select(
            {"deleted_at": IsNull(), "status": "confirmed", "starts_at": Lte(end_utc), "ends_at": Gte(start_utc)},
            order="starts_at.asc", limit=MAX_ITEMS,
        )
        # The filters are inclusive; drop blocks that only touch the edges.
        return [self.event(r) for r in rows if r["starts_at"] < end_utc and r["ends_at"] > start_utc]

    def overlaps(self, starts_utc: str, ends_utc: str, skip: str | None = None) -> list[EventItem]:
        rows = self.repo("events").select(
            {"deleted_at": IsNull(), "status": "confirmed", "starts_at": Lte(ends_utc), "ends_at": Gte(starts_utc)},
            limit=50,
        )
        return [self.event(r) for r in rows if r["id"] != skip and r["starts_at"] < ends_utc and r["ends_at"] > starts_utc]

    def _span(self, starts_at: str, ends_at: str) -> tuple[str, str]:
        start, end = parse(starts_at, self.tz), parse(ends_at, self.tz)
        if end <= start:
            raise ValueError("a block must end after it starts")
        if end - start > timedelta(days=1):
            raise ValueError("a block can be at most a day long")
        return iso(start), iso(end)

    def add_event(self, title: str, starts_at: str, ends_at: str, kind: str = "block",
                  task_id: str | None = None, key: str | None = None) -> Change:
        start, end = self._span(starts_at, ends_at)
        row, action = self._add("events", "calendar_add", {
            "title": title, "starts_at": start, "ends_at": end, "kind": kind, "status": "confirmed", "task_id": task_id,
        }, f"Added “{title}” {spoken(start, self.tz)}", key)
        clash = self.overlaps(start, end, skip=row["id"])
        note = ("Overlaps: " + "; ".join(f"{e.title} {e.starts_at}–{e.ends_at}" for e in clash)) if clash else ""
        return Change(self.event(row), action, note)

    def update_event(self, identifier: str, *, title: str | None = None, starts_at: str | None = None,
                     ends_at: str | None = None, kind: str | None = None, key: str | None = None) -> Change:
        current = self.repo("events").get(identifier)
        if current is None or current.get("deleted_at"):
            raise LookupError(identifier)
        changes: dict = {}
        if title is not None:
            changes["title"] = title
        if kind is not None:
            changes["kind"] = kind
        if starts_at is not None or ends_at is not None:
            start = starts_at or local(current["starts_at"], self.tz)
            end = ends_at or local(current["ends_at"], self.tz)
            if starts_at is not None and ends_at is None:  # moving keeps the length
                length = parse(current["ends_at"], "UTC") - parse(current["starts_at"], "UTC")
                end = (parse(starts_at, self.tz) + length).isoformat()
            changes["starts_at"], changes["ends_at"] = self._span(start, end)
        row, action = self._change("events", "calendar_update", identifier, changes, "Moved “{title}”", key)
        clash = self.overlaps(row["starts_at"], row["ends_at"], skip=identifier)
        note = ("Overlaps: " + "; ".join(f"{e.title} {e.starts_at}–{e.ends_at}" for e in clash)) if clash else ""
        return Change(self.event(row), action, note)

    def delete_event(self, identifier: str, key: str | None = None) -> Change:
        row, action = self._change("events", "calendar_delete", identifier, {"deleted_at": iso(now_utc())},
                                   "Removed “{title}” from the calendar", key)
        return Change(self.event(row), action)

    # Reminders

    def reminders(self, due_before: str | None = None, status: str = "scheduled") -> list[ReminderItem]:
        where: dict = {"deleted_at": IsNull(), "status": In((status,))}
        if due_before:
            where["due_at"] = Lte(to_storage(due_before, self.tz))
        rows = self.repo("reminders").select(where, order="due_at.asc", limit=MAX_ITEMS)
        return [self.reminder(row) for row in rows]

    def set_reminder(self, text: str, due_at: str, key: str | None = None) -> Change:
        due = to_storage(due_at, self.tz)
        if due < iso(now_utc() - timedelta(minutes=1)):
            raise ValueError("that time has passed")
        row, action = self._add("reminders", "reminder_set", {
            "text": text, "due_at": due, "status": "scheduled", "snooze_count": 0,
        }, f"Set a reminder {spoken(due, self.tz)}: “{text}”", key)
        return Change(self.reminder(row), action)

    def update_reminder(self, identifier: str, *, text: str | None = None, due_at: str | None = None,
                        cancel: bool = False, key: str | None = None) -> Change:
        changes: dict = {}
        if text is not None:
            changes["text"] = text
        if due_at is not None:
            changes["due_at"] = to_storage(due_at, self.tz)
            if changes["due_at"] < iso(now_utc() - timedelta(minutes=1)):
                raise ValueError("that time has passed")
            changes["status"] = "scheduled"
        if cancel:
            changes["status"] = "cancelled"
        verb = "Cancelled" if cancel else "Moved" if due_at else "Changed"
        row, action = self._change("reminders", "reminder_update", identifier, changes,
                                   verb + " the reminder “{title}”", key)
        return Change(self.reminder(row), action)

    def mark(self, identifier: str, status: str, via: str | None = None) -> ReminderItem | None:
        """Delivered, acknowledged: bookkeeping, not an undoable action.

        Checks the reminder as it is now: a page timer set before the user
        cancelled or moved it must not bring it back (None: nothing to do).
        """
        current = self.repo("reminders").get(identifier)
        if current is None or current.get("deleted_at") or current["status"] in ("cancelled", "acknowledged"):
            return None
        if status == "delivered" and (
            current["status"] != "scheduled" or current["due_at"] > iso(now_utc() + timedelta(minutes=1))
        ):
            return None  # moved later, or already shown
        changes: dict = {"status": status}
        if status == "delivered":
            changes |= {"delivered_at": iso(now_utc()), "delivered_via": via}
        if status == "acknowledged":
            changes["ack_at"] = iso(now_utc())
        row = self.repo("reminders").update(identifier, changes)
        return self.reminder(row) if row else None

    def snooze(self, identifier: str, minutes: int) -> ReminderItem | None:
        current = self.repo("reminders").get(identifier)
        if current is None or current.get("deleted_at") or current["status"] in ("cancelled", "acknowledged"):
            return None
        row = self.repo("reminders").update(identifier, {
            "status": "scheduled", "due_at": iso(now_utc() + timedelta(minutes=minutes)),
            "snooze_count": (current.get("snooze_count") or 0) + 1,
        })
        return self.reminder(row)

    # Prepare my day (plan P6)

    def propose_day(self, day: str | None = None, message_id: str | None = None) -> tuple[str, str, list[PlanItem]]:
        """A plan for the day: (proposal id, local date, items). Nothing changes yet."""
        today = now_utc().astimezone(zone(self.tz)).date()
        when = date.fromisoformat(day) if day else today
        start, end = day_bounds(when, self.tz)
        busy = [
            (datetime.fromisoformat(r["starts_at"]), datetime.fromisoformat(r["ends_at"]))
            for r in self.repo("events").select(
                {"deleted_at": IsNull(), "status": "confirmed", "starts_at": Lte(end), "ends_at": Gte(start)}, limit=200,
            )
        ]
        planned = {
            r["task_id"] for r in self.repo("events").select(
                {"deleted_at": IsNull(), "starts_at": Lte(end), "ends_at": Gte(start)}, limit=200,
            ) if r.get("task_id")
        }
        tasks = [
            t for t in self.repo("tasks").select({"deleted_at": IsNull(), "status": "open"}, limit=MAX_ITEMS)
            if t["id"] not in planned
        ]
        slots = free_slots(busy, when, self.tz, now_utc() if when == today else datetime.combine(when, datetime.min.time(), zone(self.tz)))
        plan = schedule(tasks, slots, when, self.tz)
        items = [
            PlanItem(index=i, title=p.title, starts_at=local(iso(p.start), self.tz), ends_at=local(iso(p.end), self.tz),
                     task_id=p.task_id, reason=p.reason)
            for i, p in enumerate(plan)
        ]
        proposals = self.repo("proposals")
        for older in proposals.select({"date": when.isoformat(), "status": "pending"}, limit=20):
            proposals.update(older["id"], {"status": "superseded"})  # only the newest plan can be applied
        row = proposals.insert({
            "date": when.isoformat(), "status": "pending", "message_id": message_id,
            "items": [item.model_dump() for item in items], "expires_at": iso(now_utc() + PLAN_LIFETIME),
        })
        return row["id"], when.isoformat(), items

    def plan_items(self, proposal_id: str) -> list[PlanItem]:
        row = self.repo("proposals").get(proposal_id)
        return [PlanItem(**item) for item in row["items"]] if row else []

    def apply_plan(self, proposal_id: str, indices: list[int] | None = None,
                   key: str | None = None) -> tuple[str, list[int], str | None]:
        """Create the chosen blocks as one action; undo removes them all.

        Returns (status, applied indices, action id). A plan that was
        replaced, declined or expired is refused (ValueError); a block that
        now clashes with the calendar is skipped (partially_applied).
        """
        proposals = self.repo("proposals")
        row = proposals.get(proposal_id)
        if row is None:
            raise LookupError(proposal_id)
        if row["status"] != "pending":
            raise ValueError(f"that plan was {row['status']}")
        if row["expires_at"] < iso(now_utc()):
            proposals.update(proposal_id, {"status": "expired"})
            raise ValueError("that plan expired; ask for a new one")
        items = [PlanItem(**item) for item in row["items"]]
        chosen = [i for i in items if indices is None or i.index in indices]
        created, applied = [], []
        for item in chosen:
            start, end = to_storage(item.starts_at, self.tz), to_storage(item.ends_at, self.tz)
            if self.overlaps(start, end):
                continue  # the calendar changed since the plan was made
            event = self.repo("events").insert({
                "title": item.title, "starts_at": start, "ends_at": end, "kind": "focus",
                "status": "confirmed", "task_id": item.task_id,
            })
            created.append({"id": event["id"], "title": event["title"]})
            applied.append(item.index)
        status = "accepted" if len(applied) == len(items) else "partially_applied"
        proposals.update(proposal_id, {"status": status})
        action_id = None
        if created and self.ledger is not None:
            action = self.ledger.record(
                "day_plan_apply", "done", f"Planned your day: {len(created)} block{'s' if len(created) != 1 else ''}",
                target_kind="events", undo={"op": "rows.unadd", "table": "events", "rows": created}, key=key,
            )
            action_id = action["id"]
        return status, applied, action_id

    def reject_plan(self, proposal_id: str) -> bool:
        row = self.repo("proposals").get(proposal_id)
        if row is None or row["status"] != "pending":
            return False
        self.repo("proposals").update(proposal_id, {"status": "rejected"})
        return True
