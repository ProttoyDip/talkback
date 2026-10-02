"""Memory tools cannot create memories from model-controlled arguments."""

import asyncio

from pydantic import Field, model_validator

from ..memory import MemoryStore
from . import Arguments, Tool, ToolResult


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


def memory_tools(store: MemoryStore) -> list[Tool]:
    async def read(args: ReadArguments) -> list[ToolResult]:
        items = await asyncio.to_thread(store.list, args.query)
        return [ToolResult(item.id, "", item.text) for item in items[:10]]

    async def delete(args: DeleteArguments) -> list[ToolResult]:
        if args.all:
            await asyncio.to_thread(store.delete_all)
        elif not await asyncio.to_thread(store.delete, args.id, args.text):
            raise ValueError("memory missing or changed since confirmation")
        return [ToolResult("Memory", "", "Memories deleted." if args.all else "Memory deleted.")]

    def summary(args: DeleteArguments) -> str:
        return "Delete all your memories?" if args.all else f'Delete the memory "{args.text}"?'

    return [
        Tool("memory_read", "Find saved memories.", ReadArguments, read, sensitive=False),
        Tool("memory_delete", "Delete saved memories.", DeleteArguments, delete,
             confirmation_summary=summary),
    ]
