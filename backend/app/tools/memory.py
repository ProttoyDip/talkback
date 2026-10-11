"""Memory tools cannot create memories from model-controlled arguments."""

import asyncio

from pydantic import Field, model_validator

from typing import TYPE_CHECKING

from ..memory import MemoryStore, MemoryWrite
from ..protocol import MemoryKind
from . import Arguments, Tool, ToolOutcome, ToolResult, current_action_key

if TYPE_CHECKING:
    from ..actions import ActionLedger


class ReadArguments(Arguments):
    query: str = Field(default="", max_length=500)


class DeleteArguments(Arguments):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    text: str | None = Field(default=None, min_length=1, max_length=250)
    all: bool = False

    @model_validator(mode="after")
    def one_target(self):
        if self.all:
            if self.id is not None or self.text is not None:
                raise ValueError("choose one memory or all memories")
        elif self.id is None or self.text is None:
            raise ValueError("id and exact memory text required")
        return self


class SuggestArguments(Arguments):
    text: str = Field(min_length=3, max_length=200)
    kind: MemoryKind = "preference"


def memory_tools(store: MemoryStore, ledger: "ActionLedger | None" = None) -> list[Tool]:
    async def read(args: ReadArguments) -> list[ToolResult]:
        items = await asyncio.to_thread(store.in_use)
        if args.query.strip():
            items = await asyncio.to_thread(store.list, args.query)
            items = [item for item in items if item.status == "confirmed"]
        return [ToolResult(item.id, "", item.text) for item in items[:10]]

    async def delete(args: DeleteArguments) -> ToolOutcome:
        rows = await asyncio.to_thread(store.all_rows) if args.all else [await asyncio.to_thread(store.row, args.id)]
        if args.all:
            await asyncio.to_thread(store.delete_all)
        elif rows[0] is None or not await asyncio.to_thread(store.delete, args.id, args.text):
            raise ValueError("memory missing or changed since confirmation")
        action_id = None
        if ledger is not None and rows:
            summary = f"Forgot all {len(rows)} memories" if args.all else f"Forgot “{args.text}”"
            action = await asyncio.to_thread(
                ledger.record, "memory_delete", "done", summary,
                target_kind="memory", target_id=None if args.all else args.id,
                undo={"op": "memory.restore", "rows": rows[:500]}, key=current_action_key.get(),
            )
            action_id = action["id"]
        results = [ToolResult("Memory", "", "Memories deleted." if args.all else "Memory deleted.")]
        return ToolOutcome(results, action_id, undoable=action_id is not None)

    async def suggest(args: SuggestArguments) -> ToolOutcome:
        # A suggestion is model output: stored apart, never used until the user
        # confirms it (SECURITY.md T3). The bridge refuses it after web results.
        item = await asyncio.to_thread(
            store.create,
            MemoryWrite(text=args.text, kind=args.kind, source="assistant_suggestion",
                        utterance="(suggested by TalkBack)", confidence=0.5),
            status="suggested",
        )
        action_id = None
        if ledger is not None:
            action = await asyncio.to_thread(
                ledger.record, "memory_suggest", "done", f"Suggested “{item.text}”",
                target_kind="memory", target_id=item.id,
                undo={"op": "memory.delete", "id": item.id, "text": item.text}, key=current_action_key.get(),
            )
            action_id = action["id"]
        return ToolOutcome([ToolResult("Memory", "", "Suggested; waiting for the user's OK.")], action_id, True)

    def summary(args: DeleteArguments) -> str:
        return "Delete all your memories?" if args.all else f'Delete the memory "{args.text}"?'

    return [
        Tool("memory_read", "Find saved memories.", ReadArguments, read, sensitive=False),
        Tool("memory_delete", "Delete saved memories.", DeleteArguments, delete,
             confirmation_summary=summary),
        Tool("memory_suggest",
             "Suggest saving a lasting preference the user stated but did not ask you to remember. "
             "The user confirms it in the Memory panel; it is not used until then.",
             SuggestArguments, suggest, sensitive=False),
    ]
