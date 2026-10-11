"""Session gateway tests, including the SECURITY.md section 6 checks."""

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.protocol import FRAME_BYTES
from app.session import MAX_CONNECTIONS_PER_IP, registry

from .conftest import ORIGIN


def connect(client, token, origin=ORIGIN):
    headers = {"origin": origin} if origin else {}
    return client.websocket_connect(f"/ws/session?token={token}", headers=headers)


def start(ws):
    ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
    return ws.receive_json()


def assert_closed_with(ws, code, end_reason="protocol_error"):
    assert ws.receive_json() == {"type": "session.end", "reason": end_reason}
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_text()
    assert closed.value.code == code


def test_session_start_reports_idle(client, token):
    with connect(client, token) as ws:
        assert start(ws) == {"type": "state", "state": "idle"}


def test_mute_and_unmute(client, token):
    with connect(client, token) as ws:
        start(ws)
        ws.send_text(json.dumps({"type": "control.mute", "muted": True}))
        assert ws.receive_json() == {"type": "state", "state": "muted"}
        ws.send_text(json.dumps({"type": "control.mute", "muted": False}))
        assert ws.receive_json() == {"type": "state", "state": "idle"}


def test_valid_audio_frames_are_accepted(client, token):
    with connect(client, token) as ws:
        start(ws)
        for _ in range(5):
            ws.send_bytes(b"\x00" * FRAME_BYTES)
        ws.send_text(json.dumps({"type": "control.mute", "muted": True}))
        assert ws.receive_json()["state"] == "muted"  # still open after audio


# SECURITY.md 6: "WebSocket without token / wrong Origin -> Connection refused"


def test_missing_token_is_refused(client):
    with pytest.raises(WebSocketDisconnect) as refused:
        with connect(client, ""):
            pass
    assert refused.value.code == 1008


def test_forged_token_is_refused(client, token):
    with pytest.raises(WebSocketDisconnect) as refused:
        with connect(client, token[:-2] + "AA"):
            pass
    assert refused.value.code == 1008


@pytest.mark.parametrize("origin", ["https://evil.example", None])
def test_wrong_or_missing_origin_is_refused(client, token, origin):
    with pytest.raises(WebSocketDisconnect) as refused:
        with connect(client, token, origin=origin):
            pass
    assert refused.value.code == 1008


def test_token_cannot_open_two_sessions(client, token):
    with connect(client, token) as ws:
        start(ws)
        with pytest.raises(WebSocketDisconnect) as refused:
            with connect(client, token):
                pass
        assert refused.value.code == 1008


def test_per_ip_connection_limit(client):
    tokens = [client.post("/api/session").json()["token"] for _ in range(MAX_CONNECTIONS_PER_IP + 1)]
    opened = [connect(client, t).__enter__() for t in tokens[:MAX_CONNECTIONS_PER_IP]]
    try:
        with pytest.raises(WebSocketDisconnect) as refused:
            with connect(client, tokens[-1]):
                pass
        assert refused.value.code == 1013
    finally:
        for ws in opened:
            ws.__exit__(None, None, None)
    assert not registry.sessions


# SECURITY.md 6: "100 KB WebSocket message -> Rejected"


def test_100kb_text_message_is_rejected(client, token):
    with connect(client, token) as ws:
        start(ws)
        ws.send_text("x" * 100 * 1024)
        assert_closed_with(ws, 1009)


def test_100kb_binary_message_is_rejected(client, token):
    with connect(client, token) as ws:
        start(ws)
        ws.send_bytes(b"\x00" * 100 * 1024)
        assert_closed_with(ws, 1003)


# SECURITY.md 5: "Every WebSocket message validated; unknown types rejected"


@pytest.mark.parametrize(
    "message",
    [
        {"type": "tool.run", "name": "shell"},
        {"type": "control.mute"},
        {"type": "control.mute", "muted": True, "extra": 1},
        {"type": "playback.position", "seq": -1, "samples_played": 0},
        {"type": "session.start", "client_sample_rate": 44100},
    ],
)
def test_invalid_messages_close_the_session(client, token, message):
    with connect(client, token) as ws:
        start(ws)
        ws.send_text(json.dumps(message))
        assert_closed_with(ws, 1008)


def test_non_json_text_is_rejected(client, token):
    with connect(client, token) as ws:
        start(ws)
        ws.send_text("not json")
        assert_closed_with(ws, 1008)


def test_audio_before_session_start_is_rejected(client, token):
    with connect(client, token) as ws:
        ws.send_bytes(b"\x00" * FRAME_BYTES)
        assert_closed_with(ws, 1008)


def test_wrong_frame_size_is_rejected(client, token):
    with connect(client, token) as ws:
        start(ws)
        ws.send_bytes(b"\x00" * (FRAME_BYTES - 2))
        assert_closed_with(ws, 1003)


def test_idle_session_ends_with_session_end(client, token, monkeypatch):
    import app.session

    monkeypatch.setattr(app.session, "IDLE_TIMEOUT_SECONDS", 0.05)
    with connect(client, token) as ws:
        start(ws)
        assert_closed_with(ws, 1000, end_reason="idle")


def test_registry_is_cleaned_up_after_disconnect(client, token):
    with connect(client, token) as ws:
        start(ws)
        assert registry.sessions
    # Give the server task a moment to run its finally block.
    client.get("/health")
    assert not registry.sessions


@pytest.mark.parametrize(
    "allowed, opted_in, logged",
    [(False, False, False), (False, True, False), (True, False, False), (True, True, True)],
)
def test_transcripts_are_logged_only_when_the_server_allows_and_the_user_opts_in(
    settings, tmp_path, monkeypatch, allowed, opted_in, logged
):
    import asyncio
    import json as jsonlib
    from unittest.mock import AsyncMock

    from app import session as gateway
    from app.engines import EngineChoice
    from app.voice_engine import TurnEnded, UserTranscript

    lines = []
    monkeypatch.setattr(gateway.transcript_log, "info", lambda msg, extra: lines.append(msg))
    settings.settings_path = str(tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(jsonlib.dumps({"transcripts_in_logs": opted_in}), encoding="utf-8")
    settings.allow_transcript_logs = allowed

    async def scenario():
        live = gateway.Session(AsyncMock(), "s1", settings, lambda *_: EngineChoice(None))
        await live.start_engine()
        await live.on_engine_event(UserTranscript("u1", "Hello there", True))
        await live.on_engine_event(TurnEnded("a1", "Hi."))

    asyncio.run(scenario())
    assert lines == (["user: Hello there", "assistant: Hi."] if logged else [])
