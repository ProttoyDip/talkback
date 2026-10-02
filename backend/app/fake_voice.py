"""Fake voice engine (plan.md X1): a scripted conversation with no keys, no GPU.

When it hears speech on the microphone it "understands" the next canned
question, shows a weather tool chip for the first one, and answers with a tone
and word timing. Interrupting it works like the real engines, so the whole
interface (captions, tool chips, barge-in, trimming) can be demoed and tested
offline. Select it with VOICE_ENGINE=fake.
"""

import asyncio
import math
from array import array
from collections.abc import AsyncIterator

from .protocol import ToolConfirm, ToolStatus
from .turn_taking import EnergyVad
from .voice_engine import (
    AssistantAudio,
    AssistantWord,
    EngineEvent,
    ModelInUse,
    ProtocolEvent,
    SessionContext,
    StateChanged,
    TurnEnded,
    UserTranscript,
)

SAMPLE_RATE = 22_050
CHUNK_SAMPLES = 4_410  # 200 ms
WORD_SECONDS = 0.35

SCRIPT = [
    (
        "What's the weather like in Lisbon tomorrow?",
        "Tomorrow in Lisbon looks mild, around twenty degrees, with a low chance of rain. "
        "It should be a good day to walk outside, so I would bring a light jacket for the evening.",
    ),
    (
        "How do you handle it when I interrupt you?",
        "I stop as soon as you speak, and I remember only the words you actually heard. "
        "Then I listen to your correction and carry on from there.",
    ),
    (
        "Thanks, that is all for now.",
        "You are welcome. Talk to me any time, and interrupt me whenever you like.",
    ),
]


def tone(seconds: float) -> bytes:
    count = int(SAMPLE_RATE * seconds)
    return array("h", (int(2500 * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)) for i in range(count))).tobytes()


class FakeVoiceEngine:
    def __init__(self, pace: float = 0.12) -> None:
        self.queue: asyncio.Queue[EngineEvent] = asyncio.Queue()
        self.vad = EnergyVad()
        self.pace = pace  # seconds between the user's words
        self.turn: asyncio.Task | None = None
        self.step = 0
        self.counter = 0
        self.playback_active = lambda: False

    def _emit(self, event: EngineEvent) -> None:
        self.queue.put_nowait(event)

    async def start(self, context: SessionContext) -> None:
        self._emit(ModelInUse(role="voice", provider="nvidia", model="Demo script (fake voice)", backup=False))

    async def send_audio(self, frame: bytes) -> None:
        speaking = self.vad.process(frame).is_speech
        busy = self.turn is not None and not self.turn.done()
        if speaking and not busy and not self.playback_active():
            self.turn = asyncio.create_task(self._converse())

    async def events(self) -> AsyncIterator[EngineEvent]:
        while True:
            yield await self.queue.get()

    async def interrupt(self, message_id: str, heard_text: str) -> None:
        if self.turn and not self.turn.done():
            self.turn.cancel()

    async def send_tool_response(self, call_id: str, payload: str) -> None: ...

    async def say_filler(self, text: str) -> None: ...

    async def confirm_tool(self, message: ToolConfirm) -> None: ...

    async def close(self) -> None:
        if self.turn and not self.turn.done():
            self.turn.cancel()

    async def _converse(self) -> None:
        question, answer = SCRIPT[self.step % len(SCRIPT)]
        with_tool = self.step % len(SCRIPT) == 0
        self.step += 1
        self.counter += 1
        user_id, reply_id = f"u{self.counter}", f"a{self.counter}"

        self._emit(StateChanged("listening"))
        words = question.split()
        for i in range(len(words)):
            await asyncio.sleep(self.pace)
            self._emit(UserTranscript(user_id, " ".join(words[: i + 1]), final=i == len(words) - 1))

        self._emit(StateChanged("thinking"))
        if with_tool:
            self._emit(StateChanged("tool", tool="weather"))
            self._emit(ProtocolEvent(ToolStatus(call_id=f"c{self.counter}", message_id=reply_id, name="weather", status="running")))
            await asyncio.sleep(0.8)
            self._emit(ProtocolEvent(ToolStatus(call_id=f"c{self.counter}", message_id=reply_id, name="weather", status="done")))

        reply_words = answer.split()
        seconds = len(reply_words) * WORD_SECONDS
        self._emit(StateChanged("assistant_speaking"))
        for _ in range(math.ceil(seconds / 0.2)):
            self._emit(AssistantAudio(reply_id, tone(0.2)))
        for i, word in enumerate(reply_words):
            self._emit(AssistantWord(reply_id, word, i * WORD_SECONDS, (i + 1) * WORD_SECONDS))
        self._emit(TurnEnded(reply_id, answer))
