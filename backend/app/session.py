"""WebSocket session gateway: /ws/session (architecture.md 2.2 and 3).

Checks before accepting (SECURITY.md T7, T8): Origin allowlist, a valid
session token, one live connection per token, and a per-IP limit.
After accepting: every message is size-limited and validated, sessions close
after 2 minutes without messages, and no session lasts longer than 30 minutes.

Audio frames go to the voice engine chosen by VOICE_ENGINE (engines.py).
Engine events become protocol messages here: audio chunks are numbered,
captions are paced to when each word plays, and the state returns to idle
only when the queued audio has finished playing.
"""

import asyncio
import logging
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from .config import Settings, get_settings
from .engines import EngineChoice, EngineFactory, get_engine_factory
from .protocol import (
    FRAME_BYTES,
    MAX_MESSAGE_BYTES,
    SERVER_SAMPLE_RATE,
    AudioChunk,
    ControlMute,
    ControlStop,
    ErrorEvent,
    AudioFlush,
    ModelActive,
    PlaybackPosition,
    ServerMessage,
    SessionEnd,
    SessionStart,
    StateEvent,
    ToolConfirm,
    TranscriptDelta,
    TranscriptTrim,
    client_message,
)
from .stores import prefs_store
from .tokens import verify_token
from .turn_taking import BargeInDecider, EnergyVad, heard_split, is_backchannel
from .voice_engine import (
    AssistantAudio,
    AssistantWord,
    EngineEvent,
    EngineProblem,
    ModelInUse,
    ProtocolEvent,
    SessionContext,
    StateChanged,
    ToolCallRequested,
    TurnEnded,
    UserTranscript,
    VoiceEngine,
)

log = logging.getLogger("talkback.session")
router = APIRouter()

MAX_CONNECTIONS_PER_IP = 3
IDLE_TIMEOUT_SECONDS = 2 * 60
MAX_SESSION_SECONDS = 30 * 60

# WebSocket close codes (RFC 6455).
CLOSE_NORMAL = 1000
CLOSE_UNSUPPORTED_DATA = 1003
CLOSE_POLICY_VIOLATION = 1008
CLOSE_TOO_BIG = 1009
CLOSE_TRY_AGAIN_LATER = 1013


class ProtocolError(Exception):
    def __init__(self, code: int, reason: str, end_reason: str = "protocol_error") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        # Value for the session.end event sent before closing.
        self.end_reason = end_reason


class Registry:
    """Live connections, by session id and by client IP."""

    def __init__(self) -> None:
        self.sessions: set[str] = set()
        self.live: dict[str, 'Session'] = {}  # for REST calls that act on a running session
        self.per_ip: Counter[str] = Counter()

    def add(self, session_id: str, ip: str) -> None:
        self.sessions.add(session_id)
        self.per_ip[ip] += 1

    def remove(self, session_id: str, ip: str) -> None:
        self.sessions.discard(session_id)
        self.per_ip[ip] -= 1
        if self.per_ip[ip] <= 0:
            del self.per_ip[ip]


registry = Registry()


def loop_time() -> float:
    return asyncio.get_running_loop().time()


ERROR_CODES = {"voice_engine_offline", "tool_failed", "rate_limited", "internal"}
_FINISH = object()  # end-of-turn marker in a caption queue
_FINISH_QUIET = object()  # end of a filler: close its captions, keep the state


class Session:
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        settings: Settings | None = None,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.settings = settings
        self.engine_factory = engine_factory
        self.started = False
        self.muted = False
        self.frames_received = 0
        self.last_playback: PlaybackPosition | None = None

        self.send_lock = asyncio.Lock()
        self.engine: VoiceEngine | None = None
        self.engine_choice: EngineChoice | None = None
        self.tasks: set[asyncio.Task] = set()
        # Assistant audio bookkeeping (X2 uses chunks to map positions to words).
        self.audio_seq = 0
        self.play_until = 0.0  # loop time when all sent assistant audio has played
        self.message_start: dict[str, float] = {}
        self.message_samples: dict[str, int] = {}
        self.chunks: dict[int, tuple[str, int]] = {}  # seq -> (message_id, sample offset)
        self.captions: dict[str, asyncio.Queue] = {}
        # Bumped when a new turn starts, so a finished turn does not reset the state.
        self.turn_epoch = 0
        # Turn-taking (X2): barge-in and trimming at the playback position.
        self.vad = EnergyVad()
        self.decider = BargeInDecider()
        if settings is not None:
            # The user's Interruptions setting applies when a session starts.
            self.decider = BargeInDecider.for_sensitivity(prefs_store(settings).load().interrupt_sensitivity)
        self.interim_user_text = ""
        self.overlapping = False
        self.words: dict[str, list[tuple[str, float, float]]] = {}
        self.message_order: list[str] = []
        self.message_base: dict[str, int] = {}  # played-sample position where a message starts
        self.total_sent_samples = 0
        self.dropped_samples = 0  # sent but never played, because of interruptions
        self.dropped: set[str] = set()
        self.caption_tasks: dict[str, asyncio.Task] = {}

    async def send(self, message: ServerMessage) -> None:
        # Optional fields that are None are left out; clients treat missing as null.
        async with self.send_lock:
            await self.websocket.send_text(message.model_dump_json(exclude_none=True))

    async def send_audio_chunk(self, seq: int, pcm: bytes) -> None:
        # Header and audio must stay together, so both go under one lock.
        async with self.send_lock:
            await self.websocket.send_text(
                AudioChunk(seq=seq, samples=len(pcm) // 2).model_dump_json(exclude_none=True)
            )
            await self.websocket.send_bytes(pcm)

    def spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # Voice engine bridge

    async def start_engine(self) -> None:
        if self.engine_factory is None or self.settings is None:
            return
        choice = self.engine_factory(self.settings)
        self.engine_choice = choice
        if choice.problem:
            await self.send(ErrorEvent(code="voice_engine_offline", message=choice.problem))
        if choice.engine is None:
            return
        self.engine = choice.engine
        # Lets the engine ignore "mm-hm" while TalkBack is still speaking.
        self.engine.playback_active = lambda: loop_time() < self.play_until  # type: ignore[attr-defined]
        await self.engine.start(SessionContext(self.session_id))
        self.spawn(self.pump_engine())

    async def pump_engine(self) -> None:
        assert self.engine is not None
        async for event in self.engine.events():
            try:
                await self.on_engine_event(event)
            except Exception:
                log.exception("engine event failed", extra={"session_id": self.session_id})

    async def on_engine_event(self, event: EngineEvent) -> None:
        now = asyncio.get_running_loop().time()
        match event:
            case AssistantAudio(message_id=message_id, pcm=pcm):
                if message_id in self.dropped:
                    return  # the user interrupted this message
                if message_id not in self.message_start:
                    self.message_start[message_id] = max(now, self.play_until)
                    self.message_samples[message_id] = 0
                    self.message_order.append(message_id)
                    self.message_base[message_id] = self.total_sent_samples - self.dropped_samples
                seq = self.audio_seq
                self.audio_seq += 1
                self.chunks[seq] = (message_id, self.message_samples[message_id])
                samples = len(pcm) // 2
                self.message_samples[message_id] += samples
                self.total_sent_samples += samples
                self.play_until = max(now, self.play_until) + samples / SERVER_SAMPLE_RATE
                await self.send_audio_chunk(seq, pcm)
            case AssistantWord(message_id=message_id, word=word, start_s=start_s, end_s=end_s):
                if message_id in self.dropped:
                    return
                self.words.setdefault(message_id, []).append((word, start_s, end_s))
                self.caption_queue(message_id).put_nowait(event)
            case TurnEnded(message_id=message_id, ends_turn=ends_turn):
                if message_id in self.dropped:
                    return
                self.caption_queue(message_id).put_nowait(_FINISH if ends_turn else _FINISH_QUIET)
            case UserTranscript(message_id=message_id, text=text, final=final):
                self.interim_user_text = "" if final else text
                # A short sound over TalkBack that did not interrupt it.
                reaction = final and is_backchannel(text) and loop_time() < self.play_until
                await self.send(
                    TranscriptDelta(message_id=message_id, speaker="user", text=text, final=final, backchannel=reaction)
                )
            case StateChanged(state=state, tool=tool):
                if state in ("listening", "thinking", "tool"):
                    self.turn_epoch += 1
                await self.send(StateEvent(state=state, tool=tool))
            case ProtocolEvent(message=message):
                await self.send(message)
            case ModelInUse(role=role, provider=provider, model=model, backup=backup):
                await self.send(ModelActive(role=role, provider=provider, model=model, backup=backup))
            case EngineProblem(code=code, message=message):
                await self.send(ErrorEvent(code=code if code in ERROR_CODES else "internal", message=message[:300]))
            case ToolCallRequested():
                # Engines with their own tool channel (VoiceChat, X7) emit this;
                # the cascade engine runs tools itself.
                log.info("tool call event not handled by this gateway", extra={"session_id": self.session_id})

    def caption_queue(self, message_id: str) -> asyncio.Queue:
        if message_id not in self.captions:
            self.captions[message_id] = asyncio.Queue()
            task = asyncio.create_task(self.send_captions(message_id))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            self.caption_tasks[message_id] = task
        return self.captions[message_id]

    async def send_captions(self, message_id: str) -> None:
        """Send each word when it starts playing, then close the turn when its audio ends."""
        loop = asyncio.get_running_loop()
        queue = self.captions[message_id]
        first = True
        try:
            while True:
                item = await queue.get()
                start = self.message_start.get(message_id, loop.time())
                if item is _FINISH or item is _FINISH_QUIET:
                    epoch = self.turn_epoch
                    await asyncio.sleep(max(0.0, self.play_until - loop.time()))
                    await self.send(TranscriptDelta(message_id=message_id, speaker="assistant", text="", final=True))
                    if item is _FINISH and epoch == self.turn_epoch and loop.time() >= self.play_until:
                        await self.send(StateEvent(state="idle"))
                    return
                await asyncio.sleep(max(0.0, start + item.start_s - loop.time()))
                text = item.word if first else f" {item.word}"
                first = False
                await self.send(TranscriptDelta(message_id=message_id, speaker="assistant", text=text, final=False))
        finally:
            self.captions.pop(message_id, None)

    # Turn-taking (X2)

    async def watch_for_barge_in(self, frame: bytes) -> None:
        """Runs on every microphone frame: speech over TalkBack is either a
        backchannel (ignored) or an interruption (architecture.md 4)."""
        state = self.vad.process(frame)
        playing = loop_time() < self.play_until
        if state.is_speech and playing:
            verdict = self.decider.update(state.speech_ms, self.interim_user_text)
            if verdict == "interrupt":
                await self.interrupt_assistant()
            elif verdict == "overlap" and not self.overlapping:
                self.overlapping = True
                await self.send(StateEvent(state="overlap"))
        elif self.overlapping and not state.is_speech:
            self.overlapping = False
            if playing:
                await self.send(StateEvent(state="assistant_speaking"))

    async def interrupt_assistant(self, reason: str = "interrupted") -> None:
        """Stop playback now and keep only the words the user heard.

        reason "interrupted": the user talked over TalkBack (barge-in).
        reason "stopped": the user pressed Stop or Esc; the state returns to idle.
        """
        played_total = self.last_playback.samples_played if self.last_playback else 0
        pending = [
            m for m in self.message_order
            if m not in self.dropped and self.message_base[m] + self.message_samples[m] > played_total
        ]
        if not pending:
            if reason == "stopped":
                await self.stop_before_audio()
            return
        current = pending[0]
        played_s = max(0, played_total - self.message_base[current]) / SERVER_SAMPLE_RATE
        heard, unheard = heard_split(self.words.get(current, []), played_s)
        for message_id in pending:
            self.dropped.add(message_id)
            if task := self.caption_tasks.pop(message_id, None):
                task.cancel()
            self.captions.pop(message_id, None)
        self.dropped_samples += max(0, self.total_sent_samples - played_total)
        self.play_until = loop_time()
        self.overlapping = False
        self.turn_epoch += 1
        await self.send(AudioFlush(reason="stopped" if reason == "stopped" else "interrupted"))
        await self.send(StateEvent(state="idle" if reason == "stopped" else "interrupted"))
        await self.send(TranscriptDelta(message_id=current, speaker="assistant", text="", final=True))
        await self.send(TranscriptTrim(message_id=current, heard_text=heard, unheard_text=unheard))
        if self.engine is not None:
            await self.engine.interrupt(current, heard)

    async def stop_before_audio(self) -> None:
        """Stop pressed while TalkBack is still thinking: cancel the reply."""
        reply_id = getattr(self.engine, "reply_message_id", None)
        reply = getattr(self.engine, "reply", None)
        if self.engine is not None and reply_id and reply is not None and not reply.done():
            self.dropped.add(reply_id)
            await self.engine.interrupt(reply_id, "")
        self.turn_epoch += 1
        await self.send(StateEvent(state="idle"))

    async def close(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.engine is not None:
            await self.engine.close()
        if self.engine_choice and self.engine_choice.http is not None:
            await self.engine_choice.http.aclose()

    def require_started(self) -> None:
        if not self.started:
            raise ProtocolError(CLOSE_POLICY_VIOLATION, "send session.start first")

    async def on_text(self, text: str) -> None:
        if len(text.encode()) > MAX_MESSAGE_BYTES:
            raise ProtocolError(CLOSE_TOO_BIG, "message too large")
        try:
            message = client_message.validate_json(text)
        except ValidationError:
            raise ProtocolError(CLOSE_POLICY_VIOLATION, "invalid message") from None

        match message:
            case SessionStart():
                if self.started:
                    raise ProtocolError(CLOSE_POLICY_VIOLATION, "session already started")
                self.started = True
                await self.send(StateEvent(state="idle"))
                await self.start_engine()
            case ControlMute(muted=muted):
                self.require_started()
                self.muted = muted
                await self.send(StateEvent(state="muted" if muted else "idle"))
            case PlaybackPosition():
                self.require_started()
                self.last_playback = message  # used for trimming in a later step
            case ControlStop():
                self.require_started()
                await self.interrupt_assistant("stopped")
            case ToolConfirm():
                self.require_started()
                # Only a pending request can be answered; a confirmation never
                # applies to a future call (SECURITY.md T5).
                if self.engine is not None:
                    await self.engine.confirm_tool(message)
                else:
                    log.info("tool.confirm with no pending call", extra={"session_id": self.session_id})

    async def on_audio(self, data: bytes) -> None:
        self.require_started()
        if len(data) != FRAME_BYTES:
            raise ProtocolError(CLOSE_UNSUPPORTED_DATA, f"audio frames must be {FRAME_BYTES} bytes")
        if self.muted:
            return  # muted audio is dropped, never processed
        self.frames_received += 1
        if self.engine is not None:
            await self.watch_for_barge_in(data)
            await self.engine.send_audio(data)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MAX_SESSION_SECONDS
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise ProtocolError(CLOSE_NORMAL, "session time limit reached", "time_limit")
            try:
                event = await asyncio.wait_for(
                    self.websocket.receive(), timeout=min(IDLE_TIMEOUT_SECONDS, remaining)
                )
            except TimeoutError:
                raise ProtocolError(CLOSE_NORMAL, "session closed after inactivity", "idle") from None

            if event["type"] == "websocket.disconnect":
                return
            if (data := event.get("bytes")) is not None:
                await self.on_audio(data)
            elif (text := event.get("text")) is not None:
                await self.on_text(text)


async def reject(websocket: WebSocket, code: int, reason: str, ip: str) -> None:
    log.warning("connection rejected", extra={"event": reason, "code": code, "client": ip})
    await websocket.close(code=code, reason=reason)


@router.websocket("/ws/session")
async def session_endpoint(
    websocket: WebSocket,
    settings: Annotated[Settings, Depends(get_settings)],
    engine_factory: Annotated[EngineFactory, Depends(get_engine_factory)],
) -> None:
    ip = websocket.client.host if websocket.client else "unknown"

    if websocket.headers.get("origin") not in settings.origins:
        return await reject(websocket, CLOSE_POLICY_VIOLATION, "origin not allowed", ip)

    claims = verify_token(settings.signing_key(), websocket.query_params.get("token", ""))
    if claims is None:
        return await reject(websocket, CLOSE_POLICY_VIOLATION, "invalid or expired token", ip)
    if claims.session_id in registry.sessions:
        return await reject(websocket, CLOSE_POLICY_VIOLATION, "token already in use", ip)
    if registry.per_ip[ip] >= MAX_CONNECTIONS_PER_IP:
        return await reject(websocket, CLOSE_TRY_AGAIN_LATER, "too many connections", ip)

    await websocket.accept()
    registry.add(claims.session_id, ip)
    session = Session(websocket, claims.session_id, settings, engine_factory)
    registry.live[claims.session_id] = session
    log.info("session opened", extra={"session_id": claims.session_id})
    try:
        await session.run()
    except ProtocolError as error:
        log.info(
            "session closed",
            extra={"session_id": claims.session_id, "event": error.reason, "code": error.code},
        )
        if websocket.client_state == WebSocketState.CONNECTED:
            await session.send(SessionEnd(reason=error.end_reason))
            await websocket.close(code=error.code, reason=error.reason)
    finally:
        # Free the connection slot first: closing the engine can take a moment,
        # and the limits (one per token, three per IP) must not wait for it.
        registry.remove(claims.session_id, ip)
        registry.live.pop(claims.session_id, None)
        await session.close()
        log.info(
            "session ended",
            extra={"session_id": claims.session_id, "event": f"frames={session.frames_received}"},
        )
