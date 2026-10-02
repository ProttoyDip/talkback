"""Personal memory with user-utterance provenance and transactional FTS5."""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .protocol import MemoryItem, MemoryKind, MemorySaved, MemoryUpdate


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: str = Field(min_length=1, max_length=500)
    kind: MemoryKind
    source: Literal["user_utterance"]
    utterance: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class MemoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source = 'user_utterance'),
                    utterance TEXT NOT NULL, created_at TEXT NOT NULL,
                    confidence REAL NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(text, content='memories');
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, text)
                        VALUES ('delete', old.rowid, old.text);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, text)
                        VALUES ('delete', old.rowid, old.text);
                    INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(**{key: row[key] for key in MemoryItem.model_fields})

    def create(self, write: MemoryWrite) -> MemoryItem:
        # Revalidate at the persistence boundary, including model_construct input.
        write = MemoryWrite.model_validate(write.model_dump())
        identifier = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)", (
                identifier, write.text, write.kind, write.source, write.utterance,
                created_at, write.confidence,
            ))
        return MemoryItem(id=identifier, text=write.text, kind=write.kind,
                          utterance=write.utterance, created_at=created_at)

    def list(self, query: str = "") -> list[MemoryItem]:
        with self.connect() as db:
            if query.strip():
                # A literal phrase, not user-controlled FTS operators or SQL.
                phrase = '"' + query.replace('"', '""') + '"'
                rows = db.execute("""SELECT m.* FROM memories m JOIN memories_fts f
                    ON m.rowid = f.rowid WHERE memories_fts MATCH ?
                    ORDER BY rank, m.id""", (phrase,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM memories ORDER BY created_at, id").fetchall()
        return [self.item(row) for row in rows]

    def update(self, identifier: str, update: MemoryUpdate) -> MemoryItem | None:
        changes = update.model_dump(exclude_none=True)
        with self.connect() as db:
            for field, value in changes.items():
                # Field names come exclusively from the validated contract model.
                if field not in {"text", "kind"}:
                    raise ValueError("invalid memory field")
                db.execute(f"UPDATE memories SET {field} = ? WHERE id = ?", (value, identifier))
            row = db.execute("SELECT * FROM memories WHERE id = ?", (identifier,)).fetchone()
        return self.item(row) if row else None

    def delete(self, identifier: str, expected_text: str | None = None) -> bool:
        with self.connect() as db:
            if expected_text is None:
                cursor = db.execute("DELETE FROM memories WHERE id = ?", (identifier,))
            else:
                cursor = db.execute("DELETE FROM memories WHERE id = ? AND text = ?", (identifier, expected_text))
            return cursor.rowcount == 1

    def delete_all(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM memories")
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
