"""control.stop (Esc / Stop button) and the public-demo access code (SECURITY.md T8)."""

import json

from pydantic import SecretStr

from app.engines import EngineChoice, get_engine_factory
from app.main import app

from .conftest import ORIGIN
from .test_turn_taking import ScriptedEngine


def test_stop_flushes_trims_and_returns_to_idle(client):
    engine = ScriptedEngine(utterance="")
    app.dependency_overrides[get_engine_factory] = lambda: lambda _s: EngineChoice(engine)
    token = client.post("/api/session").json()["token"]
    received: list[dict] = []
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        chunks = 0
        while chunks < 10:
            message = ws.receive()
            if message.get("text"):
                event = json.loads(message["text"])
                received.append(event)
                chunks += event["type"] == "audio.chunk"
        ws.send_text(json.dumps({"type": "playback.position", "seq": 4, "samples_played": int(22_050 * 0.9)}))
        ws.send_text(json.dumps({"type": "control.stop"}))
        while True:
            message = ws.receive()
            if message.get("text"):
                received.append(json.loads(message["text"]))
                if received[-1]["type"] == "transcript.trim":
                    break
    app.dependency_overrides.clear()
    assert {"type": "audio.flush", "reason": "stopped"} in received
    assert {"type": "state", "state": "idle"} in received[-4:]
    assert {"type": "state", "state": "interrupted"} not in received
    assert received[-1]["heard_text"] == "one two"
    assert engine.interrupted == [("m1", "one two")]


def test_stop_needs_a_started_session(client):
    token = client.post("/api/session").json()["token"]
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "control.stop"}))
        message = ws.receive()
    assert message["type"] == "websocket.close" or "session.end" in message.get("text", "")


def test_stop_with_nothing_playing_just_reports_idle(client):
    token = client.post("/api/session").json()["token"]
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        assert json.loads(ws.receive_text()) == {"type": "state", "state": "idle"}
        ws.send_text(json.dumps({"type": "control.stop"}))
        assert json.loads(ws.receive_text()) == {"type": "state", "state": "idle"}


def test_no_access_code_means_open_sessions(client):
    assert client.post("/api/session").status_code == 200


def test_access_code_gates_session_tokens(client, settings):
    settings.access_code = SecretStr("tb-demo-2026")
    assert client.post("/api/session").status_code == 401
    assert client.post("/api/session", headers={"X-Access-Code": "wrong"}).status_code == 401
    ok = client.post("/api/session", headers={"X-Access-Code": "tb-demo-2026"})
    assert ok.status_code == 200 and ok.json()["token"]
    # The code itself never comes back in a response.
    assert "tb-demo-2026" not in client.post("/api/session").text
