"""Personal memory with user-utterance provenance and transactional FTS5.

Correction-aware (plan P4): a memory can be replaced by a newer one about the
same thing ("slot"); the old one stays as history (superseded) and is never
used again. A suggestion from TalkBack waits for the user's OK (suggested)
and is not used until confirmed (SECURITY.md T3).
"""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from .db.schema import SQLITE_MIGRATIONS
from .db.sqlite_repo import SqliteDatabase
from .protocol import MemoryItem, MemoryKind, MemorySaved, MemorySource, MemoryStatus, MemoryUpdate

if TYPE_CHECKING:
    from .actions import ActionLedger

# The columns a full row has; undo restores a deleted memory from them.
COLUMNS = (
    "id", "text", "kind", "source", "utterance", "created_at", "confidence",
    "status", "slot", "updated_at", "superseded_by",
)
SHOWN: tuple[MemoryStatus, ...] = ("confirmed", "suggested")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    text: str = Field(min_length=1, max_length=500)
    kind: MemoryKind
    source: MemorySource
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

    def _one(self, db, identifier: str) -> sqlite3.Row | None:
        return db.execute(
            "SELECT * FROM memories WHERE id = ? AND user_id = ?", (identifier, self.user_id)
        ).fetchone()

    def create(self, write: MemoryWrite, *, status: MemoryStatus = "confirmed", slot: str | None = None) -> MemoryItem:
        # Revalidate at the persistence boundary, including model_construct input.
        write = MemoryWrite.model_validate(write.model_dump())
        if status == "confirmed" and write.source == "assistant_suggestion":
            raise ValueError("a suggestion is used only after the user confirms it")
        identifier = uuid.uuid4().hex
        created_at = now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO memories (id, text, kind, source, utterance, created_at, confidence, user_id, status, slot)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, write.text, write.kind, write.source, write.utterance,
                 created_at, write.confidence, self.user_id, status, slot),
            )
            return self.item(self._one(db, identifier))

    def get(self, identifier: str) -> MemoryItem | None:
        with self.connect() as db:
            row = self._one(db, identifier)
        return self.item(row) if row else None

    def row(self, identifier: str) -> dict | None:
        """The full stored row, for undo."""
        with self.connect() as db:
            row = self._one(db, identifier)
        return {key: row[key] for key in COLUMNS} if row else None

    def list(self, query: str = "", history: bool = False) -> list[MemoryItem]:
        """Memories in use and suggestions; history adds replaced ones."""
        statuses = SHOWN + (("superseded",) if history else ())
        marks = ",".join("?" * len(statuses))
        with self.connect() as db:
            if query.strip():
                # A literal phrase, not user-controlled FTS operators or SQL.
                phrase = '"' + query.replace('"', '""') + '"'
                rows = db.execute(f"""SELECT m.* FROM memories m JOIN memories_fts f
                    ON m.rowid = f.rowid WHERE memories_fts MATCH ? AND m.user_id = ? AND m.status IN ({marks})
                    ORDER BY rank, m.id""", (phrase, self.user_id, *statuses)).fetchall()
            else:
                rows = db.execute(
                    f"SELECT * FROM memories WHERE user_id = ? AND status IN ({marks}) ORDER BY created_at, id",
                    (self.user_id, *statuses),
                ).fetchall()
        return [self.item(row) for row in rows]

    def in_use(self) -> list[MemoryItem]:
        """What the model may use: confirmed memories only."""
        return [item for item in self.list() if item.status == "confirmed"]

    def find_slot(self, slot: str) -> MemoryItem | None:
        """The memory in use about this thing (home, name...), newest first."""
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM memories WHERE user_id = ? AND slot = ? AND status = 'confirmed'"
                " ORDER BY created_at DESC LIMIT 1",
                (self.user_id, slot),
            ).fetchone()
        return self.item(row) if row else None

    def supersede(self, old_id: str, new_id: str) -> bool:
        with self.connect() as db:
            return db.execute(
                "UPDATE memories SET status = 'superseded', superseded_by = ?, updated_at = ?"
                " WHERE id = ? AND user_id = ? AND status = 'confirmed'",
                (new_id, now(), old_id, self.user_id),
            ).rowcount == 1

    def unsupersede(self, old_id: str) -> bool:
        with self.connect() as db:
            return db.execute(
                "UPDATE memories SET status = 'confirmed', superseded_by = NULL, updated_at = ?"
                " WHERE id = ? AND user_id = ? AND status = 'superseded'",
                (now(), old_id, self.user_id),
            ).rowcount == 1

    def update(self, identifier: str, update: MemoryUpdate) -> MemoryItem | None:
        changes = update.model_dump(exclude_none=True)
        with self.connect() as db:
            row = self._one(db, identifier)
            if row is None:
                return None
            if "status" in changes and row["status"] != "suggested":
                raise ValueError("only a suggestion can be confirmed or dismissed")
            for field, value in changes.items():
                # Field names come exclusively from the validated contract model.
                if field not in {"text", "kind", "status"}:
                    raise ValueError("invalid memory field")
                db.execute(
                    f"UPDATE memories SET {field} = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (value, now(), identifier, self.user_id),
                )
            return self.item(self._one(db, identifier))

    def restore(self, row: dict) -> MemoryItem:
        """Put a memory back exactly as it was (undo)."""
        values = [row.get(key) for key in COLUMNS]
        with self.connect() as db:
            if self._one(db, row["id"]) is not None:
                # UPDATE, not INSERT OR REPLACE: REPLACE skips the delete
                # trigger and would leave a stale full-text entry.
                rest = [key for key in COLUMNS if key != "id"]
                db.execute(
                    f"UPDATE memories SET {', '.join(f'{key} = ?' for key in rest)} WHERE id = ? AND user_id = ?",
                    (*[row.get(key) for key in rest], row["id"], self.user_id),
                )
            else:
                db.execute(
                    f"INSERT INTO memories ({', '.join(COLUMNS)}, user_id) VALUES ({', '.join('?' * len(COLUMNS))}, ?)",
                    (*values, self.user_id),
                )
            return self.item(self._one(db, row["id"]))

    def all_rows(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memories WHERE user_id = ?", (self.user_id,)).fetchall()
        return [{key: row[key] for key in COLUMNS} for row in rows]

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
    *, slot: str | None = None, ledger: "ActionLedger | None" = None, only_if_replacing: bool = False,
) -> MemoryItem | None:
    """Called with provenance from trusted transcription, never a tool result.

    With a slot, a newer memory about the same thing replaces the older one
    (kept as history). The change is recorded, so it can be undone.
    """
    old = await asyncio.to_thread(store.find_slot, slot) if slot else None
    if only_if_replacing and old is None:
        return None  # "actually, ..." with nothing saved about it: not a memory
    item = await asyncio.to_thread(store.create, write, slot=slot)
    if old is not None:
        await asyncio.to_thread(store.supersede, old.id, item.id)
    action_id = None
    if ledger is not None:
        undo = (
            {"op": "memory.unsupersede", "old_id": old.id, "new_id": item.id, "text": item.text}
            if old is not None
            else {"op": "memory.delete", "id": item.id, "text": item.text, "status": "confirmed"}
        )
        summary = f"Remembered “{item.text}”" + (f" instead of “{old.text}”" if old else "")
        action = await asyncio.to_thread(
            ledger.record, "memory_write", "done", summary, target_kind="memory", target_id=item.id, undo=undo,
        )
        action_id = action["id"]
    await emit(MemorySaved(
        id=item.id, text=item.text, status=item.status, action_id=action_id,
        replaced_id=old.id if old else None, replaced_text=old.text if old else None,
    ))
    return item
