"""WebSocket session gateway: /ws/session (architecture.md 2.2 and 3).

Checks before accepting (SECURITY.md T7, T8): Origin allowlist, a valid
session token, one live connection per token, and a per-IP limit.
After accepting: every message is size-limited and validated, sessions close
after 2 minutes without messages, and no session lasts longer than 30 minutes.

The voice model is not connected yet; audio frames are validated and counted.
"""

import asyncio
import logging
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from .config import Settings, get_settings
from .protocol import (
    FRAME_BYTES,
    MAX_MESSAGE_BYTES,
    ControlMute,
    PlaybackPosition,
    ServerMessage,
    SessionEnd,
    SessionStart,
    StateEvent,
    ToolConfirm,
    client_message,
)
from .tokens import verify_token

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


class Session:
    def __init__(self, websocket: WebSocket, session_id: str) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.started = False
        self.muted = False
        self.frames_received = 0
        self.last_playback: PlaybackPosition | None = None

    async def send(self, message: ServerMessage) -> None:
        # Optional fields that are None are left out; clients treat missing as null.
        await self.websocket.send_text(message.model_dump_json(exclude_none=True))

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
            case ControlMute(muted=muted):
                self.require_started()
                self.muted = muted
                await self.send(StateEvent(state="muted" if muted else "idle"))
            case PlaybackPosition():
                self.require_started()
                self.last_playback = message  # used for trimming in a later step
            case ToolConfirm():
                self.require_started()
                # No tool can ask for confirmation yet, so there is nothing to
                # approve. A confirmation never applies to a future call (T5).
                log.info("tool.confirm with no pending call", extra={"session_id": self.session_id})

    async def on_audio(self, data: bytes) -> None:
        self.require_started()
        if len(data) != FRAME_BYTES:
            raise ProtocolError(CLOSE_UNSUPPORTED_DATA, f"audio frames must be {FRAME_BYTES} bytes")
        if self.muted:
            return  # muted audio is dropped, never processed
        self.frames_received += 1

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
    websocket: WebSocket, settings: Annotated[Settings, Depends(get_settings)]
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
    session = Session(websocket, claims.session_id)
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
        registry.remove(claims.session_id, ip)
        log.info(
            "session ended",
            extra={"session_id": claims.session_id, "event": f"frames={session.frames_received}"},
        )
