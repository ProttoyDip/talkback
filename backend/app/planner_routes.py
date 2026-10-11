"""Plan panel routes (plan P5): tasks, calendar blocks and reminders.

The same Planner the voice tools use, so a change made here is recorded in
the action history with the same undo. Every request reaches only the
token's user's rows.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .auth import Claims, session_claims
from .config import Settings, get_settings
from .planner import Planner
from .protocol import (
    EventCreate, EventItem, EventList, EventUpdate, Id, ReminderCreate, ReminderItem, ReminderList,
    ReminderSnooze, TaskCreate, TaskItem, TaskList, TaskUpdate,
)
from .stores import stores_for

router = APIRouter(prefix="/api", dependencies=[Depends(session_claims)])


def get_planner(settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> Planner:
    stores = stores_for(settings, claims.user_id)
    return stores.planner(stores.prefs.load().timezone, stores.ledger(claims.session_id))


Plan = Annotated[Planner, Depends(get_planner)]


def _found(fn, *args, **kwargs):
    """Run a change; a missing row is 404, a bad time is 422."""
    try:
        return fn(*args, **kwargs)
    except LookupError:
        raise HTTPException(404, "Not found") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


# Tasks


@router.get("/tasks", response_model=TaskList)
def list_tasks(plan: Plan, status: Annotated[str, Query(pattern="^(open|done|all)$")] = "open") -> TaskList:
    return TaskList(items=plan.tasks(None if status == "all" else status))


@router.post("/tasks", response_model=TaskItem, status_code=201)
def add_task(body: TaskCreate, plan: Plan) -> TaskItem:
    return _found(plan.add_task, body.title, body.due_at, body.priority, body.notes).item


@router.patch("/tasks/{identifier}", response_model=TaskItem)
def update_task(identifier: Id, body: TaskUpdate, plan: Plan) -> TaskItem:
    return _found(plan.update_task, identifier, **body.model_dump(exclude_none=True)).item


@router.delete("/tasks/{identifier}", status_code=204)
def delete_task(identifier: Id, plan: Plan) -> Response:
    _found(plan.delete_task, identifier)
    return Response(status_code=204)


# Calendar


@router.get("/calendar", response_model=EventList)
def list_events(
    plan: Plan,
    from_: Annotated[str, Query(alias="from", min_length=10, max_length=40)],
    to: Annotated[str, Query(min_length=10, max_length=40)],
) -> EventList:
    return EventList(items=_found(plan.events, from_, to))


@router.post("/calendar", response_model=EventItem, status_code=201)
def add_event(body: EventCreate, plan: Plan) -> EventItem:
    return _found(plan.add_event, body.title, body.starts_at, body.ends_at, body.kind, body.task_id).item


@router.patch("/calendar/{identifier}", response_model=EventItem)
def update_event(identifier: Id, body: EventUpdate, plan: Plan) -> EventItem:
    return _found(plan.update_event, identifier, **body.model_dump(exclude_none=True)).item


@router.delete("/calendar/{identifier}", status_code=204)
def delete_event(identifier: Id, plan: Plan) -> Response:
    _found(plan.delete_event, identifier)
    return Response(status_code=204)


# Reminders


@router.get("/reminders", response_model=ReminderList)
def list_reminders(
    plan: Plan, due_before: Annotated[str | None, Query(min_length=10, max_length=40)] = None,
) -> ReminderList:
    return ReminderList(items=_found(plan.reminders, due_before))


@router.post("/reminders", response_model=ReminderItem, status_code=201)
def set_reminder(body: ReminderCreate, plan: Plan) -> ReminderItem:
    return _found(plan.set_reminder, body.text, body.due_at).item


def _mark(plan: Planner, identifier: str, status: str, via: str | None = None) -> ReminderItem:
    item = plan.mark(identifier, status, via)
    if item is None:
        raise HTTPException(409, "This reminder was cancelled, moved or already answered")
    return item


@router.post("/reminders/{identifier}/delivered", response_model=ReminderItem)
def reminder_delivered(identifier: Id, plan: Plan) -> ReminderItem:
    """The page showed it (the server could not: no live conversation)."""
    return _mark(plan, identifier, "delivered", "page")


@router.post("/reminders/{identifier}/ack", response_model=ReminderItem)
def reminder_done(identifier: Id, plan: Plan) -> ReminderItem:
    return _mark(plan, identifier, "acknowledged")


@router.post("/reminders/{identifier}/snooze", response_model=ReminderItem)
def reminder_snooze(identifier: Id, body: ReminderSnooze, plan: Plan) -> ReminderItem:
    item = plan.snooze(identifier, body.minutes)
    if item is None:
        raise HTTPException(409, "This reminder was cancelled or already answered")
    return item


@router.delete("/reminders/{identifier}", status_code=204)
def cancel_reminder(identifier: Id, plan: Plan) -> Response:
    _found(plan.update_reminder, identifier, cancel=True)
    return Response(status_code=204)
