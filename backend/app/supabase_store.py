"""Memories and settings in Supabase (Postgres), through its REST API.

Used when SUPABASE_URL and SUPABASE_SECRET_KEY are set (stores.py picks).
The secret key stays on the server; the browser never talks to Supabase.
Row Level Security is on with no policies, so the public (publishable) key
can read nothing: only this server's secret key can (SECURITY.md T6).

Same methods and the same rules as the local SQLite stores (memory.py,
prefs.py): memories come only from the user's own words, and an edit or
delete names the exact row.
"""

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

import httpx
from pydantic import SecretStr

from .db.postgrest_repo import Rest, SupabaseError, shared_rest

from .memory import COLUMNS, MemoryWrite
from .prefs import Prefs, PrefsStore
from .protocol import MemoryItem, MemoryUpdate

FIELDS = "id,text,kind,utterance,created_at,status,source,updated_at,superseded_by"
ROW = ",".join(COLUMNS)  # everything undo needs to put a memory back


def _rest(url: str, key: SecretStr, transport: httpx.BaseTransport | None) -> Rest:
    # Tests pass a transport; otherwise every store shares one client.
    return Rest(url, key, transport) if transport else shared_rest(url, key.get_secret_value())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseMemoryStore:
    """The same as memory.MemoryStore, on Supabase. Every request is limited to one user."""

    def __init__(
        self, url: str, key: SecretStr, user_id: str = "local", transport: httpx.BaseTransport | None = None
    ) -> None:
        self.rest = _rest(url, key, transport)
        self.user_id = user_id
        self.mine = f"eq.{user_id}"

    @staticmethod
    def _item(row: dict) -> MemoryItem:
        return MemoryItem(**{key: row[key] for key in MemoryItem.model_fields if key in row.keys()})

    def _get(self, params: dict, select: str = FIELDS) -> list[dict]:
        return self.rest.call("GET", "/memories", params={"select": select, "user_id": self.mine, **params}).json()

    def _patch(self, params: dict, changes: dict) -> list[dict]:
        return self.rest.call(
            "PATCH", "/memories", json=changes, params={"select": FIELDS, "user_id": self.mine, **params},
            headers={"Prefer": "return=representation"},
        ).json()

    def create(self, write: MemoryWrite, *, status: str = "confirmed", slot: str | None = None) -> MemoryItem:
        write = MemoryWrite.model_validate(write.model_dump())  # revalidate at the boundary
        if status == "confirmed" and write.source == "assistant_suggestion":
            raise ValueError("a suggestion is used only after the user confirms it")
        row = {
            "id": uuid.uuid4().hex, "text": write.text, "kind": write.kind, "source": write.source,
            "utterance": write.utterance, "created_at": _now(), "confidence": write.confidence,
            "user_id": self.user_id, "status": status, "slot": slot,
        }
        response = self.rest.call(
            "POST", "/memories", json=row, params={"select": FIELDS}, headers={"Prefer": "return=representation"},
        )
        return self._item(response.json()[0])

    def get(self, identifier: str) -> MemoryItem | None:
        rows = self._get({"id": f"eq.{identifier}"})
        return self._item(rows[0]) if rows else None

    def row(self, identifier: str) -> dict | None:
        rows = self._get({"id": f"eq.{identifier}"}, ROW)
        return rows[0] if rows else None

    def list(self, query: str = "", history: bool = False) -> list[MemoryItem]:
        statuses = "confirmed,suggested" + (",superseded" if history else "")
        params = {"order": "created_at.asc,id.asc", "status": f"in.({statuses})"}
        if query.strip():
            # A phrase search on the full-text column: the words, in order.
            # PostgREST passes the value as data, never as SQL.
            params["search"] = f"phfts(english).{query.strip()}"
        return [self._item(row) for row in self._get(params)]

    def in_use(self) -> list[MemoryItem]:
        return [self._item(row) for row in self._get({"status": "eq.confirmed", "order": "created_at.asc"})]

    def find_slot(self, slot: str) -> MemoryItem | None:
        rows = self._get({"slot": f"eq.{slot}", "status": "eq.confirmed", "order": "created_at.desc", "limit": "1"})
        return self._item(rows[0]) if rows else None

    def supersede(self, old_id: str, new_id: str) -> bool:
        changes = {"status": "superseded", "superseded_by": new_id, "updated_at": _now()}
        return len(self._patch({"id": f"eq.{old_id}", "status": "eq.confirmed"}, changes)) == 1

    def unsupersede(self, old_id: str) -> bool:
        changes = {"status": "confirmed", "superseded_by": None, "updated_at": _now()}
        return len(self._patch({"id": f"eq.{old_id}", "status": "eq.superseded"}, changes)) == 1

    def update(self, identifier: str, update: MemoryUpdate) -> MemoryItem | None:
        changes = update.model_dump(exclude_none=True)
        if set(changes) - {"text", "kind", "status"}:
            raise ValueError("invalid memory field")
        current = self.get(identifier)
        if current is None:
            return None
        if "status" in changes and current.status != "suggested":
            raise ValueError("only a suggestion can be confirmed or dismissed")
        if not changes:
            return current
        rows = self._patch({"id": f"eq.{identifier}"}, {**changes, "updated_at": _now()})
        return self._item(rows[0]) if rows else None

    def restore(self, row: dict) -> MemoryItem:
        body = {key: row.get(key) for key in COLUMNS}
        if self.get(row["id"]) is not None:  # undo an edit: this user's row only
            changes = {key: value for key, value in body.items() if key != "id"}
            return self._item(self._patch({"id": f"eq.{row['id']}"}, changes)[0])
        rows = self.rest.call(  # undo a delete: a plain insert, never an upsert
            "POST", "/memories", json=body | {"user_id": self.user_id}, params={"select": FIELDS},
            headers={"Prefer": "return=representation"},
        ).json()
        return self._item(rows[0])

    def all_rows(self) -> list[dict]:
        return self._get({}, ROW)

    def delete(self, identifier: str, expected_text: str | None = None) -> bool:
        params = {"id": f"eq.{identifier}", "select": "id", "user_id": self.mine}
        if expected_text is not None:
            params["text"] = f"eq.{expected_text}"
        rows = self.rest.call("DELETE", "/memories", params=params, headers={"Prefer": "return=representation"}).json()
        return len(rows) == 1

    def delete_all(self) -> None:
        self.rest.call("DELETE", "/memories", params={"user_id": self.mine})


class SupabasePrefsStore(PrefsStore):
    """One row (id = 1) holding the settings as JSON."""

    def __init__(self, url: str, key: SecretStr, transport: httpx.BaseTransport | None = None) -> None:
        self.rest = _rest(url, key, transport)

    def load(self) -> Prefs:
        try:
            rows = self.rest.call("GET", "/app_settings", params={"select": "data", "id": "eq.1"}).json()
        except SupabaseError:
            return Prefs()  # private defaults if Supabase is unreachable
        return self.from_raw(rows[0]["data"]) if rows else Prefs()

    def save(self, prefs: Prefs) -> None:
        self.rest.call(
            "POST", "/app_settings", json={"id": 1, "data": asdict(prefs)},
            headers={"Prefer": "resolution=merge-duplicates"},
        )
