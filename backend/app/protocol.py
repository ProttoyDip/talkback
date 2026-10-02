"""Session protocol messages (architecture.md, section 3).

Every JSON message is validated here. Unknown types and unknown fields are
rejected (SECURITY.md section 5).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# Audio format (architecture.md 2.1 and 3).
CLIENT_SAMPLE_RATE = 16_000
SERVER_SAMPLE_RATE = 22_050
FRAME_MS = 20
FRAME_BYTES = CLIENT_SAMPLE_RATE * FRAME_MS // 1000 * 2  # PCM16 mono: 640 bytes
MAX_MESSAGE_BYTES = 64 * 1024  # SECURITY.md T7

ConversationState = Literal[
    "idle",
    "listening",
    "assistant_speaking",
    "overlap",
    "interrupted",
    "thinking",
    "tool",
    "confirm",
    "muted",
    "offline",
]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Client -> server


class SessionStart(Message):
    type: Literal["session.start"]
    client_sample_rate: Literal[16_000]


class PlaybackPosition(Message):
    type: Literal["playback.position"]
    seq: int = Field(ge=0)
    samples_played: int = Field(ge=0)


class ControlMute(Message):
    type: Literal["control.mute"]
    muted: bool


class ToolConfirm(Message):
    type: Literal["tool.confirm"]
    call_id: str = Field(min_length=1, max_length=64)
    approved: bool


ClientMessage = Annotated[
    SessionStart | PlaybackPosition | ControlMute | ToolConfirm,
    Field(discriminator="type"),
]
client_message = TypeAdapter(ClientMessage)


# Server -> client


class StateEvent(Message):
    type: Literal["state"] = "state"
    state: ConversationState


class AudioChunk(Message):
    type: Literal["audio.chunk"] = "audio.chunk"
    seq: int = Field(ge=0)
    samples: int = Field(ge=0)


class AudioFlush(Message):
    type: Literal["audio.flush"] = "audio.flush"
    reason: Literal["interrupted", "stopped"]


class TranscriptDelta(Message):
    type: Literal["transcript.delta"] = "transcript.delta"
    speaker: Literal["user", "assistant"]
    text: str
    final: bool


class TranscriptTrim(Message):
    type: Literal["transcript.trim"] = "transcript.trim"
    message_id: str
    heard_text: str


class ToolStatus(Message):
    type: Literal["tool.status"] = "tool.status"
    call_id: str
    name: str
    status: Literal["running", "done", "failed"]


class ToolConfirmRequest(Message):
    type: Literal["tool.confirm_request"] = "tool.confirm_request"
    call_id: str
    summary: str


class MemorySaved(Message):
    type: Literal["memory.saved"] = "memory.saved"
    id: str
    text: str


class Metrics(Message):
    type: Literal["metrics"] = "metrics"
    latency_ms: float = Field(ge=0)


ServerMessage = (
    StateEvent
    | AudioChunk
    | AudioFlush
    | TranscriptDelta
    | TranscriptTrim
    | ToolStatus
    | ToolConfirmRequest
    | MemorySaved
    | Metrics
)
