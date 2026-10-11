"""The same Repo behaviour on local SQLite and on Supabase (PostgREST)."""

import httpx
import pytest
from pydantic import SecretStr

from app.db.postgrest_repo import PostgrestRepo, Rest
from app.db.repo import Conflict, Gte, In, IsNull, Lte, Table
from app.db.sqlite_repo import SqliteDatabase, SqliteRepo

from .fake_postgrest import FakePostgrest

NOTES = Table(
    "notes",
    frozenset({"title", "status", "due_at", "tags", "created_at", "updated_at"}),
    frozenset({"tags"}),
)
NOTES_SQLITE = """
CREATE TABLE notes (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
    status TEXT NOT NULL, due_at TEXT, tags TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


@pytest.fixture(params=["sqlite", "postgrest"])
def make_repo(request, tmp_path):
    if request.param == "sqlite":
        database = SqliteDatabase(tmp_path / "test.sqlite3", [NOTES_SQLITE])
        yield lambda user: SqliteRepo(database, NOTES, user)
    else:
        transport = httpx.MockTransport(FakePostgrest())
        rest = Rest("https://project.supabase.test", SecretStr("sb_secret_test"), transport)
        yield lambda user: PostgrestRepo(rest, NOTES, user)


def test_insert_get_select_update_delete(make_repo):
    notes = make_repo("alice")
    first = notes.insert({"title": "Call mom", "status": "open", "due_at": "2026-10-12", "tags": ["family"]})
    notes.insert({"title": "Pay rent", "status": "done", "due_at": "2026-10-01"})
    notes.insert({"title": "Read", "status": "open"})
    assert notes.get(first["id"])["tags"] == ["family"]
    assert notes.get(first["id"])["user_id"] == "alice"

    def titles(**query):
        return [n["title"] for n in notes.select(**query)]

    assert titles(where={"status": "open"}, order="title.asc") == ["Call mom", "Read"]
    assert titles(where={"status": In(("done", "gone"))}) == ["Pay rent"]
    assert titles(where={"due_at": Gte("2026-10-05")}) == ["Call mom"]
    assert titles(where={"due_at": Lte("2026-10-05")}) == ["Pay rent"]
    assert titles(where={"due_at": IsNull()}) == ["Read"]
    assert len(notes.select({"due_at": IsNull(False)})) == 2
    assert len(notes.select(order="title.desc", limit=2)) == 2

    updated = notes.update(first["id"], {"status": "done"})
    assert updated["status"] == "done" and updated["updated_at"] >= first["updated_at"]
    assert notes.delete(first["id"]) is True
    assert notes.get(first["id"]) is None
    assert notes.delete(first["id"]) is False


def test_update_with_a_stale_version_is_a_conflict(make_repo):
    notes = make_repo("alice")
    note = notes.insert({"title": "Gym", "status": "open"})
    fresh = notes.update(note["id"], {"title": "Gym at 7"}, expect_updated_at=note["updated_at"])
    assert fresh["title"] == "Gym at 7"
    with pytest.raises(Conflict):
        notes.update(note["id"], {"title": "Gym at 8"}, expect_updated_at="2000-01-01T00:00:00+00:00")
    assert notes.get(note["id"])["title"] == "Gym at 7"


def test_unknown_columns_are_refused(make_repo):
    notes = make_repo("alice")
    with pytest.raises(ValueError):
        notes.insert({"title": "x", "status": "open", "evil; DROP TABLE notes": 1})
    with pytest.raises(ValueError):
        notes.select({"nope": 1})
    with pytest.raises(ValueError):
        notes.select(order="title; DROP TABLE notes")


def test_insert_many_and_delete_where_stay_within_the_user(make_repo):
    alice, bob = make_repo("alice"), make_repo("bob")
    assert alice.insert_many([
        {"title": f"p{i}", "status": "doc1", "created_at": "2026-10-12", "updated_at": "2026-10-12"} for i in range(3)
    ]) == 3
    bob.insert({"title": "theirs", "status": "doc1"})
    assert {n["user_id"] for n in alice.select()} == {"alice"}
    assert alice.delete_where({"status": "doc1"}) == 3
    assert alice.select() == [] and [n["title"] for n in bob.select()] == ["theirs"]
    with pytest.raises(ValueError):
        alice.delete_where({})
