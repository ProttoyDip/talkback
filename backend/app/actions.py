"""Action history and undo (plan P4).

Every change TalkBack makes for a user is recorded with how to reverse it.
The same change asked twice in one turn (a retry, a repeated tool call)
runs once: its idempotency key matches the earlier record. Undo checks that
the target has not changed since, so it never overwrites newer edits.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from .db.repo import Repo
from .protocol import ActionItem

log = logging.getLogger("talkback.actions")

# How each kind of change is reversed: undo["op"] -> handler(memory store, undo).


class UndoConflict(Exception):
    """The target changed since the action; undoing would lose newer work."""


class NotUndoable(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def idempotency_key(user_id: str, turn_id: str, tool: str, arguments: dict) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{user_id}\x1f{turn_id}\x1f{tool}\x1f{canonical}".encode()).hexdigest()


def _undo_memory(memory, undo: dict) -> None:
    op = undo["op"]
    if op == "memory.delete":  # undo a save or a suggestion
        if not memory.delete(undo["id"], undo["text"]):
            raise UndoConflict("memory changed or already gone")
    elif op == "memory.unsupersede":  # undo a correction
        if not memory.delete(undo["new_id"], undo["text"]):
            raise UndoConflict("the new memory changed or is gone")
        memory.unsupersede(undo["old_id"])
    elif op == "memory.restore":  # undo a delete
        for row in undo["rows"]:
            if memory.get(row["id"]) is not None:
                raise UndoConflict("a memory with that id exists again")
        for row in undo["rows"]:
            memory.restore(row)
    elif op == "memory.revert":  # undo an edit, confirm or dismiss
        current = memory.row(undo["id"])
        if current is None or current["updated_at"] != undo["after_updated_at"]:
            raise UndoConflict("memory changed since")
        memory.restore({**current, **undo["before"]})
    else:
        raise NotUndoable(op)


class ActionLedger:
    def __init__(self, repo: Repo, memory=None, session_id: str | None = None) -> None:
        self.repo = repo  # one user's actions
        self.memory = memory  # that user's memory store, for undo
        self.session_id = session_id

    def find(self, key: str) -> dict | None:
        rows = self.repo.select({"idempotency_key": key}, limit=1)
        return rows[0] if rows else None

    def record(
        self, tool: str, status: str, summary: str, *,
        target_kind: str | None = None, target_id: str | None = None,
        undo: dict | None = None, key: str | None = None, call_id: str | None = None,
    ) -> dict:
        """Write one action; with a key already used, return that earlier action."""
        if key is not None and (earlier := self.find(key)) is not None:
            return earlier
        stamp = now()
        return self.repo.insert({
            "session_id": self.session_id, "call_id": call_id, "tool": tool, "status": status,
            "summary": summary[:300], "target_kind": target_kind, "target_id": target_id, "undo": undo,
            "idempotency_key": key or hashlib.sha256(f"{stamp}{tool}{summary}".encode()).hexdigest(),
            "finished_at": stamp,
        })

    @staticmethod
    def item(row: dict) -> ActionItem:
        return ActionItem(
            id=row["id"], tool=row["tool"], status=row["status"], summary=row["summary"],
            created_at=row["created_at"], finished_at=row.get("finished_at"),
            undoable=row["status"] == "done" and bool(row.get("undo")), undone_at=row.get("undone_at"),
        )

    def list(self, limit: int = 50) -> list[ActionItem]:
        return [self.item(row) for row in self.repo.select(order="created_at.desc", limit=limit)]

    def undo(self, action_id: str) -> ActionItem:
        row = self.repo.get(action_id)
        if row is None or row["status"] != "done" or not row.get("undo"):
            raise NotUndoable(action_id)
        if self.memory is None:
            raise NotUndoable("no store")
        _undo_memory(self.memory, row["undo"])
        updated = self.repo.update(action_id, {"status": "undone", "undone_at": now()})
        log.info("action undone", extra={"event": row["tool"]})
        return self.item(updated)
