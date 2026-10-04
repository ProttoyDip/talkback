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

from .memory import MemoryWrite
from .prefs import Prefs, PrefsStore
from .protocol import MemoryItem, MemoryUpdate

TIMEOUT = 8.0
FIELDS = "id,text,kind,utterance,created_at"


class SupabaseError(Exception):
    """Supabase could not be reached or refused the request. Safe to log."""


class _Rest:
    def __init__(self, url: str, key: SecretStr, transport: httpx.BaseTransport | None = None) -> None:
        secret = key.get_secret_value()
        headers = {"apikey": secret}
        # Legacy service_role keys are JWTs and also go in Authorization;
        # the newer sb_secret_ keys go in apikey only.
        if secret.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {secret}"
        self.client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1", headers=headers, timeout=TIMEOUT,
            follow_redirects=False, transport=transport,
        )

    def call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise SupabaseError("Supabase is not reachable") from None
        if response.status_code >= 400:
            # Never include the response body: it can echo stored text.
            raise SupabaseError(f"Supabase refused the request ({response.status_code})")
        return response


class SupabaseMemoryStore:
    def __init__(self, url: str, key: SecretStr, transport: httpx.BaseTransport | None = None) -> None:
        self.rest = _Rest(url, key, transport)

    @staticmethod
    def _item(row: dict) -> MemoryItem:
        return MemoryItem(**{key: row[key] for key in MemoryItem.model_fields})

    def create(self, write: MemoryWrite) -> MemoryItem:
        write = MemoryWrite.model_validate(write.model_dump())  # revalidate at the boundary
        row = {
            "id": uuid.uuid4().hex,
            "text": write.text,
            "kind": write.kind,
            "source": write.source,
            "utterance": write.utterance,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "confidence": write.confidence,
        }
        response = self.rest.call(
            "POST", "/memories", json=row, params={"select": FIELDS},
            headers={"Prefer": "return=representation"},
        )
        return self._item(response.json()[0])

    def list(self, query: str = "") -> list[MemoryItem]:
        params = {"select": FIELDS, "order": "created_at.asc,id.asc"}
        if query.strip():
            # A phrase search on the full-text column: the words, in order.
            # PostgREST passes the value as data, never as SQL.
            params["search"] = f"phfts(english).{query.strip()}"
        return [self._item(row) for row in self.rest.call("GET", "/memories", params=params).json()]

    def update(self, identifier: str, update: MemoryUpdate) -> MemoryItem | None:
        changes = update.model_dump(exclude_none=True)
        if set(changes) - {"text", "kind"}:
            raise ValueError("invalid memory field")
        if not changes:
            rows = self.rest.call("GET", "/memories", params={"select": FIELDS, "id": f"eq.{identifier}"}).json()
        else:
            rows = self.rest.call(
                "PATCH", "/memories", json=changes, params={"select": FIELDS, "id": f"eq.{identifier}"},
                headers={"Prefer": "return=representation"},
            ).json()
        return self._item(rows[0]) if rows else None

    def delete(self, identifier: str, expected_text: str | None = None) -> bool:
        params = {"id": f"eq.{identifier}", "select": "id"}
        if expected_text is not None:
            params["text"] = f"eq.{expected_text}"
        rows = self.rest.call("DELETE", "/memories", params=params, headers={"Prefer": "return=representation"}).json()
        return len(rows) == 1

    def delete_all(self) -> None:
        # PostgREST refuses an unfiltered delete; this filter matches every row.
        self.rest.call("DELETE", "/memories", params={"id": "not.is.null"})


class SupabasePrefsStore(PrefsStore):
    """One row (id = 1) holding the settings as JSON."""

    def __init__(self, url: str, key: SecretStr, transport: httpx.BaseTransport | None = None) -> None:
        self.rest = _Rest(url, key, transport)

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
