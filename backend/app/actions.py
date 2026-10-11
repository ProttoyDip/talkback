"""Action history and undo (plan P4).

Every change TalkBack makes for a user is recorded with how to reverse it.
The same change asked twice in one turn (a retry, a repeated tool call)
runs once: its idempotency key matches the earlier record. Undo checks that
the target has not changed since, so it never overwrites newer edits.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from .db.repo import IsNull, Lte, Repo
from .protocol import ActionItem

log = logging.getLogger("talkback.actions")

# Undo keeps a copy of what changed (a deleted memory's words). It lasts this
# long; then the copy is erased and the summary loses the memory's text
# (SECURITY.md T10: forgetting means forgetting).
UNDO_WINDOW = timedelta(hours=24)
REDACTED = {"memory_delete": "Forgot a memory", "memory_write": "Changed a memory", "memory_suggest": "Suggested a memory"}
# Plan entries keep their titles: the user can read them in the Plan panel anyway.

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
        current = memory.get(undo["id"])
        if current is None or current.text != undo["text"] or current.status != undo.get("status", current.status):
            raise UndoConflict("memory changed since (edited, kept or replaced)")
        memory.delete(undo["id"], undo["text"])
    elif op == "memory.unsupersede":  # undo a correction
        current = memory.get(undo["new_id"])
        if current is None or current.text != undo["text"] or current.status != "confirmed":
            raise UndoConflict("a later correction replaced it; undo that one first")
        memory.delete(undo["new_id"], undo["text"])
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
        before = {key: undo["before"][key] for key in ("text", "kind", "status", "updated_at") if key in undo["before"]}
        memory.restore({**current, **before})
    else:
        raise NotUndoable(op)


ROW_TABLES = {"tasks", "events", "reminders"}


def _undo_row(tables, undo: dict) -> None:
    """Tasks, calendar blocks, reminders (plan P5): soft-deleted rows make this simple."""
    if undo["table"] not in ROW_TABLES:
        raise NotUndoable(undo["table"])
    repo = tables(undo["table"])
    if undo["op"] == "rows.unadd":  # a day plan: all its blocks, or none
        rows = [(repo.get(r["id"]), r) for r in undo["rows"]]
        if any(cur is None or cur.get("deleted_at") or cur["title"] != r["title"] for cur, r in rows):
            raise UndoConflict("a block of the plan changed since")
        removed = []
        try:
            for current, _ in rows:
                removed.append(repo.update(current["id"], {"deleted_at": now()}, expect_updated_at=current["updated_at"]))
        except Exception:
            for row in removed:  # all or none
                repo.update(row["id"], {"deleted_at": None})
            raise UndoConflict("a block of the plan changed since") from None
        return
    current = repo.get(undo["id"])
    # Changed since? Only the fields this action changed matter, so undoing
    # newer actions first (a stack) still works.
    if current is None or any(current.get(k) != v for k, v in undo["after"].items()):
        raise UndoConflict("it changed since")
    if undo["op"] == "row.unadd":
        repo.update(undo["id"], {"deleted_at": now()}, expect_updated_at=current["updated_at"])
    else:
        allowed = repo.table.columns - {"created_at", "updated_at"}
        before = {key: value for key, value in undo["before"].items() if key in allowed}
        repo.update(undo["id"], before, expect_updated_at=current["updated_at"])


class ActionLedger:
    def __init__(self, repo: Repo, memory=None, session_id: str | None = None, tables=None) -> None:
        self.repo = repo  # one user's actions
        self.memory = memory  # that user's memory store, for undo
        self.session_id = session_id
        self.tables = tables  # table name -> that user's Repo (tasks, events, reminders)

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
        self.expire()
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
        self.expire()
        return [self.item(row) for row in self.repo.select(order="created_at.desc", limit=limit)]

    def expire(self, older_than: datetime | None = None) -> None:
        """Erase undo copies past the undo window, and the memory text in their summaries."""
        cutoff = (older_than or datetime.now(timezone.utc) - UNDO_WINDOW).isoformat()
        for row in self.repo.select({"created_at": Lte(cutoff), "undo": IsNull(False)}, limit=200):
            self.redact(row)

    def redact(self, row: dict) -> None:
        self.repo.update(row["id"], {"undo": None, "summary": REDACTED.get(row["tool"], row["summary"])})

    def forget_history(self, keep: str | None = None) -> None:
        """"Forget everything": earlier history keeps no memory text either."""
        for row in self.repo.select({"target_kind": "memory"}, limit=1000):
            if row["id"] != keep:
                self.redact(row)

    def undo(self, action_id: str) -> ActionItem:
        row = self.repo.get(action_id)
        if row is None or row["status"] != "done" or not row.get("undo"):
            raise NotUndoable(action_id)
        undo = row["undo"]
        if undo["op"].startswith(("row.", "rows.")):
            if self.tables is None:
                raise NotUndoable("no store")
            try:
                _undo_row(self.tables, undo)
            except Exception as error:  # Conflict from the repo: changed since
                if isinstance(error, (UndoConflict, NotUndoable)):
                    raise
                raise UndoConflict(str(type(error).__name__)) from None
        else:
            if self.memory is None:
                raise NotUndoable("no store")
            _undo_memory(self.memory, undo)
        updated = self.repo.update(action_id, {"status": "undone", "undone_at": now()})
        log.info("action undone", extra={"event": row["tool"]})
        return self.item(updated)
