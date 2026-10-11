"""Prepare my day (plan P6): fit the most urgent open tasks into free time.

Pure functions, no storage: the Planner gives them the day's blocks and the
open tasks, and stores the result as a proposal the user accepts or not.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .timeutil import zone

WORK_START = time(9, 0)
WORK_END = time(18, 0)
MIN_SLOT = timedelta(minutes=15)
MAX_BLOCKS = 5
LENGTH = {"high": timedelta(minutes=90), "normal": timedelta(minutes=60), "low": timedelta(minutes=30)}
STEP = timedelta(minutes=15)


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Proposed:
    title: str
    start: datetime
    end: datetime
    task_id: str
    reason: str


def round_up(moment: datetime) -> datetime:
    """To the next quarter hour, so blocks start at :00, :15, :30, :45."""
    base = moment.replace(second=0, microsecond=0)
    if base < moment:  # 09:15:40 is past 09:15
        base += timedelta(minutes=1)
    return base + timedelta(minutes=(-base.minute) % 15)


def free_slots(busy: list[tuple[datetime, datetime]], day: date, tz: str, now: datetime) -> list[Slot]:
    """Free time in the working day, after now, between existing blocks."""
    start = datetime.combine(day, WORK_START, zone(tz))
    end = datetime.combine(day, WORK_END, zone(tz))
    start = max(start, round_up(now.astimezone(zone(tz))))
    slots: list[Slot] = []
    cursor = start
    for begin, finish in sorted(busy):
        if finish <= cursor or begin >= end:
            continue
        if begin - cursor >= MIN_SLOT:
            slots.append(Slot(cursor, min(begin, end)))
        cursor = max(cursor, finish)
    if end - cursor >= MIN_SLOT:
        slots.append(Slot(cursor, end))
    return slots


def urgency(task: dict, day_end: datetime) -> tuple:
    """Overdue and due today first, then high priority; earlier due first."""
    due = datetime.fromisoformat(task["due_at"]) if task.get("due_at") else None
    due_today = due is not None and due <= day_end
    rank = {"high": 0, "normal": 1, "low": 2}[task.get("priority", "normal")]
    return (0 if due_today else 1, rank, due or day_end + timedelta(days=365), task["created_at"])


def schedule(tasks: list[dict], slots: list[Slot], day: date, tz: str) -> list[Proposed]:
    """Greedy: the most urgent task takes the earliest slot that fits it."""
    day_end = datetime.combine(day, time(23, 59), zone(tz))
    wanted = [
        t for t in tasks
        if (t.get("due_at") and datetime.fromisoformat(t["due_at"]) <= day_end) or t.get("priority") == "high"
    ]
    free = list(slots)
    plan: list[Proposed] = []
    for task in sorted(wanted, key=lambda t: urgency(t, day_end)):
        length = LENGTH.get(task.get("priority", "normal"), LENGTH["normal"])
        for i, slot in enumerate(free):
            if slot.end - slot.start >= length:
                due = datetime.fromisoformat(task["due_at"]) if task.get("due_at") else None
                reason = (
                    "Overdue" if due and due < slot.start else
                    "Due today" if due and due <= day_end else
                    "High priority"
                )
                plan.append(Proposed(task["title"], slot.start, slot.start + length, task["id"], reason))
                rest = Slot(slot.start + length, slot.end)
                free[i:i + 1] = [rest] if rest.end - rest.start >= MIN_SLOT else []
                break
        if len(plan) >= MAX_BLOCKS:
            break
    return sorted(plan, key=lambda p: p.start)
