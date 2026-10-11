"""Personal memory with user-utterance provenance and transactional FTS5."""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .db.schema import SQLITE_MIGRATIONS
from .db.sqlite_repo import SqliteDatabase
from .protocol import MemoryItem, MemoryKind, MemorySaved, MemoryUpdate


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: str = Field(min_length=1, max_length=500)
    kind: MemoryKind
    source: Literal["user_utterance"]
    utterance: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class MemoryStore:
    def __init__(self, path: str | Path, user_id: str = "local") -> None:
        self.path = Path(path)
        self.user_id = user_id  # every query below is limited to this user
        self.database = SqliteDatabase(self.path, SQLITE_MIGRATIONS)

    def connect(self):
        return self.database.connect()

    @staticmethod
    def item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(**{key: row[key] for key in MemoryItem.model_fields if key in row.keys()})

    def create(self, write: MemoryWrite) -> MemoryItem:
        # Revalidate at the persistence boundary, including model_construct input.
        write = MemoryWrite.model_validate(write.model_dump())
        identifier = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute(
                "INSERT INTO memories (id, text, kind, source, utterance, created_at, confidence, user_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, write.text, write.kind, write.source, write.utterance,
                 created_at, write.confidence, self.user_id),
            )
        return MemoryItem(id=identifier, text=write.text, kind=write.kind,
                          utterance=write.utterance, created_at=created_at)

    def list(self, query: str = "") -> list[MemoryItem]:
        with self.connect() as db:
            if query.strip():
                # A literal phrase, not user-controlled FTS operators or SQL.
                phrase = '"' + query.replace('"', '""') + '"'
                rows = db.execute("""SELECT m.* FROM memories m JOIN memories_fts f
                    ON m.rowid = f.rowid WHERE memories_fts MATCH ? AND m.user_id = ?
                    ORDER BY rank, m.id""", (phrase, self.user_id)).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at, id", (self.user_id,)
                ).fetchall()
        return [self.item(row) for row in rows]

    def update(self, identifier: str, update: MemoryUpdate) -> MemoryItem | None:
        changes = update.model_dump(exclude_none=True)
        with self.connect() as db:
            for field, value in changes.items():
                # Field names come exclusively from the validated contract model.
                if field not in {"text", "kind"}:
                    raise ValueError("invalid memory field")
                db.execute(
                    f"UPDATE memories SET {field} = ? WHERE id = ? AND user_id = ?", (value, identifier, self.user_id)
                )
            row = db.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?", (identifier, self.user_id)
            ).fetchone()
        return self.item(row) if row else None

    def delete(self, identifier: str, expected_text: str | None = None) -> bool:
        with self.connect() as db:
            if expected_text is None:
                cursor = db.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (identifier, self.user_id))
            else:
                cursor = db.execute(
                    "DELETE FROM memories WHERE id = ? AND text = ? AND user_id = ?",
                    (identifier, expected_text, self.user_id),
                )
            return cursor.rowcount == 1

    def delete_all(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM memories WHERE user_id = ?", (self.user_id,))
            # Drop obsolete FTS segments containing deleted words.
            db.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")


async def remember(
    store: MemoryStore, write: MemoryWrite,
    emit: Callable[[MemorySaved], Awaitable[None]],
) -> MemoryItem:
    """Called with provenance from trusted transcription, never a tool result."""
    item = await asyncio.to_thread(store.create, write)
    await emit(MemorySaved(id=item.id, text=item.text))
    return item
