"""Voice tools for tasks, calendar blocks and reminders (plan P5).

Times are local ("2026-10-12T15:00") in the user's time zone. Adding or
changing one task or calendar block runs at once with an Undo chip (they are
recorded and reversible); after web results it asks first. Deleting asks
first, and so does setting or changing a reminder, which sends a
notification later (SECURITY.md T5).
"""

import asyncio
from typing import Literal

from pydantic import Field

from ..planner import Change, Planner
from ..protocol import PlanItem, PlanProposed, PlanUpdated
from ..timeutil import spoken, to_storage
from . import Arguments, Tool, ToolOutcome, ToolResult, current_action_key, current_turn_id

LocalTime = Field(min_length=10, max_length=32, description="Local time, e.g. 2026-10-12T15:00")


class TaskListArguments(Arguments):
    status: Literal["open", "done", "all"] = "open"


class TaskAddArguments(Arguments):
    title: str = Field(min_length=1, max_length=200)
    due_at: str | None = Field(default=None, min_length=10, max_length=32,
                               description="Local date or time it is due, e.g. 2026-10-12 or 2026-10-12T17:00")
    priority: Literal["low", "normal", "high"] = "normal"


class TaskUpdateArguments(Arguments):
    id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: str | None = Field(default=None, min_length=10, max_length=32)
    status: Literal["open", "done", "cancelled"] | None = None
    priority: Literal["low", "normal", "high"] | None = None


class TaskDeleteArguments(Arguments):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200, description="The task's exact title, from task_list")


class CalendarListArguments(Arguments):
    from_: str = Field(alias="from", min_length=10, max_length=32, description="Local start, e.g. 2026-10-12T00:00")
    to: str = Field(min_length=10, max_length=32, description="Local end, e.g. 2026-10-13T00:00")


class CalendarAddArguments(Arguments):
    title: str = Field(min_length=1, max_length=200)
    starts_at: str = LocalTime
    ends_at: str = LocalTime
    kind: Literal["block", "meeting", "focus", "personal"] = "block"


class CalendarUpdateArguments(Arguments):
    id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: str | None = Field(default=None, min_length=10, max_length=32)
    ends_at: str | None = Field(default=None, min_length=10, max_length=32)


class CalendarDeleteArguments(Arguments):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200, description="The block's exact title, from calendar_list")


class ReminderSetArguments(Arguments):
    text: str = Field(min_length=1, max_length=300)
    due_at: str = LocalTime


class DayPlanProposeArguments(Arguments):
    date: str | None = Field(default=None, min_length=10, max_length=10, description="Local date; today when missing")


class DayPlanApplyArguments(Arguments):
    proposal_id: str = Field(min_length=1, max_length=64)
    items: list[int] | None = Field(default=None, max_length=20, description="Which items to apply; all when missing")


class ReminderUpdateArguments(Arguments):
    id: str = Field(min_length=1, max_length=64)
    due_at: str | None = Field(default=None, min_length=10, max_length=32)
    cancel: bool = False


PLAN_KINDS = ("tasks", "calendar", "reminders", "actions")


def describe_task_update(a: "TaskUpdateArguments", when) -> str:
    """The card says exactly what changes (SECURITY.md T5)."""
    parts = []
    if a.title:
        parts.append(f"rename it to “{a.title}”")
    if a.due_at:
        parts.append(f"make it due {when(a.due_at, True)}")
    if a.status:
        parts.append({"done": "mark it done", "open": "reopen it", "cancelled": "cancel it"}[a.status])
    if a.priority:
        parts.append(f"set priority {a.priority}")
    return f"Change the task: {', '.join(parts) or 'no change'}?"[:300]


def describe_event_update(a: "CalendarUpdateArguments", when) -> str:
    parts = []
    if a.title:
        parts.append(f"rename it to “{a.title}”")
    if a.starts_at:
        parts.append(f"start {when(a.starts_at)}")
    if a.ends_at:
        parts.append(f"end {when(a.ends_at)}")
    return f"Change the calendar block: {', '.join(parts) or 'no change'}?"[:300]


def _out(change: Change, text: str) -> ToolOutcome:
    note = f" {change.note}" if change.note else ""
    item = change.item.model_dump(exclude_none=True)
    return ToolOutcome([ToolResult(text, "", f"{item}{note}")], change.action_id, change.action_id is not None)


def planner_tools(planner: Planner) -> list[Tool]:
    tz = planner.tz
    proposed: dict[str, list[PlanItem]] = {}  # plans this conversation made

    def when(text: str | None, end_of_day: bool = False) -> str:
        try:
            return spoken(to_storage(text, tz, end_of_day=end_of_day), tz) if text else ""
        except ValueError:
            return text or ""

    async def run(fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, key=current_action_key.get(), **kwargs)

    async def task_list(args: TaskListArguments) -> list[ToolResult]:
        items = await asyncio.to_thread(planner.tasks, None if args.status == "all" else args.status)
        return [ToolResult(t.title, "", t.model_dump_json(exclude_none=True)) for t in items[:30]]

    async def task_add(args: TaskAddArguments) -> ToolOutcome:
        return _out(await run(planner.add_task, args.title, args.due_at, args.priority), "Task added")

    async def task_update(args: TaskUpdateArguments) -> ToolOutcome:
        change = await run(planner.update_task, args.id, title=args.title, due_at=args.due_at,
                           status=args.status, priority=args.priority)
        return _out(change, "Task updated")

    async def task_delete(args: TaskDeleteArguments) -> ToolOutcome:
        current = await asyncio.to_thread(planner.repo("tasks").get, args.id)
        if current is None or current["title"] != args.title:
            raise ValueError("task missing or changed since confirmation")
        return _out(await run(planner.delete_task, args.id), "Task deleted")

    async def calendar_list(args: CalendarListArguments) -> list[ToolResult]:
        items = await asyncio.to_thread(planner.events, args.from_, args.to)
        return [ToolResult(e.title, "", e.model_dump_json(exclude_none=True)) for e in items[:50]]

    async def calendar_add(args: CalendarAddArguments) -> ToolOutcome:
        return _out(await run(planner.add_event, args.title, args.starts_at, args.ends_at, args.kind), "Added")

    async def calendar_update(args: CalendarUpdateArguments) -> ToolOutcome:
        change = await run(planner.update_event, args.id, title=args.title, starts_at=args.starts_at, ends_at=args.ends_at)
        return _out(change, "Moved")

    async def calendar_delete(args: CalendarDeleteArguments) -> ToolOutcome:
        current = await asyncio.to_thread(planner.repo("events").get, args.id)
        if current is None or current["title"] != args.title:
            raise ValueError("block missing or changed since confirmation")
        return _out(await run(planner.delete_event, args.id), "Removed")

    async def reminder_set(args: ReminderSetArguments) -> ToolOutcome:
        return _out(await run(planner.set_reminder, args.text, args.due_at), "Reminder set")

    async def reminder_update(args: ReminderUpdateArguments) -> ToolOutcome:
        return _out(await run(planner.update_reminder, args.id, due_at=args.due_at, cancel=args.cancel),
                    "Reminder changed")

    async def day_plan_propose(args: DayPlanProposeArguments) -> ToolOutcome:
        proposal_id, day, items, expires_at = await asyncio.to_thread(
            planner.propose_day, args.date, current_turn_id.get(),
        )
        proposed[proposal_id] = items  # for the apply card, without a store read on the event loop
        card = PlanProposed(
            proposal_id=proposal_id, message_id=current_turn_id.get() or "turn", date=day, items=items,
            expires_at=expires_at,
        )
        summary = "; ".join(f"{i.title} {i.starts_at[11:16]}–{i.ends_at[11:16]} ({i.reason})" for i in items)
        text = f"proposal_id={proposal_id}. {summary}" if items else "Nothing needs a block today: no free time or no urgent tasks."
        return ToolOutcome([ToolResult("Day plan", "", text)], None, False, (card,) if items else ())

    async def day_plan_apply(args: DayPlanApplyArguments) -> ToolOutcome:
        status, applied, action_id = await asyncio.to_thread(
            planner.apply_plan, args.proposal_id, args.items, key=current_action_key.get(),
        )
        update = PlanUpdated(proposal_id=args.proposal_id, status=status, applied=applied, action_id=action_id)
        text = f"{status}: {len(applied)} blocks added." + (" Some clashed with the calendar and were skipped." if status == "partially_applied" else "")
        return ToolOutcome([ToolResult("Day plan", "", text)], action_id, action_id is not None, (update,))

    def plan_lines(args: DayPlanApplyArguments) -> list[str]:
        items = proposed.get(args.proposal_id, [])
        return [
            f"{i.starts_at[11:16]}–{i.ends_at[11:16]} {i.title}" for i in items
            if args.items is None or i.index in args.items
        ]

    reversible = dict(sensitive=False, mutates=True, confirm_when_tainted=True, data_kinds=PLAN_KINDS)
    asks = dict(mutates=True, data_kinds=PLAN_KINDS)
    return [
        Tool("task_list", "List the user's tasks (open by default).", TaskListArguments, task_list, sensitive=False),
        Tool("task_add", "Add a task, optionally with a local due date or time.", TaskAddArguments, task_add,
             confirmation_summary=lambda a: f"Add the task “{a.title}”{' for ' + when(a.due_at, True) if a.due_at else ''}?",
             **reversible),
        Tool("task_update", "Change, complete (status done) or reschedule a task by id.", TaskUpdateArguments,
             task_update, confirmation_summary=lambda a: describe_task_update(a, when), **reversible),
        Tool("task_delete", "Delete a task by id and exact title.", TaskDeleteArguments, task_delete,
             confirmation_summary=lambda a: f"Delete the task “{a.title}”?", **asks),
        Tool("calendar_list", "List calendar blocks between two local times.", CalendarListArguments, calendar_list,
             sensitive=False),
        Tool("calendar_add", "Add a calendar block (local start and end). Reports overlaps.", CalendarAddArguments,
             calendar_add,
             confirmation_summary=lambda a: f"Add “{a.title}” {when(a.starts_at)}?", **reversible),
        Tool("calendar_update", "Move or rename a calendar block by id. Reports overlaps.", CalendarUpdateArguments,
             calendar_update, confirmation_summary=lambda a: describe_event_update(a, when), **reversible),
        Tool("calendar_delete", "Remove a calendar block by id and exact title.", CalendarDeleteArguments,
             calendar_delete, confirmation_summary=lambda a: f"Remove “{a.title}” from your calendar?", **asks),
        Tool("reminder_set", "Set a reminder that notifies the user at a local time.", ReminderSetArguments,
             reminder_set, confirmation_summary=lambda a: f"Remind you {when(a.due_at)}: “{a.text}”?", **asks),
        Tool("reminder_update", "Move or cancel a reminder by id.", ReminderUpdateArguments, reminder_update,
             confirmation_summary=lambda a: "Cancel this reminder?" if a.cancel else f"Move the reminder to {when(a.due_at)}?",
             **asks),
        Tool("day_plan_propose", "Propose blocks for the most urgent open tasks in today's free time. "
             "Shows the user a plan card; nothing changes until they accept.",
             DayPlanProposeArguments, day_plan_propose, sensitive=False),
        Tool("day_plan_apply", "Apply a proposed day plan (all items, or the ones the user chose).",
             DayPlanApplyArguments, day_plan_apply,
             confirmation_summary=lambda a: "Add these blocks to your calendar?", confirmation_details=plan_lines, **asks),
    ]
