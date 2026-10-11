"""Plan P6: "Prepare my day" proposes, the user accepts all or some, undo reverts it all."""

import asyncio
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.planning import Slot, free_slots, schedule
from app.protocol import PlanProposed, PlanUpdated, ToolConfirmRequest
from app.stores import stores_for
from app.timeutil import iso, now_utc, zone
from app.tokens import issue_token
from app.tool_bridge import ToolBridge
from app.tools.planner import planner_tools

TZ = "Asia/Dhaka"
DAY = date(2030, 1, 7)  # a future Monday: the whole working day is free time
EARLY = datetime(2030, 1, 7, 0, 0, tzinfo=zone(TZ))


def at(hour, minute=0):
    return datetime(2030, 1, 7, hour, minute, tzinfo=zone(TZ))


# The pure planner


def test_free_time_is_the_working_day_between_blocks():
    slots = free_slots([(at(10), at(11)), (at(13), at(14, 30))], DAY, TZ, EARLY)
    assert [(s.start.hour, s.end.hour) for s in slots] == [(9, 10), (11, 13), (14, 18)]


def test_free_time_starts_from_now_on_the_quarter_hour():
    [slot] = free_slots([], DAY, TZ, at(11, 7))
    assert slot.start == at(11, 15)


def test_the_most_urgent_task_gets_the_earliest_slot():
    tasks = [
        {"id": "a", "title": "Read", "priority": "low", "due_at": None, "created_at": "1"},
        {"id": "b", "title": "Slides", "priority": "high", "due_at": None, "created_at": "2"},
        {"id": "c", "title": "Invoice", "priority": "normal", "due_at": at(17).isoformat(), "created_at": "3"},
    ]
    plan = schedule(tasks, [Slot(at(9), at(12))], DAY, TZ)
    assert [(p.title, p.start.hour, p.reason) for p in plan] == [("Invoice", 9, "Due today"), ("Slides", 10, "High priority")]


# Propose, accept, undo


@pytest.fixture
def planner(settings):
    return stores_for(settings, "u1").planner(TZ)


def urgent_tasks(planner):
    planner.add_task("Invoice", "2030-01-07T17:00")
    planner.add_task("Slides", priority="high")
    planner.add_event("Standup", "2030-01-07T09:00", "2030-01-07T10:00")


def test_a_plan_changes_nothing_until_accepted_and_undo_removes_it_all(planner):
    urgent_tasks(planner)
    proposal, day, items, _ = planner.propose_day("2030-01-07")
    assert day == "2030-01-07" and [i.title for i in items] == ["Invoice", "Slides"]
    assert [e.title for e in planner.events("2030-01-07T00:00", "2030-01-08T00:00")] == ["Standup"]  # nothing yet

    status, applied, action_id = planner.apply_plan(proposal)
    assert (status, applied) == ("accepted", [0, 1])
    titles = [e.title for e in planner.events("2030-01-07T00:00", "2030-01-08T00:00")]
    assert titles == ["Standup", "Invoice", "Slides"]

    planner.ledger.undo(action_id)  # one undo, the whole plan
    assert [e.title for e in planner.events("2030-01-07T00:00", "2030-01-08T00:00")] == ["Standup"]
    with pytest.raises(ValueError):
        planner.apply_plan(proposal)  # answered already


def test_accepting_some_items_and_clashes_are_skipped(planner):
    urgent_tasks(planner)
    proposal, _, items, _ = planner.propose_day("2030-01-07")
    first = items[0]
    planner.add_event("Dentist", first.starts_at, first.ends_at)  # the calendar changed since
    status, applied, _ = planner.apply_plan(proposal)
    assert status == "partially_applied" and applied == [1]


def test_a_newer_plan_replaces_the_older_one(planner):
    urgent_tasks(planner)
    older, *_ = planner.propose_day("2030-01-07")
    newer, *_ = planner.propose_day("2030-01-07")
    with pytest.raises(ValueError, match="superseded"):
        planner.apply_plan(older)
    assert planner.apply_plan(newer)[0] == "accepted"


def test_an_old_plan_expires(planner, settings):
    urgent_tasks(planner)
    proposal, *_ = planner.propose_day("2030-01-07")
    stores_for(settings, "u1").repo("proposals").update(proposal, {"expires_at": iso(now_utc() - timedelta(minutes=1))})
    with pytest.raises(ValueError, match="expired"):
        planner.apply_plan(proposal)


# By voice


def test_the_propose_tool_shows_a_card_and_apply_asks_with_every_block(planner):
    urgent_tasks(planner)
    emit = AsyncMock()
    bridge = ToolBridge("s", planner_tools(planner), emit, AsyncMock())
    bridge.ledger, bridge.user_id = planner.ledger, "u1"
    result = asyncio.run(bridge.execute('[{"name":"day_plan_propose","arguments":{"date":"2030-01-07"}}]', "turn1"))
    [card] = [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], PlanProposed)]
    assert card.message_id == "turn1" and [i.title for i in card.items] == ["Invoice", "Slides"]
    assert card.proposal_id in result

    asked = []

    async def answer(message):
        if isinstance(message, ToolConfirmRequest):
            asked.append(message)
            bridge.resolve(message.call_id, True)

    emit.side_effect = answer
    asyncio.run(bridge.execute(json.dumps([{"name": "day_plan_apply", "arguments": {"proposal_id": card.proposal_id}}]), "turn2"))
    assert asked[0].summary == "Add these blocks to your calendar?"
    assert [line[12:] for line in asked[0].details] == ["Invoice", "Slides"]
    [update] = [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], PlanUpdated)]
    assert update.status == "accepted" and update.action_id


def test_the_card_buttons_apply_or_decline(client, settings):
    planner = stores_for(settings, "u1").planner("UTC")
    planner.add_task("Invoice", "2030-01-07T17:00")
    proposal, *_ = planner.propose_day("2030-01-07")
    token, _ = issue_token(settings.signing_key(), user_id="u1")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/api/plans/{proposal}/apply", headers=bearer_for(settings, "u2"), json={}).status_code == 404
    body = client.post(f"/api/plans/{proposal}/apply", headers=headers, json={"items": [0]}).json()
    assert body["status"] == "accepted" and body["applied"] == [0]
    assert client.post(f"/api/plans/{proposal}/reject", headers=headers).status_code == 409


def bearer_for(settings, user):
    token, _ = issue_token(settings.signing_key(), user_id=user)
    return {"Authorization": f"Bearer {token}"}


def test_the_skill_ships(client, settings):
    items = client.get("/api/skills", headers=bearer_for(settings, "u1")).json()["items"]
    skill = next(s for s in items if s["id"] == "prepare-my-day")
    assert "day_plan_propose" in skill["allowed_tools"] and "prepare my day" in skill["triggers"]


# Review fixes


def test_unticked_items_are_a_choice_not_a_clash(planner):
    urgent_tasks(planner)
    proposal, _, items, _ = planner.propose_day("2030-01-07")
    assert planner.apply_plan(proposal, [1])[:2] == ("accepted", [1])


def test_a_spoken_yes_applies_only_the_ticked_items(planner):
    urgent_tasks(planner)
    proposal, *_ = planner.propose_day("2030-01-07")
    assert planner.choose(proposal, [0])
    assert planner.apply_plan(proposal)[1] == [0]  # no items given: the card's ticks


def test_a_past_day_cannot_be_planned(planner):
    with pytest.raises(ValueError):
        planner.propose_day("2020-01-01")


def test_rounding_never_goes_back_in_time():
    from app.planning import round_up

    assert round_up(at(9, 15).replace(second=40)) == at(9, 30)
    assert round_up(at(9, 15)) == at(9, 15)
