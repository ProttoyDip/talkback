"""Times for tasks, calendar and reminders, in the user's time zone (plan P5).

The model and the browser speak local time ("2026-10-12T15:00"); storage is
UTC ISO 8601, so it sorts the same everywhere. A time without an offset is
read in the user's IANA time zone (Settings, set from the browser).
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """Storage form: UTC, seconds, with offset."""
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def parse(text: str, tz: str, *, end_of_day: bool = False) -> datetime:
    """A local time (or one with an offset) as an aware datetime.

    "2026-10-12" alone means that day: 23:59 for a due date (end_of_day),
    09:00 otherwise. Raises ValueError on anything else.
    """
    text = text.strip().replace(" ", "T", 1) if "T" not in text else text.strip()
    if len(text) == 10:
        day = date.fromisoformat(text)
        return datetime.combine(day, time(23, 59) if end_of_day else time(9, 0), zone(tz))
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=zone(tz))


def to_storage(text: str | None, tz: str, *, end_of_day: bool = False) -> str | None:
    return iso(parse(text, tz, end_of_day=end_of_day)) if text else None


def local(stored: str | None, tz: str) -> str | None:
    """What the model and the user see: local time with its offset."""
    if not stored:
        return None
    return datetime.fromisoformat(stored).astimezone(zone(tz)).isoformat(timespec="minutes")


def spoken(stored: str, tz: str) -> str:
    """"today at 3:00 PM", "tomorrow at 9:30 AM", "Mon 14 Oct at 9:00 AM"."""
    moment = datetime.fromisoformat(stored).astimezone(zone(tz))
    today = now_utc().astimezone(zone(tz)).date()
    clock = moment.strftime("%I:%M %p").lstrip("0")
    if moment.date() == today:
        return f"today at {clock}"
    if moment.date() == today + timedelta(days=1):
        return f"tomorrow at {clock}"
    return f"{moment.strftime('%a %d %b')} at {clock}"


def now_line(tz: str) -> str:
    """For the system prompt, so "tomorrow at 3" means the right day."""
    moment = now_utc().astimezone(zone(tz))
    return f"Now: {moment.strftime('%a %Y-%m-%d %H:%M')} in the user's time zone {zone(tz).key}."


def day_bounds(day: date, tz: str) -> tuple[str, str]:
    start = datetime.combine(day, time(0, 0), zone(tz))
    return iso(start), iso(start + timedelta(days=1))
