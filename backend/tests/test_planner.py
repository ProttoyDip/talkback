"""Plan P5: tasks, calendar, reminders, the reminder scheduler, your own skills."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.actions import UndoConflict
from app.protocol import ReminderDue, ToolConfirmRequest, ToolStatus
from app.scheduler import deliver_due
from app.session import registry
from app.stores import stores_for
from app.timeutil import iso, now_utc, zone
from app.tokens import issue_token
from app.tool_bridge import ToolBridge
from app.tools.planner import planner_tools

TZ = "Asia/Dhaka"  # UTC+6, no daylight saving


@pytest.fixture
def stores(settings):
    return stores_for(settings, "u1")


@pytest.fixture
def planner(stores):
    return stores.planner(TZ)


def local_in(hours: float) -> str:
    return (now_utc() + timedelta(hours=hours)).astimezone(zone(TZ)).strftime("%Y-%m-%dT%H:%M")


# Tasks


def test_a_task_due_date_is_stored_in_utc_and_shown_in_local_time(planner, stores):
    change = planner.add_task("Pay rent", "2026-10-12T17:00")
    assert change.item.due_at == "2026-10-12T17:00+06:00"
    assert stores.repo("tasks").get(change.item.id)["due_at"] == "2026-10-12T11:00:00+00:00"
    assert planner.add_task("File taxes", "2026-10-13").item.due_at == "2026-10-13T23:59+06:00"  # end of that day


def test_complete_move_delete_and_undo(planner, stores):
    ledger = planner.ledger
    task = planner.add_task("Call mom", "2026-10-12T18:00")
    planner.update_task(task.item.id, status="done")
    assert [t.title for t in planner.tasks("done")] == ["Call mom"]
    moved = planner.update_task(task.item.id, due_at="2026-10-13T09:00")
    deleted = planner.delete_task(task.item.id)
    assert planner.tasks(None) == []

    ledger.undo(deleted.action_id)  # back, as it was
    assert planner.tasks(None)[0].due_at == "2026-10-13T09:00+06:00"
    ledger.undo(moved.action_id)
    assert planner.tasks(None)[0].due_at == "2026-10-12T18:00+06:00"
    ledger.undo(task.action_id)  # undo the add
    assert planner.tasks(None) == []


def test_undo_refuses_when_the_task_changed_since(planner):
    task = planner.add_task("Gym")
    planner.update_task(task.item.id, title="Gym at 7")
    with pytest.raises(UndoConflict):
        planner.ledger.undo(task.action_id)


# Calendar


def test_a_block_reports_overlaps_and_moving_keeps_its_length(planner):
    first = planner.add_event("Standup", "2026-10-12T09:00", "2026-10-12T09:30")
    second = planner.add_event("Focus", "2026-10-12T09:15", "2026-10-12T11:15", "focus")
    assert "Standup" in second.note and first.note == ""
    moved = planner.update_event(second.item.id, starts_at="2026-10-12T13:00")
    assert (moved.item.starts_at, moved.item.ends_at) == ("2026-10-12T13:00+06:00", "2026-10-12T15:00+06:00")
    day = planner.events("2026-10-12T00:00", "2026-10-13T00:00")
    assert [e.title for e in day] == ["Standup", "Focus"]


def test_a_block_must_end_after_it_starts(planner):
    with pytest.raises(ValueError):
        planner.add_event("Oops", "2026-10-12T10:00", "2026-10-12T09:00")


# Reminders


def test_a_reminder_in_the_past_is_refused_and_snooze_moves_it(planner):
    with pytest.raises(ValueError):
        planner.set_reminder("Too late", local_in(-1))
    reminder = planner.set_reminder("Stretch", local_in(1)).item
    snoozed = planner.snooze(reminder.id, 10)
    assert snoozed.snooze_count == 1 and snoozed.status == "scheduled"


# Tools: what runs at once, what asks first


def bridge_for(planner, emit=None, **kwargs):
    emit = emit or AsyncMock()
    bridge = ToolBridge("s", planner_tools(planner), emit, AsyncMock(), **kwargs)
    bridge.ledger, bridge.user_id = planner.ledger, "u1"
    return bridge, emit


def finals(emit):
    return [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], ToolStatus) and c.args[0].status != "running"]


def test_adding_a_task_runs_at_once_with_undo(planner):
    bridge, emit = bridge_for(planner)
    asyncio.run(bridge.execute('[{"name":"task_add","arguments":{"title":"Buy milk"}}]', "turn"))
    [done] = finals(emit)
    assert done.status == "done" and done.undoable and done.action_id
    assert not [c for c in emit.await_args_list if isinstance(c.args[0], ToolConfirmRequest)]


def test_after_web_results_adding_a_task_asks_first(planner):
    bridge, emit = bridge_for(planner, confirmation_timeout=0.05)
    bridge.tainted.add("turn")
    asyncio.run(bridge.execute('[{"name":"task_add","arguments":{"title":"Buy milk"}}]', "turn"))  # no answer
    asks = [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], ToolConfirmRequest)]
    assert asks and asks[0].summary == "Add the task “Buy milk”?"


def test_a_reminder_asks_first_and_says_when(planner):
    asked = []

    async def answer(message):
        if isinstance(message, ToolConfirmRequest):
            asked.append(message.summary)
            bridge.resolve(message.call_id, True)

    bridge, emit = bridge_for(planner, AsyncMock(side_effect=answer))
    due = local_in(2)
    asyncio.run(bridge.execute(json.dumps([{"name": "reminder_set", "arguments": {"text": "Call mom", "due_at": due}}]), "t"))
    assert asked and asked[0].startswith("Remind you ") and "Call mom" in asked[0]
    assert [r.text for r in planner.reminders()] == ["Call mom"]


def test_deleting_needs_the_exact_title(planner):
    task = planner.add_task("Water plants").item

    async def approve(message):
        if isinstance(message, ToolConfirmRequest):
            bridge.resolve(message.call_id, True)

    bridge, emit = bridge_for(planner, AsyncMock(side_effect=approve))
    wrong = json.dumps([{"name": "task_delete", "arguments": {"id": task.id, "title": "Something else"}}])
    asyncio.run(bridge.execute(wrong, "t1"))
    assert planner.tasks()[0].title == "Water plants"


def test_planning_tools_are_offered_only_when_talking_about_plans():
    from app.cascade_engine import PLAN_WORDS

    assert PLAN_WORDS.search("Remind me to call mom at 5pm")
    assert PLAN_WORDS.search("What's on my calendar tomorrow?")
    assert not PLAN_WORDS.search("What does full-duplex mean?")


# REST routes


def bearer(settings, user="u1"):
    token, _ = issue_token(settings.signing_key(), user_id=user)
    return {"Authorization": f"Bearer {token}"}


def test_routes_keep_each_users_plan_apart(client, settings):
    alice, bob = bearer(settings), bearer(settings, "u2")
    task = client.post("/api/tasks", headers=alice, json={"title": "Alice's task", "due_at": "2026-10-12"}).json()
    assert client.get("/api/tasks", headers=bob).json()["items"] == []
    assert client.patch(f"/api/tasks/{task['id']}", headers=bob, json={"status": "done"}).status_code == 404
    done = client.patch(f"/api/tasks/{task['id']}", headers=alice, json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"]
    event = client.post("/api/calendar", headers=alice, json={
        "title": "Focus", "starts_at": "2026-10-12T09:00", "ends_at": "2026-10-12T10:00", "kind": "focus"})
    assert event.status_code == 201
    day = client.get("/api/calendar", headers=alice, params={"from": "2026-10-12T00:00", "to": "2026-10-13T00:00"})
    assert [e["title"] for e in day.json()["items"]] == ["Focus"]
    assert client.post("/api/calendar", headers=alice, json={
        "title": "Bad", "starts_at": "2026-10-12T10:00", "ends_at": "2026-10-12T09:00"}).status_code == 422
    # The action history records these, with undo.
    summaries = [a["summary"] for a in client.get("/api/actions", headers=alice).json()["items"]]
    assert any(s.startswith("Added the task “Alice's task”") for s in summaries)


def test_the_time_zone_is_checked(client, settings):
    headers = bearer(settings)
    assert client.patch("/api/settings", headers=headers, json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.patch("/api/settings", headers=headers, json={"timezone": TZ}).json()["timezone"] == TZ


# The scheduler


class LiveSession:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.session_id = "live"
        self.sent: list = []
        self.engine = None

    async def send(self, message) -> None:
        self.sent.append(message)


def test_a_due_reminder_reaches_the_open_conversation_once(settings, stores):
    reminders = stores.repo("reminders")
    reminders.insert({"text": "Stretch", "due_at": iso(now_utc() - timedelta(minutes=1)), "status": "scheduled",
                      "snooze_count": 0})
    live = LiveSession("u1")
    registry.live["live"] = live
    try:
        async def twice():
            return await asyncio.gather(deliver_due(settings), deliver_due(settings))

        counts = asyncio.run(twice())
    finally:
        registry.live.pop("live", None)
    assert sum(counts) == 1
    [due] = live.sent
    assert isinstance(due, ReminderDue) and due.reminder.text == "Stretch"
    assert reminders.select()[0]["status"] == "delivered"


def test_without_an_open_conversation_the_page_delivers_it(settings, stores):
    reminders = stores.repo("reminders")
    reminders.insert({"text": "Stretch", "due_at": iso(now_utc() - timedelta(minutes=1)), "status": "scheduled",
                      "snooze_count": 0})
    assert asyncio.run(deliver_due(settings)) == 0
    assert reminders.select()[0]["status"] == "scheduled"


# Your own skills


def test_your_own_skill_is_checked_saved_and_listed(client, settings):
    headers = bearer(settings)
    body = {"name": "Evening wrap", "triggers": ["wrap up my day"], "allowed_tools": ["task_list"],
            "instructions": "List my open tasks briefly."}
    made = client.post("/api/skills", headers=headers, json=body).json()
    assert made["builtin"] is False and made["instructions"] == "List my open tasks briefly."
    listed = {s["id"]: s for s in client.get("/api/skills", headers=headers).json()["items"]}
    assert made["id"] in listed and listed["morning-brief"]["builtin"] is True
    assert client.get("/api/skills", headers=bearer(settings, "u2")).json()["items"][-1]["builtin"] is True

    for bad, reason in [
        ({**body, "triggers": ["okay"]}, "can't start a skill"),
        ({**body, "triggers": ["morning brief"]}, "already starts another skill"),
        ({**body, "triggers": ["run the shell"], "allowed_tools": ["skill_run"]}, "can't use"),
    ]:
        response = client.post("/api/skills", headers=headers, json=bad)
        assert response.status_code == 422 and reason in response.json()["detail"]

    assert client.patch("/api/skills/morning-brief", headers=headers, json={"name": "Mine"}).status_code == 409
    off = client.patch(f"/api/skills/{made['id']}", headers=headers, json={"enabled": False}).json()
    assert off["enabled"] is False
    assert client.delete(f"/api/skills/{made['id']}", headers=headers).status_code == 204
