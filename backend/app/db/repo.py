"""Per-user table access, the same on local SQLite and on Supabase (PostgREST).

A Repo is bound to one table and one user: every read, update and delete is
filtered by that user, and every insert is stamped with it, so one user's
rows can never reach another (plan: separate user data). Only the reminder
scheduler uses an unscoped repo, through stores.system_repo().

Column names come only from the table's declared columns, never from input,
because the SQLite repo puts them into SQL text.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

Row = dict[str, Any]


@dataclass(frozen=True)
class Table:
    name: str
    columns: frozenset[str]
    # Stored as JSON text in SQLite (jsonb or arrays in Postgres).
    json_columns: frozenset[str] = field(default_factory=frozenset)
    # The table has created_at and updated_at; update() stamps updated_at.
    timestamps: bool = True


@dataclass(frozen=True)
class In:
    values: tuple


@dataclass(frozen=True)
class Gte:
    value: Any


@dataclass(frozen=True)
class Lte:
    value: Any


@dataclass(frozen=True)
class IsNull:
    null: bool = True  # False: IS NOT NULL


# A filter maps a column to a value (equals) or one of the operators above.
Where = dict[str, Any]


class Conflict(Exception):
    """The row changed since it was read (expect_updated_at did not match)."""


class Repo(Protocol):
    table: Table
    user_id: str | None

    def insert(self, row: Row) -> Row: ...
    def get(self, identifier: str) -> Row | None: ...
    def select(self, where: Where | None = None, order: str | None = None, limit: int | None = None) -> list[Row]: ...
    def update(self, identifier: str, changes: Row, expect_updated_at: str | None = None) -> Row | None: ...
    def delete(self, identifier: str, where: Where | None = None) -> bool: ...
    def delete_where(self, where: Where) -> int: ...
    def insert_many(self, rows: list[Row]) -> int: ...


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_columns(table: Table, names) -> None:
    unknown = set(names) - table.columns - {"id", "user_id"}
    if unknown:
        raise ValueError(f"unknown column for {table.name}")


def parse_order(table: Table, order: str | None) -> list[tuple[str, bool]]:
    """'due_at.asc,id.desc' -> [(column, descending)]; columns are checked."""
    if not order:
        return []
    parts = []
    for item in order.split(","):
        name, _, direction = item.partition(".")
        check_columns(table, [name])
        if direction not in ("", "asc", "desc"):
            raise ValueError("invalid order")
        parts.append((name, direction == "desc"))
    return parts
