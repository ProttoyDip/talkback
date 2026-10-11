"""An in-memory stand-in for Supabase's REST API (PostgREST), for repo tests.

Supports what PostgrestRepo sends: eq, in, gte, lte, is.null/not.is.null
filters, order, limit, and Prefer: return=representation.
"""

import json
import re

import httpx


def _value(text: str):
    return {"true": True, "false": False, "null": None}.get(text, text)


def _in_values(text: str) -> list[str]:
    """in.("a","b") or in.(a,b): PostgREST accepts both."""
    if '"' not in text:
        return text.split(",")
    found = re.finditer(r'"((?:[^"\\]|\\.)*)"', text)
    return [m.group(1).replace('\\"', '"').replace("\\\\", "\\") for m in found]


class FakePostgrest:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self.seen: list[httpx.Request] = []

    @staticmethod
    def _matches(row: dict, params) -> bool:
        for key, value in params.multi_items():
            if key in ("select", "order", "limit"):
                continue
            field = row.get(key)
            if value == "is.null":
                ok = field is None
            elif value == "not.is.null":
                ok = field is not None
            elif value.startswith("in.("):
                ok = str(field) in _in_values(value[4:-1])
            elif value.startswith("gte."):
                ok = field is not None and str(field) >= value[4:]
            elif value.startswith("lte."):
                ok = field is not None and str(field) <= value[4:]
            elif value.startswith("eq."):
                ok = field == _value(value[3:]) or str(field) == value[3:]
            else:
                raise AssertionError(f"unsupported filter {key}={value}")
            if not ok:
                return False
        return True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        rows = self.tables.setdefault(request.url.path.rsplit("/", 1)[-1], [])
        params = request.url.params
        if request.method == "POST":
            row = json.loads(request.content)
            rows.append(row)
            return httpx.Response(201, json=[row])
        hits = [r for r in rows if self._matches(r, params)]
        if request.method == "GET":
            for item in reversed((params.get("order") or "").split(",")):
                if item:
                    name, _, direction = item.partition(".")
                    hits.sort(key=lambda r: (r.get(name) is None, r.get(name)), reverse=direction == "desc")
            if "limit" in params:
                hits = hits[: int(params["limit"])]
            return httpx.Response(200, json=hits)
        if request.method == "PATCH":
            for row in hits:
                row.update(json.loads(request.content))
            return httpx.Response(200, json=hits)
        if request.method == "DELETE":
            for row in hits:
                rows.remove(row)
            return httpx.Response(200, json=hits)
        return httpx.Response(405)
