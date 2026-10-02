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


def assert_closed_with(ws, code):
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


def test_registry_is_cleaned_up_after_disconnect(client, token):
    with connect(client, token) as ws:
        start(ws)
        assert registry.sessions
    # Give the server task a moment to run its finally block.
    client.get("/health")
    assert not registry.sessions
