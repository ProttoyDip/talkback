"""Plan B voice engine: speech-to-text -> Nemotron -> text-to-speech.

Used until NVIDIA VoiceChat runs on a Nebius GPU (prd.md section 12).
- Each final transcript starts a reply. Replies stream sentence by sentence:
  the first sentence is spoken while Nemotron writes the rest.
- Turn-taking (barge-in, backchannels, trimming) is X2's job: it calls
  interrupt(). Until then, user turns that arrive during a reply wait.
"""

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator

from .llm import LlmClient, LlmProvider, LlmUnavailable
from .speech import SpeechToText, TextToSpeech
from .voice_engine import (
    AssistantAudio,
    AssistantWord,
    EngineEvent,
    EngineProblem,
    ModelInUse,
    SessionContext,
    StateChanged,
    TurnEnded,
    UserTranscript,
)

log = logging.getLogger("talkback.cascade")

SYSTEM_PROMPT = (
    "You are TalkBack, a friendly voice assistant. Your words are spoken aloud. "
    "Answer in one to three short sentences, under 20 seconds of speech. "
    "Use plain words. No lists, no markdown, no emoji, no URLs. "
    "If the user corrects you, follow the correction. "
    "You cannot look anything up, check the weather or browse the web yet. "
    "If asked for current information, say briefly that you can't check it right now. "
    "Never offer to do something you cannot do."
)

CHUNK_SAMPLES = 4_410  # 200 ms at 22.05 kHz
MAX_HISTORY_TURNS = 20
# Split spoken text at sentence ends, or at a comma once a clause is long.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MARKDOWN = re.compile(r"[*_#`>|]+")


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _speakable(text: str) -> str:
    return " ".join(MARKDOWN.sub("", text).split())


class CascadeEngine:
    def __init__(self, stt: SpeechToText, tts: TextToSpeech, llm: LlmClient) -> None:
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.queue: asyncio.Queue[EngineEvent] = asyncio.Queue()
        self.history: list[dict[str, str]] = []
        self.user_turns: asyncio.Queue[str] = asyncio.Queue()
        self.user_message_id: str | None = None
        self.reply_message_id: str | None = None
        self.worker: asyncio.Task[None] | None = None
        self.reply: asyncio.Task[None] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.planner_reported: str | None = None
        # message_id -> heard text, set by interrupt() (may arrive mid-reply).
        self.heard: dict[str, str] = {}

    def _emit(self, event: EngineEvent) -> None:
        self.queue.put_nowait(event)

    # VoiceEngine interface

    async def start(self, context: SessionContext) -> None:
        self.loop = asyncio.get_running_loop()
        loop = self.loop
        self.stt.start(
            on_result=lambda text, final: loop.call_soon_threadsafe(self._on_transcript, text, final),
            on_error=lambda message: loop.call_soon_threadsafe(
                self._emit, EngineProblem("voice_engine_offline", message)
            ),
        )
        self._emit(ModelInUse(role="voice", provider="nvidia", model="Parakeet + Magpie TTS", backup=False))
        self.worker = asyncio.create_task(self._serve_turns())

    async def send_audio(self, frame: bytes) -> None:
        self.stt.push(frame)

    async def events(self) -> AsyncIterator[EngineEvent]:
        while True:
            yield await self.queue.get()

    async def interrupt(self, message_id: str, heard_text: str) -> None:
        # History keeps only what the user heard (architecture.md 4.2). The
        # reply may still be running (its entry is written when it ends) or
        # already finished while its audio plays; handle both.
        self.heard[message_id] = heard_text
        if self.reply and not self.reply.done() and self.reply_message_id == message_id:
            self.reply.cancel()
        for turn in reversed(self.history):
            if turn["role"] == "assistant" and turn.get("id") == message_id:
                turn["content"] = heard_text
                break

    async def send_tool_response(self, call_id: str, payload: str) -> None:
        log.info("tool responses are not used by the cascade engine yet")

    async def say_filler(self, text: str) -> None:
        speech = await self.tts.synthesize(text)
        self._emit_speech(_new_id("f"), speech.pcm, speech.words, 0.0)

    async def close(self) -> None:
        self.stt.close()
        for task in (self.worker, self.reply):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (self.worker, self.reply) if t), return_exceptions=True)

    # Internals

    def _on_transcript(self, text: str, final: bool) -> None:
        text = text.strip()
        if not text:
            return
        if self.user_message_id is None:
            self.user_message_id = _new_id("u")
            self._emit(StateChanged("listening"))
        self._emit(UserTranscript(self.user_message_id, text, final))
        if final:
            self.user_message_id = None
            self.user_turns.put_nowait(text)

    async def _serve_turns(self) -> None:
        while True:
            text = await self.user_turns.get()
            self.reply = asyncio.create_task(self._answer(text))
            try:
                await self.reply
            except asyncio.CancelledError:
                if asyncio.current_task() and asyncio.current_task().cancelling():
                    raise
            except Exception:
                log.exception("reply failed")
                self._emit(EngineProblem("internal", "Something went wrong with that answer. Please try again."))

    def _on_provider(self, provider: LlmProvider) -> None:
        if self.planner_reported != provider.id:
            self.planner_reported = provider.id
            self._emit(ModelInUse(role="planner", provider=provider.id, model=provider.model, backup=not provider.primary))

    def _emit_speech(self, message_id: str, pcm: bytes, words: list[tuple[str, float, float]], offset_s: float) -> None:
        step = CHUNK_SAMPLES * 2
        for start in range(0, len(pcm), step):
            self._emit(AssistantAudio(message_id, pcm[start : start + step]))
        for word, start_s, end_s in words:
            self._emit(AssistantWord(message_id, word, offset_s + start_s, offset_s + end_s))

    async def _answer(self, user_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history = self.history[-2 * MAX_HISTORY_TURNS :]
        message_id = _new_id("a")
        self.reply_message_id = message_id
        self._emit(StateChanged("thinking"))
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": t["role"], "content": t["content"]} for t in self.history
        ]

        spoken: list[str] = []
        offset = 0.0
        pending = ""

        async def speak(sentence: str) -> None:
            nonlocal offset
            sentence = _speakable(sentence)
            if not sentence:
                return
            speech = await self.tts.synthesize(sentence)
            if not spoken:
                self._emit(StateChanged("assistant_speaking"))
            spoken.append(sentence)
            self._emit_speech(message_id, speech.pcm, speech.words, offset)
            offset += speech.duration_s

        entry = {"role": "assistant", "content": "", "id": message_id}
        try:
            async for piece in self.llm.stream(messages, self._on_provider):
                pending += piece
                parts = SENTENCE_END.split(pending)
                for sentence in parts[:-1]:
                    await speak(sentence)
                pending = parts[-1]
                if len(pending) > 160 and "," in pending:  # long clause: speak up to the last comma
                    head, _, pending = pending.rpartition(",")
                    await speak(head + ",")
            await speak(pending)
        except LlmUnavailable as error:
            self._emit(EngineProblem("internal", str(error)))
        except Exception:
            log.exception("speech synthesis failed")
            self._emit(EngineProblem("voice_engine_offline", "The voice engine isn't reachable. Please try again."))
        finally:
            planned = " ".join(spoken)
            entry["content"] = self.heard.pop(message_id, planned)
            if entry["content"]:
                self.history.append(entry)
            self._emit(TurnEnded(message_id, planned))
