"""Plan P4: action history with undo, correction-aware memory, suggestions."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.actions import ActionLedger, UndoConflict
from app.cascade_engine import CascadeEngine
from app.db.schema import SQLITE_MIGRATIONS
from app.db.sqlite_repo import SqliteDatabase
from app.memory import MemoryStore, MemoryWrite, remember
from app.protocol import ToolStatus
from app.stores import repo, stores_for
from app.supabase_store import SupabaseMemoryStore
from app.tool_bridge import ToolBridge
from app.tools import ToolResult
from app.tools.memory import memory_tools
from app.tokens import issue_token

from .fake_postgrest import FakePostgrest
from .test_cascade import FakeSTT, FakeTTS


def said(text: str, utterance: str | None = None) -> MemoryWrite:
    return MemoryWrite(text=text, kind="fact", source="user_utterance", utterance=utterance or text, confidence=0.9)


@pytest.fixture
def stores(settings):
    return stores_for(settings, "u1")


# Storage


def test_an_old_database_upgrades_with_its_memories(tmp_path):
    path = tmp_path / "old.sqlite3"
    SqliteDatabase(path, SQLITE_MIGRATIONS[:2])  # the schema before plan P4
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO memories (id, text, kind, source, utterance, created_at, confidence, user_id)"
            " VALUES ('m1', 'Home city is Lisbon', 'fact', 'user_utterance', 'x', '2026-10-01', 0.9, 'u1')"
        )
    store = MemoryStore(path, "u1")
    [item] = store.list("Lisbon")  # the full-text index was rebuilt
    assert (item.id, item.status, item.source) == ("m1", "confirmed", "user_utterance")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == len(SQLITE_MIGRATIONS)


def test_the_database_refuses_a_suggestion_in_use(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    suggestion = MemoryWrite(text="Likes jazz", kind="preference", source="assistant_suggestion",
                             utterance="(suggested)", confidence=0.5)
    with pytest.raises(ValueError):
        store.create(suggestion)  # status confirmed + assistant source: never
    assert store.create(suggestion, status="suggested").status == "suggested"


# Corrections


def test_a_correction_replaces_the_old_memory_and_undo_brings_it_back(stores):
    emit = AsyncMock()
    ledger = stores.ledger()
    lisbon = asyncio.run(remember(stores.memory, said("I live in Lisbon"), emit, slot="home", ledger=ledger))
    rome = asyncio.run(remember(stores.memory, said("I live in Rome now"), emit, slot="home", ledger=ledger))

    saved = emit.await_args.args[0]
    assert (saved.replaced_id, saved.replaced_text) == (lisbon.id, "I live in Lisbon")
    assert [m.text for m in stores.memory.in_use()] == ["I live in Rome now"]
    history = {m.text: m for m in stores.memory.list(history=True)}
    assert history["I live in Lisbon"].status == "superseded"
    assert history["I live in Lisbon"].superseded_by == rome.id

    ledger.undo(saved.action_id)
    assert [m.text for m in stores.memory.in_use()] == ["I live in Lisbon"]


class QuietLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def stream(self, messages, on_provider, tools=None):
        self.prompts.append(messages[0]["content"])
        yield "Okay."


def test_saying_a_correction_without_remember_that_updates_the_memory(stores):
    async def scenario():
        llm = QuietLLM()
        engine = CascadeEngine(FakeSTT(), FakeTTS(), llm, memory_store=stores.memory, ledger=stores.ledger())  # type: ignore[arg-type]
        await engine._answer("Remember that I live in Lisbon.")
        await engine._answer("Actually, I live in Rome now.")
        await engine._answer("What's new?")
        return llm.prompts

    prompts = asyncio.run(scenario())
    assert "I live in Rome now" in prompts[-1] and "Lisbon" not in prompts[-1]


def test_a_correction_with_nothing_to_correct_is_not_saved(stores):
    async def scenario():
        engine = CascadeEngine(FakeSTT(), FakeTTS(), QuietLLM(), memory_store=stores.memory)  # type: ignore[arg-type]
        await engine._answer("Actually, I live in Rome now.")

    asyncio.run(scenario())
    assert stores.memory.list() == []


# Suggestions


def test_suggestions_wait_for_the_users_ok(stores):
    store = stores.memory
    suggested = store.create(MemoryWrite(text="Likes jazz", kind="preference", source="assistant_suggestion",
                                         utterance="(suggested)", confidence=0.5), status="suggested")
    assert store.in_use() == []
    from app.protocol import MemoryUpdate
    store.update(suggested.id, MemoryUpdate(status="confirmed"))
    assert [m.text for m in store.in_use()] == ["Likes jazz"]
    with pytest.raises(ValueError):  # only a suggestion changes status
        store.update(suggested.id, MemoryUpdate(status="dismissed"))


def test_no_suggestions_after_web_results():
    bridge = ToolBridge("s", memory_tools(MemoryStore(":memory:") if False else _tmp_store()), AsyncMock(), AsyncMock())
    bridge.tainted.add("turn")
    result = asyncio.run(bridge.execute('[{"name":"memory_suggest","arguments":{"text":"Likes jazz"}}]', "turn"))
    assert "not_after_web_results" in result


def _tmp_store():
    import tempfile
    from pathlib import Path

    return MemoryStore(Path(tempfile.mkdtemp()) / "m.sqlite3")


# The ledger


def test_the_same_change_is_recorded_once(stores):
    ledger = stores.ledger()
    first = ledger.record("memory_delete", "done", "Forgot x", key="k1")
    again = ledger.record("memory_delete", "done", "Forgot x", key="k1")
    assert first["id"] == again["id"]
    assert len(ledger.list()) == 1


def test_undo_refuses_when_the_memory_changed_since(stores):
    from app.protocol import MemoryUpdate

    ledger = stores.ledger()
    item = stores.memory.create(said("Likes tea"))
    before = stores.memory.row(item.id)
    stores.memory.update(item.id, MemoryUpdate(text="Likes green tea"))
    after = stores.memory.row(item.id)
    action = ledger.record("memory_write", "done", "Edited", undo={
        "op": "memory.revert", "id": item.id, "after_updated_at": after["updated_at"],
        "before": {k: before[k] for k in ("text", "kind", "status", "updated_at")},
    })
    stores.memory.update(item.id, MemoryUpdate(text="Likes black tea"))  # a newer edit
    with pytest.raises(UndoConflict):
        ledger.undo(action["id"])
    assert stores.memory.get(item.id).text == "Likes black tea"


def test_a_repeated_delete_in_one_turn_runs_once(stores):
    item = stores.memory.create(said("Home city is Lisbon"))
    runs = []
    tools = memory_tools(stores.memory, stores.ledger())
    original = tools[1].run

    async def counting(args):
        runs.append(1)
        return await original(args)

    from dataclasses import replace
    tools[1] = replace(tools[1], run=counting)
    emit = AsyncMock()
    bridge = ToolBridge("s", tools, emit, AsyncMock())
    bridge.ledger, bridge.user_id = stores.ledger(), "u1"

    async def approve(message):
        from app.protocol import ToolConfirmRequest
        if isinstance(message, ToolConfirmRequest):
            bridge.resolve(message.call_id, True)

    emit.side_effect = approve
    call = '[{"name":"memory_delete","arguments":{"id":"%s","text":"Home city is Lisbon"}}]' % item.id
    asyncio.run(bridge.execute(call, "turn"))
    asyncio.run(bridge.execute(call, "turn"))  # the model repeats itself
    assert runs == [1]
    finals = [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], ToolStatus) and c.args[0].status != "running"]
    assert finals[0].status == "done" and finals[0].undoable and finals[0].action_id
    assert (finals[1].status, finals[1].reason, finals[1].action_id) == ("done", "already_done", finals[0].action_id)


# The REST routes


def bearer(settings, user="u1"):
    token, _ = issue_token(settings.signing_key(), user_id=user)
    return {"Authorization": f"Bearer {token}"}


def test_forget_then_undo_from_the_activity_list(client, settings, stores):
    item = stores.memory.create(said("Home city is Lisbon"))
    headers = bearer(settings)
    assert client.delete(f"/api/memories/{item.id}", headers=headers).status_code == 204
    [action] = client.get("/api/actions", headers=headers).json()["items"]
    assert action["summary"] == "Forgot “Home city is Lisbon”" and action["undoable"]
    undone = client.post(f"/api/actions/{action['id']}/undo", headers=headers).json()
    assert undone["status"] == "undone" and not undone["undoable"]
    assert [m["text"] for m in client.get("/api/memories", headers=headers).json()["items"]] == ["Home city is Lisbon"]
    assert client.post(f"/api/actions/{action['id']}/undo", headers=headers).status_code == 404  # only once


def test_confirming_a_suggestion_is_an_undoable_action(client, settings, stores):
    headers = bearer(settings)
    suggested = stores.memory.create(MemoryWrite(text="Likes jazz", kind="preference", source="assistant_suggestion",
                                                 utterance="(suggested)", confidence=0.5), status="suggested")
    body = client.patch(f"/api/memories/{suggested.id}", headers=headers, json={"status": "confirmed"}).json()
    assert body["status"] == "confirmed"
    [action] = client.get("/api/actions", headers=headers).json()["items"]
    client.post(f"/api/actions/{action['id']}/undo", headers=headers)
    assert stores.memory.get(suggested.id).status == "suggested"
    assert client.patch(
        f"/api/memories/{stores.memory.create(said('x y z')).id}", headers=headers, json={"status": "dismissed"}
    ).status_code == 409


def test_actions_belong_to_one_user(client, settings, stores):
    item = stores.memory.create(said("Secret plan"))
    client.delete(f"/api/memories/{item.id}", headers=bearer(settings))
    [action] = client.get("/api/actions", headers=bearer(settings)).json()["items"]
    assert client.get("/api/actions", headers=bearer(settings, "u2")).json()["items"] == []
    assert client.post(f"/api/actions/{action['id']}/undo", headers=bearer(settings, "u2")).status_code == 404


# Supabase parity


def test_the_supabase_store_corrects_and_suggests_the_same_way():
    fake = FakePostgrest()
    store = SupabaseMemoryStore(
        "https://p.supabase.test", SecretStr("sb_secret_test"), "u1", transport=httpx.MockTransport(fake),
    )
    old = store.create(said("I live in Lisbon"), slot="home")
    assert store.find_slot("home").id == old.id
    new = store.create(said("I live in Rome"), slot="home")
    assert store.supersede(old.id, new.id)
    assert [m.text for m in store.in_use()] == ["I live in Rome"]
    assert {m.status for m in store.list(history=True)} == {"confirmed", "superseded"}
    row = store.row(new.id)
    assert store.delete(new.id, "I live in Rome")
    store.restore(row)
    assert store.get(new.id).text == "I live in Rome"
    assert all(r.url.params.get("user_id") == "eq.u1" for r in fake.seen if r.method != "POST")


# Review fixes


def test_undoing_an_edit_keeps_search_right(stores):
    from app.protocol import MemoryUpdate

    ledger = stores.ledger()
    item = stores.memory.create(said("Home city is Lisbon"))
    before = stores.memory.row(item.id)
    stores.memory.update(item.id, MemoryUpdate(text="Home city is Rome"))
    after = stores.memory.row(item.id)
    action = ledger.record("memory_write", "done", "Edited", undo={
        "op": "memory.revert", "id": item.id, "after_updated_at": after["updated_at"],
        "before": {k: before[k] for k in ("text", "kind", "status", "updated_at")},
    })
    ledger.undo(action["id"])
    assert [m.text for m in stores.memory.list("Lisbon")] == ["Home city is Lisbon"]
    assert stores.memory.list("Rome") == []  # no stale full-text entry


def test_undoing_an_older_correction_waits_for_the_newer_one(stores):
    emit, ledger = AsyncMock(), stores.ledger()
    asyncio.run(remember(stores.memory, said("I live in Lisbon"), emit, slot="home", ledger=ledger))
    asyncio.run(remember(stores.memory, said("I live in Rome"), emit, slot="home", ledger=ledger))
    to_rome = emit.await_args.args[0].action_id
    asyncio.run(remember(stores.memory, said("I live in Paris"), emit, slot="home", ledger=ledger))
    with pytest.raises(UndoConflict):
        ledger.undo(to_rome)
    assert [m.text for m in stores.memory.in_use()] == ["I live in Paris"]


def test_undoing_a_suggestion_after_keeping_it_is_refused(stores):
    from app.protocol import MemoryUpdate

    tools = memory_tools(stores.memory, stores.ledger())
    emit = AsyncMock()
    bridge = ToolBridge("s", tools, emit, AsyncMock())
    bridge.ledger, bridge.user_id = stores.ledger(), "u1"
    asyncio.run(bridge.execute('[{"name":"memory_suggest","arguments":{"text":"Likes jazz"}}]', "turn"))
    from app.protocol import MemorySaved
    [saved] = [c.args[0] for c in emit.await_args_list if isinstance(c.args[0], MemorySaved)]
    assert saved.status == "suggested" and saved.action_id  # the toast offers Keep
    stores.memory.update(saved.id, MemoryUpdate(status="confirmed"))
    with pytest.raises(UndoConflict):
        stores.ledger().undo(saved.action_id)
    assert stores.memory.get(saved.id).status == "confirmed"


def test_a_typed_memory_is_marked_typed_even_with_fillers(stores):
    async def scenario():
        # Not started: no worker takes the turn, so the test reads the queue itself.
        engine = CascadeEngine(FakeSTT(), FakeTTS(), QuietLLM(), memory_store=stores.memory)  # type: ignore[arg-type]
        engine.submit_text("Um, remember that I like tea.")
        text, typed = engine.user_turns.get_nowait()
        assert (text, typed) == ("remember that I like tea.", True)
        await engine._answer(text, typed)

    asyncio.run(scenario())
    [item] = stores.memory.list()
    assert item.source == "user_text"


# Security review: forgetting means forgetting


def test_undo_copies_expire_and_summaries_lose_the_text(stores):
    from datetime import datetime, timedelta, timezone

    ledger = stores.ledger()
    item = stores.memory.create(said("Secret plan"))
    row = stores.memory.row(item.id)
    stores.memory.delete(item.id)
    action = ledger.record("memory_delete", "done", "Forgot “Secret plan”", undo={"op": "memory.restore", "rows": [row]})
    ledger.expire(older_than=datetime.now(timezone.utc) + timedelta(seconds=1))
    stored = stores.repo("actions").get(action["id"])
    assert stored["undo"] is None and stored["summary"] == "Forgot a memory"
    assert not ledger.list()[0].undoable


def test_forget_everything_erases_memory_text_from_earlier_history(client, settings, stores):
    headers = bearer(settings)
    first = stores.memory.create(said("Secret plan"))
    client.delete(f"/api/memories/{first.id}", headers=headers)
    stores.memory.create(said("Another thing"))
    client.delete("/api/memories", headers=headers)
    summaries = [a["summary"] for a in client.get("/api/actions", headers=headers).json()["items"]]
    assert summaries == ["Forgot all 1 memories", "Forgot a memory"]
