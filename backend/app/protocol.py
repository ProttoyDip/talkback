"""Session protocol messages (architecture.md, section 3).

Every JSON message is validated here. Unknown types and unknown fields are
rejected (SECURITY.md section 5).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter

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


ToolName = Literal["weather", "web_search", "memory_read", "memory_write", "memory_delete", "skill_run"]

# Ids are short opaque strings created by the server.
Id = Annotated[str, Field(min_length=1, max_length=64)]


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
    # Set with state "tool", so the UI can say "CHECKING WEATHER".
    tool: ToolName | None = None


class AudioChunk(Message):
    type: Literal["audio.chunk"] = "audio.chunk"
    seq: int = Field(ge=0)
    samples: int = Field(ge=0)


class AudioFlush(Message):
    type: Literal["audio.flush"] = "audio.flush"
    reason: Literal["interrupted", "stopped"]


class TranscriptDelta(Message):
    """Live captions. Deltas with the same message_id append to one turn."""

    type: Literal["transcript.delta"] = "transcript.delta"
    message_id: Id
    speaker: Literal["user", "assistant"]
    text: str
    final: bool
    # A short user sound ("mm-hm") that did not interrupt. The UI shows it
    # inside the assistant turn that was playing (design.md 5.2).
    backchannel: bool = False


class TranscriptTrim(Message):
    """After an interruption: the assistant message keeps only heard_text in
    its history. unheard_text is what it had planned to say next; the UI shows
    it faded and struck through (design.md 5.2). It is never sent back to the
    model."""

    type: Literal["transcript.trim"] = "transcript.trim"
    message_id: Id
    heard_text: str
    unheard_text: str = ""


class Source(Message):
    title: str = Field(max_length=300)
    url: HttpUrl


class ToolStatus(Message):
    type: Literal["tool.status"] = "tool.status"
    call_id: Id
    # The assistant turn the tool chip belongs to.
    message_id: Id
    name: ToolName
    status: Literal["running", "done", "failed"]
    # web_search results, shown as the expandable source list.
    sources: list[Source] = Field(default_factory=list, max_length=10)


class ToolConfirmRequest(Message):
    type: Literal["tool.confirm_request"] = "tool.confirm_request"
    call_id: Id
    summary: str = Field(max_length=300)
    # The request expires after 30 seconds (SECURITY.md T5).
    expires_in_ms: int = Field(default=30_000, gt=0)


class MemorySaved(Message):
    type: Literal["memory.saved"] = "memory.saved"
    id: Id
    text: str


class Metrics(Message):
    type: Literal["metrics"] = "metrics"
    latency_ms: float = Field(ge=0)


ErrorCode = Literal[
    "voice_engine_offline",  # design.md 5.6: "The voice engine isn't reachable"
    "tool_failed",
    "rate_limited",
    "internal",
]


class ErrorEvent(Message):
    """A problem the user should see. The session stays open."""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str = Field(max_length=300)  # plain words, shown to the user
    retry_in_ms: int | None = Field(default=None, ge=0)


class SessionEnd(Message):
    """Sent just before the server closes the WebSocket."""

    type: Literal["session.end"] = "session.end"
    reason: Literal["idle", "time_limit", "server_shutdown", "protocol_error"]


ServerMessage = Annotated[
    StateEvent
    | AudioChunk
    | AudioFlush
    | TranscriptDelta
    | TranscriptTrim
    | ToolStatus
    | ToolConfirmRequest
    | MemorySaved
    | Metrics
    | ErrorEvent
    | SessionEnd,
    Field(discriminator="type"),
]
server_message = TypeAdapter(ServerMessage)


# REST API (architecture.md 3.2). All routes need the session token in an
# "Authorization: Bearer <token>" header.


class Rest(BaseModel):
    model_config = ConfigDict(extra="forbid")


MemoryKind = Literal["preference", "fact", "reminder"]


class MemoryItem(Rest):
    id: Id
    text: str = Field(max_length=500)
    kind: MemoryKind
    utterance: str = Field(max_length=1000)  # the user's exact words
    created_at: str  # ISO 8601, UTC


class MemoryList(Rest):
    items: list[MemoryItem]


class MemoryUpdate(Rest):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    kind: MemoryKind | None = None


class SkillItem(Rest):
    id: Id
    name: str
    triggers: list[str]
    allowed_tools: list[ToolName]


class SkillList(Rest):
    items: list[SkillItem]


class SkillRunAccepted(Rest):
    """The run happens inside the live session; progress arrives as events."""

    run_id: Id


class ToolSetting(Rest):
    enabled: bool
    description: str  # what the tool can access, shown in Settings


class SettingsView(Rest):
    tools: dict[ToolName, ToolSetting]
    save_recordings: bool  # off by default (FR-18)
    transcripts_in_logs: bool  # off by default


class SettingsUpdate(Rest):
    tools: dict[ToolName, bool] | None = None
    save_recordings: bool | None = None
    transcripts_in_logs: bool | None = None
