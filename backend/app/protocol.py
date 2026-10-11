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


ToolName = Literal[
    "weather", "web_search", "memory_read", "memory_write", "memory_delete", "memory_suggest", "skill_run",
    "task_list", "task_add", "task_update", "task_delete",
    "calendar_list", "calendar_add", "calendar_update", "calendar_delete",
    "reminder_set", "reminder_update", "day_plan_propose", "day_plan_apply",
]

# Ids are short opaque strings created by the server.
Id = Annotated[str, Field(min_length=1, max_length=64)]

# Model providers (plan.md section 8). Keys and base URLs never leave the server.
ProviderId = Literal[
    "nebius",
    "nvidia",  # NVIDIA API catalog (build.nvidia.com): hosted speech models for plan B
    "openrouter",
    "agentrouter",
    "nararouter",
    "experimentallab",
    "tavily",
    "perplexity",
]
ModelRole = Literal["voice", "planner", "search"]


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


class ControlStop(Message):
    """The user asks TalkBack to stop talking now (Esc or the Stop button)."""

    type: Literal["control.stop"]


class ToolConfirm(Message):
    type: Literal["tool.confirm"]
    call_id: str = Field(min_length=1, max_length=64)
    approved: bool


class SessionResume(Message):
    """The answer to session.resumable: continue the earlier conversation, or start fresh."""

    type: Literal["session.resume"]
    state_id: Id
    accept: bool


class TextInput(Message):
    """A typed turn: the same as speaking it (works while muted)."""

    type: Literal["text.input"]
    text: str = Field(min_length=1, max_length=2000)


ClientMessage = Annotated[
    SessionStart | PlaybackPosition | ControlMute | ControlStop | ToolConfirm | TextInput | SessionResume,
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
    # The user typed this turn instead of saying it (text.input).
    typed: bool = False


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


ToolStatusReason = Literal[
    "user_declined", "timeout", "superseded", "stopped", "interrupted", "session_closed", "already_done",
]


class ToolStatus(Message):
    type: Literal["tool.status"] = "tool.status"
    call_id: Id
    # The assistant turn the tool chip belongs to.
    message_id: Id
    name: ToolName
    # declined: the user said no or did not answer in time; cancelled: the
    # call was stopped before it ran (interruption, Stop, a newer request);
    # expired: a confirmation request ran out. Any final status for a call_id
    # closes its confirmation card.
    status: Literal["running", "done", "failed", "declined", "cancelled", "expired"]
    reason: ToolStatusReason | None = None
    # The change this call made (GET /api/actions), and whether it can be undone.
    action_id: Id | None = None
    undoable: bool = False
    # web_search results, shown as the expandable source list.
    sources: list[Source] = Field(default_factory=list, max_length=10)


class ToolConfirmRequest(Message):
    type: Literal["tool.confirm_request"] = "tool.confirm_request"
    call_id: Id
    summary: str = Field(max_length=300)
    # The assistant turn and tool the request belongs to.
    message_id: Id | None = None
    name: ToolName | None = None
    # More lines for the card when one summary is not enough (a day plan).
    details: list[str] = Field(default_factory=list, max_length=10)
    # The request expires after 30 seconds (SECURITY.md T5).
    expires_in_ms: int = Field(default=30_000, gt=0)


class MemorySaved(Message):
    type: Literal["memory.saved"] = "memory.saved"
    id: Id
    text: str
    # A suggestion waits for the user's OK; it is not used until confirmed.
    status: MemoryStatus = "confirmed"
    # A correction replaces an older memory ("Remembered: tea, instead of coffee").
    replaced_id: Id | None = None
    replaced_text: str | None = Field(default=None, max_length=500)
    # Undo goes through POST /api/actions/{action_id}/undo.
    action_id: Id | None = None


DataKind = Literal["memories", "actions", "tasks", "calendar", "reminders", "skills"]


class DataChanged(Message):
    """Stored data changed outside the panel (by voice): open panels reload."""

    type: Literal["data.changed"] = "data.changed"
    kinds: list[DataKind] = Field(min_length=1, max_length=8)


class PlanItem(Message):
    """One proposed change in a day plan: a block for a task in free time."""

    index: int = Field(ge=0, le=20)
    op: Literal["create_block"] = "create_block"
    title: str = Field(max_length=200)
    starts_at: str
    ends_at: str
    task_id: Id | None = None
    reason: str = Field(max_length=120)


class PlanProposed(Message):
    """A day plan for the user to accept (all or some) or decline. Nothing
    changes until they accept it (plan P6)."""

    type: Literal["plan.proposed"] = "plan.proposed"
    proposal_id: Id
    message_id: Id
    date: str  # local date, "2026-10-12"
    items: list[PlanItem] = Field(max_length=20)
    expires_at: str


class PlanUpdated(Message):
    type: Literal["plan.updated"] = "plan.updated"
    proposal_id: Id
    status: Literal["accepted", "partially_applied", "rejected", "superseded", "expired"]
    applied: list[int] = Field(default_factory=list, max_length=20)
    action_id: Id | None = None


class PlanApply(Message):
    """POST /api/plans/{id}/apply: which items to apply (all when missing)."""

    items: list[int] | None = Field(default=None, max_length=20)


class SessionResumable(Message):
    """An unfinished conversation from earlier (plan P7). Facts only: the
    user's goal in their own words, what was done, what is still open.
    Nothing open runs again without being asked again."""

    type: Literal["session.resumable"] = "session.resumable"
    state_id: Id
    goal: str = Field(max_length=200)
    decisions: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=10)
    pending: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=10)
    updated_at: str


class ReminderDue(Message):
    """A reminder is due now: the page shows it (and a notification if hidden)."""

    type: Literal["reminder.due"] = "reminder.due"
    reminder: "ReminderItem"


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


class ModelActive(Message):
    """Which provider and model now serve a role. Sent at session start and
    whenever the server switches (backup = not the primary provider)."""

    type: Literal["model.active"] = "model.active"
    role: ModelRole
    provider: ProviderId
    model: str = Field(min_length=1, max_length=128)
    backup: bool


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
    | DataChanged
    | ReminderDue
    | SessionResumable
    | PlanProposed
    | PlanUpdated
    | Metrics
    | ErrorEvent
    | ModelActive
    | SessionEnd,
    Field(discriminator="type"),
]
server_message = TypeAdapter(ServerMessage)


# REST API (architecture.md 3.2). All routes need the session token in an
# "Authorization: Bearer <token>" header.


class Rest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionUser(Rest):
    """Who the session belongs to. Without accounts (AUTH_MODE=off) everyone is "local"."""

    id: str = Field(min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    # A guest who signed in with the access code instead of an email.
    anonymous: bool = False


class AuthConfig(Rest):
    """GET /api/auth-config (no token needed): how this server signs people in.
    The publishable key is public by design; Row Level Security protects data."""

    mode: Literal["off", "optional", "required"]
    supabase_url: str | None = None
    publishable_key: str | None = None
    # The server asks for an access code (SECURITY.md T8).
    access_code: bool = False


class SessionToken(Rest):
    """POST /api/session. 401 details: sign_in_required, access_code_required."""

    token: str
    expires_at: int
    user: SessionUser | None = None


MemoryKind = Literal["preference", "fact", "reminder"]
# confirmed: in use. suggested: proposed by TalkBack, waiting for the user's OK.
# superseded: replaced by a correction (kept as history). dismissed: rejected.
MemoryStatus = Literal["confirmed", "suggested", "superseded", "dismissed"]
# Where the words came from (SECURITY.md T3): only the user's own words, or
# their edit, create a memory in use; a suggestion stays one until confirmed.
MemorySource = Literal["user_utterance", "user_text", "user_edit", "assistant_suggestion"]


class MemoryItem(Rest):
    id: Id
    text: str = Field(max_length=500)
    kind: MemoryKind
    utterance: str = Field(max_length=1000)  # the user's exact words
    created_at: str  # ISO 8601, UTC
    status: MemoryStatus = "confirmed"
    source: MemorySource = "user_utterance"
    updated_at: str | None = None  # ISO 8601, UTC; set when edited or replaced
    superseded_by: Id | None = None  # the correction that replaced it


class MemoryList(Rest):
    items: list[MemoryItem]


class MemoryUpdate(Rest):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    kind: MemoryKind | None = None
    # Confirm or dismiss a suggestion. Only suggestions can change status.
    status: Literal["confirmed", "dismissed"] | None = None


ActionStatus = Literal["done", "failed", "cancelled", "declined", "expired", "undone"]


class ActionItem(Rest):
    """One change TalkBack made, or was asked to make (action history)."""

    id: Id
    tool: str = Field(max_length=64)
    status: ActionStatus
    summary: str = Field(max_length=300)  # "Deleted the memory “Home city is Lisbon”"
    created_at: str
    finished_at: str | None = None
    undoable: bool = False
    undone_at: str | None = None


class ActionList(Rest):
    items: list[ActionItem]


class SkillItem(Rest):
    id: Id
    name: str
    triggers: list[str]
    allowed_tools: list[ToolName]
    # One plain sentence: what the skill does and what to say.
    summary: str | None = Field(default=None, max_length=200)
    # Built-in skills ship with TalkBack and cannot be edited (but can be copied).
    builtin: bool = True
    enabled: bool = True
    # What TalkBack does when the skill runs (shown and editable for your own skills).
    instructions: str | None = Field(default=None, max_length=2000)


class SkillCreate(Rest):
    name: str = Field(min_length=1, max_length=60)
    triggers: list[Annotated[str, Field(min_length=4, max_length=60)]] = Field(min_length=1, max_length=10)
    allowed_tools: list[ToolName] = Field(max_length=12)
    instructions: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=200)


class SkillUpdate(Rest):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    triggers: list[Annotated[str, Field(min_length=4, max_length=60)]] | None = Field(default=None, min_length=1, max_length=10)
    allowed_tools: list[ToolName] | None = Field(default=None, max_length=12)
    instructions: str | None = Field(default=None, min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


# Tasks, calendar and reminders (plan P5). Times are ISO 8601 with an offset;
# the server works in the user's time zone (SettingsView.timezone).

TaskStatus = Literal["open", "done", "cancelled"]
Priority = Literal["low", "normal", "high"]


class TaskItem(Rest):
    id: Id
    title: str = Field(max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    status: TaskStatus = "open"
    due_at: str | None = None
    priority: Priority = "normal"
    created_at: str
    updated_at: str | None = None
    completed_at: str | None = None


class TaskCreate(Rest):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_at: str | None = None
    priority: Priority = "normal"


class TaskUpdate(Rest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
    due_at: str | None = None
    priority: Priority | None = None


class TaskList(Rest):
    items: list[TaskItem]


EventKind = Literal["block", "meeting", "focus", "personal"]


class EventItem(Rest):
    id: Id
    title: str = Field(max_length=200)
    starts_at: str
    ends_at: str
    kind: EventKind = "block"
    status: Literal["confirmed", "cancelled"] = "confirmed"
    task_id: Id | None = None
    created_at: str
    updated_at: str | None = None


class EventCreate(Rest):
    title: str = Field(min_length=1, max_length=200)
    starts_at: str
    ends_at: str
    kind: EventKind = "block"
    task_id: Id | None = None


class EventUpdate(Rest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: str | None = None
    ends_at: str | None = None
    kind: EventKind | None = None


class EventList(Rest):
    items: list[EventItem]


ReminderStatus = Literal["scheduled", "delivered", "acknowledged", "cancelled", "missed"]


class ReminderItem(Rest):
    id: Id
    text: str = Field(max_length=300)
    due_at: str
    status: ReminderStatus = "scheduled"
    delivered_at: str | None = None
    snooze_count: int = 0
    created_at: str


class ReminderCreate(Rest):
    text: str = Field(min_length=1, max_length=300)
    due_at: str


class ReminderSnooze(Rest):
    minutes: int = Field(ge=1, le=24 * 60)


class ReminderList(Rest):
    items: list[ReminderItem]


class SkillList(Rest):
    items: list[SkillItem]


class SkillRunAccepted(Rest):
    """The run happens inside the live session; progress arrives as events."""

    run_id: Id


class ProviderInfo(Rest):
    id: ProviderId
    name: str  # display name, e.g. "Nebius Token Factory"
    role: ModelRole
    primary: bool
    enabled: bool  # the user can turn backups off
    configured: bool  # the server has a key for it
    receives_user_words: bool  # shown in Settings for privacy (plan.md 8.2)


class ModelOption(Rest):
    id: Id  # stable, e.g. "nebius:nemotron-3-nano"
    provider: ProviderId
    model: str
    nvidia: bool
    available: bool  # provider enabled and configured


class ModelsView(Rest):
    voice_model: str  # the engine serving voice now; cannot be changed
    # True only for a full-duplex voice model (NVIDIA VoiceChat). The cascade
    # engine is turn-based and handles interruptions with barge-in detection.
    full_duplex: bool = False
    planner_model: Id  # selected ModelOption id
    planner_options: list[ModelOption]  # allowlist, NVIDIA models first
    providers: list[ProviderInfo]  # per role, in backup order


class ToolSetting(Rest):
    enabled: bool
    description: str  # what the tool can access, shown in Settings


InterruptSensitivity = Literal["low", "normal", "high"]
AnswerLength = Literal["short", "normal", "detailed"]


class SettingsView(Rest):
    tools: dict[ToolName, ToolSetting]
    save_recordings: bool  # off by default (FR-18)
    transcripts_in_logs: bool  # off by default
    # How quickly speech over TalkBack counts as an interruption.
    interrupt_sensitivity: InterruptSensitivity = "normal"
    # How long spoken answers are.
    answer_length: AnswerLength = "normal"
    models: ModelsView
    # IANA time zone for tasks, calendar and reminders ("Asia/Dhaka").
    timezone: str = "UTC"
    # Offer to continue an unfinished conversation (plan P7); on by default.
    resume_sessions: bool = True
    # Also keep the last 6 heard turns for that (off by default, SECURITY.md T10).
    keep_recent_turns: bool = False


class SettingsUpdate(Rest):
    tools: dict[ToolName, bool] | None = None
    save_recordings: bool | None = None
    transcripts_in_logs: bool | None = None
    interrupt_sensitivity: InterruptSensitivity | None = None
    answer_length: AnswerLength | None = None
    planner_model: Id | None = None  # must be an available ModelOption id
    providers: dict[ProviderId, bool] | None = None  # turn backups on or off
    timezone: str | None = Field(default=None, min_length=1, max_length=64)  # IANA name, checked by the server
    resume_sessions: bool | None = None
    keep_recent_turns: bool | None = None


ReminderDue.model_rebuild()
