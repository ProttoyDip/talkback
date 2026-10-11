"""Supabase storage through its REST API (PostgREST), with the per-user Repo.

The secret key stays on the server (SECURITY.md T6). Row Level Security is
on for every table; this server's secret key bypasses it, so the user filter
here is what keeps users apart, and test_isolation.py checks it is always sent.
"""

import uuid
from functools import lru_cache

import httpx
from pydantic import SecretStr

from .repo import Conflict, Gte, In, IsNull, Lte, Row, Table, Where, check_columns, now, parse_order

TIMEOUT = 8.0


class SupabaseError(Exception):
    """Supabase could not be reached or refused the request. Safe to log."""


class Rest:
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


@lru_cache(maxsize=4)
def shared_rest(url: str, key: str) -> Rest:
    """One client (and connection pool) per project for the whole process."""
    return Rest(url, SecretStr(key))


def _literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _quoted(value) -> str:
    """A value inside in.(...): quoted, so commas and parentheses stay data."""
    text = _literal(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


class PostgrestRepo:
    def __init__(self, rest: Rest, table: Table, user_id: str | None) -> None:
        self.rest = rest
        self.table = table
        self.user_id = user_id

    def _params(self, where: Where | None) -> list[tuple[str, str]]:
        where = dict(where or {})
        check_columns(self.table, where)
        if self.user_id is not None:
            where["user_id"] = self.user_id
        params = []
        for name, value in where.items():
            if isinstance(value, In):
                params.append((name, f"in.({','.join(_quoted(v) for v in value.values)})"))
            elif isinstance(value, Gte):
                params.append((name, f"gte.{_literal(value.value)}"))
            elif isinstance(value, Lte):
                params.append((name, f"lte.{_literal(value.value)}"))
            elif isinstance(value, IsNull):
                params.append((name, "is.null" if value.null else "not.is.null"))
            else:
                params.append((name, f"eq.{_literal(value)}"))
        return params

    def _path(self) -> str:
        return f"/{self.table.name}"

    def insert(self, row: Row) -> Row:
        row = dict(row)
        check_columns(self.table, row)
        row.setdefault("id", uuid.uuid4().hex)
        if self.user_id is not None:
            row["user_id"] = self.user_id
        elif "user_id" not in row:
            raise ValueError("an unscoped insert must name the user")
        if self.table.timestamps:
            row.setdefault("created_at", now())
            row.setdefault("updated_at", row["created_at"])
        rows = self.rest.call(
            "POST", self._path(), json=row, params={"select": "*"}, headers={"Prefer": "return=representation"},
        ).json()
        return rows[0] if rows else row

    def get(self, identifier: str) -> Row | None:
        rows = self.select({"id": identifier}, limit=1)
        return rows[0] if rows else None

    def select(self, where: Where | None = None, order: str | None = None, limit: int | None = None) -> list[Row]:
        params = [("select", "*"), *self._params(where)]
        ordering = parse_order(self.table, order)
        if ordering:
            params.append(("order", ",".join(f"{name}.{'desc' if desc else 'asc'}" for name, desc in ordering)))
        if limit is not None:
            params.append(("limit", str(int(limit))))
        return self.rest.call("GET", self._path(), params=params).json()

    def update(self, identifier: str, changes: Row, expect_updated_at: str | None = None) -> Row | None:
        changes = {k: v for k, v in changes.items() if k not in ("id", "user_id", "created_at")}
        check_columns(self.table, changes)
        if self.table.timestamps:
            changes["updated_at"] = now()
        where: Where = {"id": identifier}
        if expect_updated_at is not None:
            where["updated_at"] = expect_updated_at
        rows = self.rest.call(
            "PATCH", self._path(), json=changes, params=[("select", "*"), *self._params(where)],
            headers={"Prefer": "return=representation"},
        ).json()
        if rows:
            return rows[0]
        if expect_updated_at is not None and self.get(identifier) is not None:
            raise Conflict(identifier)
        return None

    def delete(self, identifier: str, where: Where | None = None) -> bool:
        rows = self.rest.call(
            "DELETE", self._path(), params=[("select", "id"), *self._params({**(where or {}), "id": identifier})],
            headers={"Prefer": "return=representation"},
        ).json()
        return len(rows) == 1
