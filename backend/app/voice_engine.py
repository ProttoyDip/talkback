"""The voice engine interface (architecture.md 2.2, plan.md X1/X7/X12).

The session gateway talks only to this interface, so the engines are
interchangeable:
- "cascade": NVIDIA Parakeet speech-to-text -> Nemotron -> NVIDIA Magpie
  text-to-speech (plan B, cascade_engine.py)
- "fake": replays the demo fixture (X1)
- "voicechat": NVIDIA NemotronLabs VoiceChat on Nebius (X7)
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from .protocol import ConversationState, ModelRole, ProviderId, ServerMessage, ToolConfirm, ToolName


@dataclass(frozen=True)
class SessionContext:
    session_id: str


# Engine events. Times are seconds from the start of that message's audio.


@dataclass(frozen=True)
class AssistantAudio:
    """PCM16 mono, 22.05 kHz. Chunks of one message arrive in order."""

    message_id: str
    pcm: bytes


@dataclass(frozen=True)
class AssistantWord:
    message_id: str
    word: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class UserTranscript:
    """Full text so far for this user turn."""

    message_id: str
    text: str
    final: bool


@dataclass(frozen=True)
class StateChanged:
    state: ConversationState
    tool: ToolName | None = None  # with state "tool": "CHECKING WEATHER"


@dataclass(frozen=True)
class ToolCallRequested:
    message_id: str
    raw: str  # contents of <TOOLCALL>...</TOOLCALL>


@dataclass(frozen=True)
class TurnEnded:
    message_id: str
    # The full text the assistant planned to say in this turn.
    text: str
    # False for short fillers ("Let me check that"): the turn goes on, so the
    # gateway must not return to idle when this audio ends.
    ends_turn: bool = True


@dataclass(frozen=True)
class ProtocolEvent:
    """A protocol message produced inside the engine (tool chips,
    confirmation requests, memory saved). The gateway sends it unchanged."""

    message: ServerMessage


@dataclass(frozen=True)
class ModelInUse:
    role: ModelRole
    provider: ProviderId
    model: str
    backup: bool


@dataclass(frozen=True)
class EngineProblem:
    """Shown to the user; the session stays open."""

    code: str  # an ErrorCode from protocol.py
    message: str


EngineEvent = (
    AssistantAudio
    | AssistantWord
    | UserTranscript
    | StateChanged
    | ToolCallRequested
    | TurnEnded
    | ModelInUse
    | EngineProblem
    | ProtocolEvent
)


class VoiceEngine(Protocol):
    async def start(self, context: SessionContext) -> None: ...

    async def send_audio(self, frame: bytes) -> None:
        """One 20 ms PCM16 frame at 16 kHz."""

    def events(self) -> AsyncIterator[EngineEvent]: ...

    async def interrupt(self, message_id: str, heard_text: str) -> None:
        """Stop speaking now. History keeps only heard_text for message_id."""

    async def send_tool_response(self, call_id: str, payload: str) -> None: ...

    async def say_filler(self, text: str) -> None: ...

    async def confirm_tool(self, message: ToolConfirm) -> None:
        """The user's answer to a tool.confirm_request."""

    async def close(self) -> None: ...
