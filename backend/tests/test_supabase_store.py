"""Supabase stores, against a small in-memory stand-in for its REST API."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.memory import MemoryStore, MemoryWrite
from app.prefs import Prefs, PrefsStore
from app.protocol import MemoryUpdate
from app.stores import memory_store, prefs_store, uses_supabase
from app.supabase_store import SupabaseError, SupabaseMemoryStore, SupabasePrefsStore

URL = "https://project.supabase.test"
KEY = SecretStr("sb_secret_test")


class FakeSupabase:
    """Just enough PostgREST: eq filters, the phrase search, return=representation."""

    def __init__(self) -> None:
        self.memories: list[dict] = []
        self.settings: dict[int, dict] = {}
        self.seen: list[httpx.Request] = []
        self.fail = False

    @staticmethod
    def _matches(row: dict, params) -> bool:
        for key, value in params.multi_items():
            if key in ("select", "order"):
                continue
            if key == "search":
                phrase = value.split(".", 1)[1].lower()
                if phrase not in row["text"].lower():
                    return False
            elif value == "not.is.null":
                continue
            elif value.startswith("eq.") and str(row.get(key)) != value[3:]:
                return False
        return True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if self.fail:
            return httpx.Response(503, text="stored secret text")
        table = request.url.path.rsplit("/", 1)[-1]
        params = request.url.params
        if table == "app_settings":
            if request.method == "GET":
                return httpx.Response(200, json=[{"data": self.settings[1]}] if 1 in self.settings else [])
            body = json.loads(request.content)
            self.settings[body["id"]] = body["data"]
            return httpx.Response(201)
        if request.method == "POST":
            row = json.loads(request.content)
            self.memories.append(row)
            return httpx.Response(201, json=[row])
        hits = [r for r in self.memories if self._matches(r, params)]
        if request.method == "GET":
            return httpx.Response(200, json=hits)
        if request.method == "PATCH":
            for row in hits:
                row.update(json.loads(request.content))
            return httpx.Response(200, json=hits)
        if request.method == "DELETE":
            self.memories = [r for r in self.memories if r not in hits]
            return httpx.Response(200, json=[{"id": r["id"]} for r in hits])
        return httpx.Response(405)


@pytest.fixture
def fake():
    return FakeSupabase()


def write(text: str, utterance: str = "Remember this") -> MemoryWrite:
    return MemoryWrite(text=text, kind="preference", source="user_utterance", utterance=utterance, confidence=0.9)


def test_memories_round_trip(fake):
    store = SupabaseMemoryStore(URL, KEY, httpx.MockTransport(fake))
    item = store.create(write("I prefer Celsius", "Remember that I prefer Celsius"))
    store.create(write("Likes short answers"))
    assert [m.text for m in store.list()] == ["I prefer Celsius", "Likes short answers"]
    assert [m.text for m in store.list("celsius")] == ["I prefer Celsius"]

    updated = store.update(item.id, MemoryUpdate(text="I prefer Fahrenheit"))
    assert updated is not None and updated.text == "I prefer Fahrenheit"
    assert store.update("missing", MemoryUpdate(text="x")) is None

    assert not store.delete(item.id, "I prefer Celsius")  # the text changed since
    assert store.delete(item.id, "I prefer Fahrenheit")
    store.delete_all()
    assert store.list() == []


def test_only_the_users_own_words_can_create_a_memory(fake):
    store = SupabaseMemoryStore(URL, KEY, httpx.MockTransport(fake))
    forged = MemoryWrite.model_construct(
        text="x", kind="fact", source="tool_result", utterance="y", confidence=0.5
    )
    with pytest.raises(ValueError):
        store.create(forged)
    assert fake.memories == []


def test_secret_key_header_and_no_leaks_in_errors(fake):
    store = SupabaseMemoryStore(URL, KEY, httpx.MockTransport(fake))
    store.list()
    request = fake.seen[0]
    assert request.headers["apikey"] == "sb_secret_test"
    assert "authorization" not in request.headers  # new-style keys go in apikey only
    fake.fail = True
    with pytest.raises(SupabaseError) as error:
        store.list()
    assert "stored secret text" not in str(error.value)


def test_legacy_service_role_key_also_goes_in_authorization(fake):
    store = SupabaseMemoryStore(URL, SecretStr("eyJhbGciOi.test"), httpx.MockTransport(fake))
    store.list()
    assert fake.seen[0].headers["authorization"] == "Bearer eyJhbGciOi.test"


def test_settings_round_trip_and_private_defaults(fake):
    store = SupabasePrefsStore(URL, KEY, httpx.MockTransport(fake))
    assert store.load() == Prefs()
    store.save(Prefs(save_recordings=True, answer_length="short"))
    loaded = store.load()
    assert loaded.save_recordings is True and loaded.answer_length == "short"
    fake.fail = True
    assert store.load() == Prefs()  # unreachable: fall back to the private defaults


def test_store_choice_follows_configuration(tmp_path):
    local = Settings(_env_file=None, memory_db_path=str(tmp_path / "m.sqlite3"), settings_path=str(tmp_path / "s.json"))
    assert not uses_supabase(local)
    assert isinstance(memory_store(local), MemoryStore)
    assert type(prefs_store(local)) is PrefsStore
    cloud = Settings(_env_file=None, supabase_url=URL, supabase_secret_key="sb_secret_x")
    assert uses_supabase(cloud)
    assert isinstance(memory_store(cloud), SupabaseMemoryStore)
    assert isinstance(prefs_store(cloud), SupabasePrefsStore)
