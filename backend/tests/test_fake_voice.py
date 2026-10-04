"""X1: the fake voice engine, through the real gateway."""

import json

from app.engines import get_engine_factory
from app.main import app

from .conftest import ORIGIN
from .test_turn_taking import frame


def session(client, settings):
    settings.voice_engine = "fake"
    app.dependency_overrides[get_engine_factory] = get_engine_factory  # use the real factory
    token = client.post("/api/session").json()["token"]
    return client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN})


def test_a_spoken_turn_runs_the_whole_scripted_conversation(client, settings):
    with session(client, settings) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        for _ in range(5):
            ws.send_bytes(frame(5000))  # speech starts the script
        events = []
        while True:
            message = ws.receive()
            if message.get("text"):
                events.append(json.loads(message["text"]))
                if events[-1] == {"type": "state", "state": "idle"} and any(
                    e.get("speaker") == "assistant" and e.get("final") for e in events
                ):
                    break
    user = [e for e in events if e["type"] == "transcript.delta" and e["speaker"] == "user" and e["final"]]
    assert user[0]["text"] == "What's the weather like in Lisbon tomorrow?"
    assert [e["status"] for e in events if e["type"] == "tool.status"] == ["running", "done"]
    said = "".join(e["text"] for e in events if e["type"] == "transcript.delta" and e["speaker"] == "assistant")
    assert said.startswith("Tomorrow in Lisbon looks mild") and said.endswith("for the evening.")


def test_interrupting_the_fake_engine_trims_and_stops_it(client, settings):
    with session(client, settings) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        for _ in range(5):
            ws.send_bytes(frame(5000))
        events, chunks = [], 0
        while chunks < 3:  # TalkBack is now speaking
            message = ws.receive()
            if message.get("text"):
                events.append(json.loads(message["text"]))
                chunks += events[-1]["type"] == "audio.chunk"
        ws.send_text(json.dumps({"type": "playback.position", "seq": 2, "samples_played": int(22_050 * 1.1)}))
        for _ in range(25):  # the user talks over it for 500 ms
            ws.send_bytes(frame(5000))
        while True:
            message = ws.receive()
            if message.get("text"):
                events.append(json.loads(message["text"]))
                if events[-1]["type"] == "transcript.trim":
                    break
    trim = events[-1]
    assert trim["heard_text"].startswith("Tomorrow in Lisbon") and trim["unheard_text"]
    assert {"type": "audio.flush", "reason": "interrupted"} in events
