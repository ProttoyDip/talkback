"""X2: turn-taking rules. Pure logic, no audio devices."""

import math
from array import array

from app.turn_taking import (
    BargeInDecider,
    EnergyVad,
    heard_split,
    is_backchannel,
    is_filler_only,
    looks_incomplete,
    strip_fillers,
)


def frame(amplitude: int) -> bytes:
    """A 20 ms, 16 kHz tone at the given amplitude (0 = silence)."""
    return array("h", (int(amplitude * math.sin(i / 3)) for i in range(320))).tobytes()


def run(vad: EnergyVad, amplitude: int, frames: int):
    state = None
    for _ in range(frames):
        state = vad.process(frame(amplitude))
    return state


def test_vad_silence_then_speech_then_silence():
    vad = EnergyVad()
    assert not run(vad, 0, 20).is_speech
    state = run(vad, 5000, 15)  # 300 ms of speech
    assert state.is_speech and state.speech_ms == 300
    assert not run(vad, 0, 15).is_speech  # past the 200 ms hangover


def test_vad_ignores_a_short_dip_inside_speech():
    vad = EnergyVad()
    run(vad, 5000, 10)
    assert run(vad, 0, 3).is_speech  # 60 ms dip
    assert run(vad, 5000, 1).speech_ms > 200


def test_vad_ignores_steady_room_noise():
    vad = EnergyVad()
    assert not run(vad, 200, 100).is_speech


def test_speech_shorter_than_250_ms_never_interrupts():
    decider = BargeInDecider()
    assert decider.update(200, "stop") == "none"


def test_real_words_interrupt_once_speech_is_long_enough():
    decider = BargeInDecider()
    assert decider.update(260, "wait, actually") == "interrupt"


def test_backchannel_does_not_interrupt():
    decider = BargeInDecider()
    assert decider.update(300, "mm-hm") == "overlap"
    assert decider.update(500, "yeah") == "overlap"


def test_long_sound_interrupts_even_without_words():
    decider = BargeInDecider()
    assert decider.update(300, "") == "overlap"
    assert decider.update(650, "") == "interrupt"


def test_backchannel_word_list():
    assert is_backchannel("Mm-hm.")
    assert is_backchannel("uh-huh")
    assert is_backchannel("okay, right")
    assert not is_backchannel("no")  # an answer or a correction
    assert not is_backchannel("yeah but what about Paris")


WORDS = [("It", 0.0, 0.2), ("means", 0.2, 0.6), ("both", 0.6, 0.9), ("sides", 0.9, 1.3), ("talk.", 1.3, 1.6)]


def test_heard_split_cuts_at_the_playback_position():
    assert heard_split(WORDS, 0.0) == ("", "It means both sides talk.")
    assert heard_split(WORDS, 0.9) == ("It means both", "sides talk.")
    assert heard_split(WORDS, 99) == ("It means both sides talk.", "")


def test_heard_split_counts_a_half_played_word():
    heard, unheard = heard_split(WORDS, 0.75)  # "both" is 50% played
    assert heard == "It means both" and unheard == "sides talk."


def test_fillers_and_stutters_are_removed():
    assert strip_fillers("Umm, I I want, uh, the weather") == "I want, the weather"
    assert strip_fillers("Ahh... hmm") == ""


def test_filler_only_input_is_hesitation_not_a_request():
    assert is_filler_only("umm")
    assert is_filler_only("Uh, hmm...")
    assert not is_filler_only("umm what is the weather")


def test_unfinished_thoughts_are_detected():
    assert looks_incomplete("I want to know about the")
    assert looks_incomplete("What is the weather in Paris and")
    assert looks_incomplete("Well,")
    assert looks_incomplete("So um")
    assert not looks_incomplete("What is the weather in Paris?")
    assert not looks_incomplete("Tell me a joke")


# Gateway: barge-in end to end, with a scripted engine.

import asyncio
import json

from app.engines import EngineChoice, get_engine_factory
from app.main import app
from app.voice_engine import AssistantAudio, AssistantWord, StateChanged, TurnEnded, UserTranscript

from .conftest import ORIGIN


class ScriptedEngine:
    """Speaks 2 s ("one two three four five", 0.4 s each). On the first
    microphone frame the user is heard saying `utterance`."""

    def __init__(self, utterance: str = "wait stop") -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.utterance = utterance
        self.interrupted: list[tuple[str, str]] = []
        self.heard_frames = 0
        self.playback_active = lambda: False

    async def start(self, context) -> None:
        self.queue.put_nowait(StateChanged("assistant_speaking"))
        for _ in range(10):  # 10 x 200 ms
            self.queue.put_nowait(AssistantAudio("m1", b"\x01\x00" * 4410))
        for i, word in enumerate("one two three four five".split()):
            self.queue.put_nowait(AssistantWord("m1", word, i * 0.4, (i + 1) * 0.4))
        self.queue.put_nowait(TurnEnded("m1", "one two three four five"))

    async def send_audio(self, frame: bytes) -> None:
        self.heard_frames += 1
        if self.heard_frames == 1 and self.utterance:
            self.queue.put_nowait(UserTranscript("u1", self.utterance, False))

    async def events(self):
        while True:
            yield await self.queue.get()

    async def interrupt(self, message_id: str, heard_text: str) -> None:
        self.interrupted.append((message_id, heard_text))

    async def send_tool_response(self, call_id, payload) -> None: ...
    async def say_filler(self, text) -> None: ...
    async def confirm_tool(self, message) -> None: ...
    async def close(self) -> None: ...


def drive(client, engine: ScriptedEngine, speech_frames: int) -> list[dict]:
    app.dependency_overrides[get_engine_factory] = lambda: lambda _s: EngineChoice(engine)
    token = client.post("/api/session").json()["token"]
    received: list[dict] = []
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        chunks = 0
        while chunks < 10:  # wait until all audio is queued
            message = ws.receive()
            if message.get("text"):
                event = json.loads(message["text"])
                received.append(event)
                chunks += event["type"] == "audio.chunk"
        # The browser has played 0.9 s: "one two" heard, "three" not.
        ws.send_text(json.dumps({"type": "playback.position", "seq": 4, "samples_played": int(22_050 * 0.9)}))
        for _ in range(speech_frames):
            ws.send_bytes(frame(5000))
        ws.send_bytes(frame(0))  # a last frame so the engine gets audio even for 0 speech
        # Collect what the gateway says in reply, until a short timeout.
        # The gateway answers within a moment, or the 2 s of audio simply
        # finish and the state returns to idle.
        while True:
            message = ws.receive()
            if message.get("text"):
                received.append(json.loads(message["text"]))
                if received[-1]["type"] == "transcript.trim" or received[-1] == {"type": "state", "state": "idle"}:
                    break
    app.dependency_overrides.clear()
    return received


def test_interrupting_flushes_audio_and_trims_to_heard_words(client):
    engine = ScriptedEngine("wait stop")
    received = drive(client, engine, speech_frames=20)  # 400 ms of speech
    types = [e["type"] for e in received]
    assert {"type": "audio.flush", "reason": "interrupted"} in received
    assert {"type": "state", "state": "interrupted"} in received
    trim = next(e for e in received if e["type"] == "transcript.trim")
    assert trim["message_id"] == "m1"
    assert trim["heard_text"] == "one two"
    assert trim["unheard_text"] == "three four five"
    assert types.index("audio.flush") < types.index("transcript.trim")
    assert engine.interrupted == [("m1", "one two")]


def test_a_backchannel_does_not_interrupt(client):
    engine = ScriptedEngine("mm-hm")
    received = drive(client, engine, speech_frames=20)
    assert not [e for e in received if e["type"] in ("audio.flush", "transcript.trim")]
    assert {"type": "state", "state": "overlap"} in received
    assert engine.interrupted == []


def test_speech_under_250_ms_does_not_interrupt(client):
    engine = ScriptedEngine("stop")
    received = drive(client, engine, speech_frames=8)  # 160 ms
    assert not [e for e in received if e["type"] in ("audio.flush", "transcript.trim")]


# Conversation controller inside the cascade engine.

from app.cascade_engine import CascadeEngine

from .test_cascade import FakeSTT, FakeTTS


def controller(playing: bool = False, wait: float = 0.05) -> CascadeEngine:
    engine = CascadeEngine(FakeSTT(), FakeTTS(), llm=None, incomplete_wait_s=wait)  # type: ignore[arg-type]
    engine.loop = asyncio.get_event_loop()
    engine.playback_active = lambda: playing
    return engine


def turns(engine: CascadeEngine) -> list[str]:
    out = []
    while not engine.user_turns.empty():
        out.append(engine.user_turns.get_nowait())
    return out


def test_filler_only_turn_is_not_answered():
    async def run():
        engine = controller()
        engine._on_transcript("umm", True)
        engine._on_transcript("uh, hmm...", True)
        await asyncio.sleep(0.1)
        return turns(engine)

    assert asyncio.run(run()) == []


def test_fillers_are_stripped_from_what_the_model_sees():
    async def run():
        engine = controller()
        engine._on_transcript("Umm, what is, uh, the weather in Paris?", True)
        return turns(engine)

    assert asyncio.run(run()) == ["what is, the weather in Paris?"]


def test_unfinished_turn_waits_and_joins_the_rest():
    async def run():
        engine = controller(wait=0.2)
        engine._on_transcript("What is the weather in Paris and", True)
        assert turns(engine) == []  # held
        engine._on_transcript("also in Rome?", True)
        return turns(engine)

    assert asyncio.run(run()) == ["What is the weather in Paris and also in Rome?"]


def test_unfinished_turn_is_answered_after_the_wait():
    async def run():
        engine = controller(wait=0.05)
        engine._on_transcript("Tell me about the", True)
        await asyncio.sleep(0.15)
        return turns(engine)

    assert asyncio.run(run()) == ["Tell me about the"]


def test_new_speech_cancels_the_wait():
    async def run():
        engine = controller(wait=0.05)
        engine._on_transcript("Tell me about the", True)
        engine._on_transcript("moon", False)  # the user is talking again
        await asyncio.sleep(0.15)
        return turns(engine)

    assert asyncio.run(run()) == []


def test_backchannel_over_speech_is_ignored_but_answered_when_idle():
    async def run(playing: bool):
        engine = controller(playing=playing)
        engine._on_transcript("okay", True)
        return turns(engine)

    assert asyncio.run(run(True)) == []
    assert asyncio.run(run(False)) == ["okay"]
