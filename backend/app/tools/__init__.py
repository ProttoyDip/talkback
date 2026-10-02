"""Registered tool definitions; handlers receive validated arguments only."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


@dataclass(frozen=True)
class ToolResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[Arguments]
    run: Callable[[Arguments], Awaitable[list[ToolResult]]]
    sensitive: bool = True
