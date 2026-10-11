"""One user's repo never reads, changes or deletes another user's rows."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.db.postgrest_repo import PostgrestRepo, Rest
from app.db.sqlite_repo import SqliteDatabase, SqliteRepo

from .fake_postgrest import FakePostgrest
from .test_repo_contract import NOTES, NOTES_SQLITE


def postgrest(fake: FakePostgrest, user: str | None) -> PostgrestRepo:
    rest = Rest("https://project.supabase.test", SecretStr("sb_secret_test"), httpx.MockTransport(fake))
    return PostgrestRepo(rest, NOTES, user)


@pytest.fixture(params=["sqlite", "postgrest"])
def make_repo(request, tmp_path):
    if request.param == "sqlite":
        database = SqliteDatabase(tmp_path / "test.sqlite3", [NOTES_SQLITE])
        yield lambda user: SqliteRepo(database, NOTES, user)
    else:
        fake = FakePostgrest()
        yield lambda user: postgrest(fake, user)


def test_users_cannot_reach_each_others_rows(make_repo):
    alice, bob = make_repo("alice"), make_repo("bob")
    secret = alice.insert({"title": "Alice's plan", "status": "open"})
    bob.insert({"title": "Bob's plan", "status": "open"})

    assert [n["title"] for n in bob.select()] == ["Bob's plan"]
    assert bob.get(secret["id"]) is None
    assert bob.update(secret["id"], {"title": "changed"}) is None
    assert bob.delete(secret["id"]) is False
    assert alice.get(secret["id"])["title"] == "Alice's plan"


def test_a_user_cannot_insert_rows_for_someone_else(make_repo):
    row = make_repo("bob").insert({"title": "x", "status": "open", "user_id": "alice"})
    assert row["user_id"] == "bob"
    assert make_repo("alice").select() == []


def test_an_unscoped_repo_sees_everyone_but_must_name_the_user_to_insert(make_repo):
    make_repo("alice").insert({"title": "a", "status": "open"})
    make_repo("bob").insert({"title": "b", "status": "open"})
    system = make_repo(None)
    assert sorted(n["user_id"] for n in system.select()) == ["alice", "bob"]
    with pytest.raises(ValueError):
        system.insert({"title": "c", "status": "open"})


def test_every_supabase_request_carries_the_user_filter():
    fake = FakePostgrest()
    notes = postgrest(fake, "alice")
    note = notes.insert({"title": "a", "status": "open"})
    notes.select({"status": "open"})
    notes.get(note["id"])
    notes.update(note["id"], {"status": "done"})
    notes.delete(note["id"])
    assert len(fake.seen) == 5
    for request in fake.seen:
        if request.method == "POST":
            assert json.loads(request.content)["user_id"] == "alice"
        else:
            assert request.url.params.get("user_id") == "eq.alice", request.url
