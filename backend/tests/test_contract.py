"""The shared fixture (docs/fixtures/demo_session.jsonl) must match the contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.protocol import TranscriptDelta, TranscriptTrim, ToolStatus, server_message

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "demo_session.jsonl"


def load():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


def test_every_fixture_event_is_a_valid_server_message():
    for line in load():
        server_message.validate_python(line["event"])


def test_fixture_is_in_time_order():
    times = [line["t_ms"] for line in load()]
    assert times == sorted(times) and times[0] == 0


def test_fixture_references_are_consistent():
    events = [server_message.validate_python(line["event"]) for line in load()]
    assistant_text: dict[str, str] = {}
    for e in events:
        if isinstance(e, TranscriptDelta) and e.speaker == "assistant":
            assistant_text[e.message_id] = assistant_text.get(e.message_id, "") + e.text
    for e in events:
        if isinstance(e, ToolStatus):
            assert e.message_id.startswith("a"), "tool chips belong to assistant turns"
        if isinstance(e, TranscriptTrim):
            assert assistant_text[e.message_id].strip() == e.heard_text
            assert e.unheard_text, "the demo interruption cuts off planned words"


def test_unknown_server_event_is_rejected():
    with pytest.raises(ValidationError):
        server_message.validate_python({"type": "state", "state": "idle", "extra": 1})
    with pytest.raises(ValidationError):
        server_message.validate_python({"type": "nope"})


def test_model_active_event():
    event = server_message.validate_python(
        {"type": "model.active", "role": "planner", "provider": "openrouter",
         "model": "nvidia/nemotron-3-nano", "backup": True}
    )
    assert event.backup is True
    with pytest.raises(ValidationError):
        server_message.validate_python(
            {"type": "model.active", "role": "planner", "provider": "unknown-router",
             "model": "x", "backup": False}
        )


def test_settings_view_never_carries_keys():
    from app.protocol import ProviderInfo, SettingsView

    fields = set(SettingsView.model_fields) | set(ProviderInfo.model_fields)
    assert not {f for f in fields if "key" in f or "url" in f or "secret" in f}
