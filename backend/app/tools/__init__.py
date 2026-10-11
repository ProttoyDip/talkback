"""Registered tool definitions; handlers receive validated arguments only."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


# Set by the tool bridge while a tool runs: one key per (user's turn, tool,
# arguments), so the same change asked twice is recorded and run once.
current_action_key: ContextVar[str | None] = ContextVar("current_action_key", default=None)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


@dataclass(frozen=True)
class ToolResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool that changes data returns: its results and the recorded action."""

    results: list[ToolResult]
    action_id: str | None = None
    undoable: bool = False
    # Messages for the browser after the status (e.g. memory.saved for a suggestion).
    events: tuple = ()


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[Arguments]
    run: Callable[[Arguments], Awaitable["list[ToolResult] | ToolOutcome"]]
    sensitive: bool = True  # asks the user first (SECURITY.md T5)
    confirmation_summary: Callable[[Arguments], str] | None = None
    # Changes data: recorded with undo, run once per turn, never left half done.
    mutates: bool = False
    # A reversible change that runs without asking, except in a turn that saw
    # web results, where it asks like a sensitive one (plan P5, T5).
    confirm_when_tainted: bool = False
    # What open panels reload after it changes something.
    data_kinds: tuple[str, ...] = ("memories", "actions")
