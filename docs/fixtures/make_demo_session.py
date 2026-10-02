"""Generate demo_session.jsonl: the server events of the demo conversation.

Shared test data for both sides (docs/plan.md, C0.7):
- the frontend replays it to develop without a backend;
- the backend fake voice model uses the same script and timing.

Each line is {"t_ms": <time since session start>, "event": <server message>}.
An "audio.chunk" event stands for the header plus its binary PCM; the replay
creates the audio (the samples count gives its length). Assistant words are
sent as transcript deltas at the moment the word starts playing.

Run: python docs/fixtures/make_demo_session.py
"""

import json
from pathlib import Path

RATE = 22_050
CHUNK_MS = 200
MS_PER_WORD = 260  # assistant speaking pace
USER_MS_PER_WORD = 300

events: list[tuple[int, dict]] = []
audio_seq = 0


def emit(t_ms: int, event: dict) -> None:
    events.append((t_ms, event))


def state(t_ms: int, value: str, tool: str | None = None) -> None:
    event = {"type": "state", "state": value}
    if tool:
        event["tool"] = tool
    emit(t_ms, event)


def user_says(t_ms: int, message_id: str, text: str, backchannel: bool = False) -> int:
    """Partial captions while the user speaks, then a final one."""
    words = text.split()
    for i in range(1, len(words)):
        emit(t_ms + i * USER_MS_PER_WORD, {
            "type": "transcript.delta", "message_id": message_id, "speaker": "user",
            "text": " ".join(words[:i]), "final": False, "backchannel": backchannel,
        })
    end = t_ms + len(words) * USER_MS_PER_WORD
    emit(end, {
        "type": "transcript.delta", "message_id": message_id, "speaker": "user",
        "text": text, "final": True, "backchannel": backchannel,
    })
    return end


def assistant_says(t_ms: int, message_id: str, text: str, stop_after_words: int | None = None) -> int:
    """Audio chunks plus one caption delta per word, at the word's start time.
    Returns the time the audio ends (or stops, if interrupted)."""
    global audio_seq
    words = text.split()
    spoken = words if stop_after_words is None else words[:stop_after_words]
    duration = len(spoken) * MS_PER_WORD
    for offset in range(0, duration, CHUNK_MS):
        ms = min(CHUNK_MS, duration - offset)
        emit(t_ms + offset, {"type": "audio.chunk", "seq": audio_seq, "samples": RATE * ms // 1000})
        audio_seq += 1
    for i, word in enumerate(spoken):
        emit(t_ms + i * MS_PER_WORD, {
            "type": "transcript.delta", "message_id": message_id, "speaker": "assistant",
            "text": word if i == 0 else " " + word, "final": False,
        })
    if stop_after_words is None:
        emit(t_ms + duration, {
            "type": "transcript.delta", "message_id": message_id, "speaker": "assistant",
            "text": "", "final": True,
        })
    return t_ms + duration


# 1. A web question.
state(0, "idle")
state(400, "listening")
t = user_says(400, "u1", "What does full-duplex mean?")
state(t + 100, "tool", "web_search")
emit(t + 120, {"type": "tool.status", "call_id": "c1", "message_id": "a1", "name": "web_search", "status": "running"})
emit(t + 900, {
    "type": "tool.status", "call_id": "c1", "message_id": "a1", "name": "web_search", "status": "done",
    "sources": [
        {"title": "Duplex (telecommunications) - Wikipedia",
         "url": "https://en.wikipedia.org/wiki/Duplex_(telecommunications)"},
        {"title": "NVIDIA NemotronLabs VoiceChat 11B - model card",
         "url": "https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B"},
        {"title": "NemotronLabs VoiceChat - paper", "url": "https://arxiv.org/html/2609.21967"},
    ],
})
state(t + 1000, "assistant_speaking")
t = assistant_says(t + 1000, "a1", "It means both sides can talk at the same time, like a phone call. "
                   "I keep listening while I speak, so you can cut in whenever you like.")
state(t, "idle")

# 2. Weather, a backchannel, then an interruption.
state(t + 1200, "listening")
t = user_says(t + 1200, "u2", "Good. What's the weather in Lisbon?")
state(t + 100, "tool", "weather")
emit(t + 120, {"type": "tool.status", "call_id": "c2", "message_id": "a2", "name": "weather", "status": "running"})
emit(t + 600, {"type": "tool.status", "call_id": "c2", "message_id": "a2", "name": "weather", "status": "done"})
speak_at = t + 700
state(speak_at, "assistant_speaking")
weather = ("It's sunny in Lisbon right now, around 24 degrees. This evening the wind picks up "
           "from the north, so take a light jacket if you're out after dinner.")
heard_words = 18  # last word played: "north,"
# Backchannel right after "degrees." (word 9): TalkBack keeps going.
bc_at = speak_at + 9 * MS_PER_WORD
state(bc_at, "overlap")
user_says(bc_at, "u3", "mm-hm", backchannel=True)
state(bc_at + 400, "assistant_speaking")
# The user cuts in during the last heard word.
cut_at = speak_at + heard_words * MS_PER_WORD
assistant_says(speak_at, "a2", weather, stop_after_words=heard_words)
state(cut_at - 300, "overlap")
state(cut_at, "interrupted")
emit(cut_at, {"type": "audio.flush", "reason": "interrupted"})
emit(cut_at + 80, {
    "type": "transcript.trim", "message_id": "a2",
    "heard_text": " ".join(weather.split()[:heard_words]),
})
state(cut_at + 150, "listening")
t = user_says(cut_at - 300, "u4", "No, tomorrow.")
state(t + 100, "assistant_speaking")
t = assistant_says(t + 100, "a3", "Tomorrow is cloudier, with a high of 21 and rain likely after 4 pm.")
state(t, "idle")

# 3. A sensitive action that needs confirmation. The replay stops here and
# waits for the user's answer.
state(t + 1500, "listening")
t = user_says(t + 1500, "u5", "Forget my home city.")
state(t + 100, "assistant_speaking")
t = assistant_says(t + 100, "a4", "Okay. I need your OK first.")
emit(t + 50, {"type": "tool.confirm_request", "call_id": "c3", "summary": "Delete the memory “Home city is Lisbon”?"})
state(t + 60, "confirm")

events.sort(key=lambda pair: pair[0])
out = Path(__file__).with_name("demo_session.jsonl")
out.write_text("".join(json.dumps({"t_ms": t, "event": e}) + "\n" for t, e in events), encoding="utf-8")
print(f"wrote {len(events)} events, {events[-1][0] / 1000:.1f} s, to {out.name}")
