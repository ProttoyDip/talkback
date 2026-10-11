"""Accounts: sign-in at POST /api/session, and each user's data kept apart."""

import httpx
import pytest
from pydantic import SecretStr

from app import main
from app.auth import SupabaseUser, supabase_user
from app.config import Settings
from app.memory import MemoryWrite
from app.stores import memory_store
from app.tokens import issue_token, verify_token

KEY = b"k" * 40
ALICE = "6f1c2c0e-3b7a-4c1e-9b1d-0a8a1d2f3e4c"
BOB = "0b9e8d7c-6a5b-4c3d-8e2f-1a0b9c8d7e6f"


def test_tokens_carry_the_user():
    token, claims = issue_token(KEY, now=1000, user_id=ALICE, anonymous=True)
    found = verify_token(KEY, token, now=1001)
    assert found == claims and found.user_id == ALICE and found.anonymous is True


def test_tokens_from_before_accounts_are_refused():
    import base64
    import hashlib
    import hmac

    payload = b"abcd1234.2000"  # session_id.expires_at, no user
    b64 = lambda data: base64.urlsafe_b64encode(data).rstrip(b"=").decode()  # noqa: E731
    old = f"{b64(payload)}.{b64(hmac.new(KEY, payload, hashlib.sha256).digest())}"
    assert verify_token(KEY, old, now=1001) is None


@pytest.mark.parametrize("bad", ["", "a.b", "../etc", "x" * 65, "has space"])
def test_user_ids_are_checked(bad):
    with pytest.raises(ValueError):
        issue_token(KEY, user_id=bad)


def accounts(settings, mode="required"):
    settings.auth_mode = mode
    settings.supabase_url = "https://project.supabase.test"
    settings.supabase_publishable_key = "sb_publishable_test"


def fake_users(monkeypatch, users: dict[str, SupabaseUser]):
    monkeypatch.setattr(main, "supabase_user", lambda settings, token: users.get(token))


def test_without_accounts_everyone_is_the_local_user(client):
    body = client.post("/api/session").json()
    assert body["user"] == {"id": "local", "email": None, "anonymous": False}
    assert client.get("/api/auth-config").json() == {
        "mode": "off", "supabase_url": None, "publishable_key": None, "access_code": False,
    }


def test_auth_config_is_off_until_supabase_is_set_up(client, settings):
    settings.auth_mode = "required"  # but no Supabase URL or key
    assert client.get("/api/auth-config").json()["mode"] == "off"
    accounts(settings)
    assert client.get("/api/auth-config").json()["publishable_key"] == "sb_publishable_test"


def test_required_mode_needs_a_signed_in_user(client, settings, monkeypatch):
    accounts(settings)
    fake_users(monkeypatch, {"good": SupabaseUser(ALICE, "alice@example.com", False)})
    assert client.post("/api/session").status_code == 401
    assert client.post("/api/session").json()["detail"] == "sign_in_required"
    assert client.post("/api/session", headers={"Authorization": "Bearer revoked"}).status_code == 401

    body = client.post("/api/session", headers={"Authorization": "Bearer good"}).json()
    assert body["user"] == {"id": ALICE, "email": "alice@example.com", "anonymous": False}
    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["id"] == ALICE


def test_guests_and_members_still_need_the_access_code(client, settings, monkeypatch):
    accounts(settings)
    settings.access_code = SecretStr("demo-code")
    fake_users(monkeypatch, {"guest": SupabaseUser(BOB, None, True)})
    response = client.post("/api/session", headers={"Authorization": "Bearer guest"})
    assert response.status_code == 401 and response.json()["detail"] == "access_code_required"
    body = client.post("/api/session", headers={"Authorization": "Bearer guest", "X-Access-Code": "demo-code"}).json()
    assert body["user"]["anonymous"] is True


def test_optional_mode_lets_visitors_in_as_the_local_user(client, settings, monkeypatch):
    accounts(settings, "optional")
    fake_users(monkeypatch, {})
    assert client.post("/api/session").json()["user"]["id"] == "local"


def bearer(settings: Settings, user: str) -> dict[str, str]:
    token, _ = issue_token(settings.signing_key(), user_id=user)
    return {"Authorization": f"Bearer {token}"}


def test_memories_belong_to_one_user(client, settings, tmp_path):
    settings.memory_db_path = str(tmp_path / "m.sqlite3")
    memory_store(settings, ALICE).create(
        MemoryWrite(text="Home city is Lisbon", kind="fact", source="user_utterance",
                    utterance="Remember that my home city is Lisbon.", confidence=0.9)
    )
    alice, bob = bearer(settings, ALICE), bearer(settings, BOB)
    [item] = client.get("/api/memories", headers=alice).json()["items"]
    assert client.get("/api/memories", headers=bob).json()["items"] == []
    assert client.delete(f"/api/memories/{item['id']}", headers=bob).status_code == 404
    assert client.patch(f"/api/memories/{item['id']}", headers=bob, json={"text": "x"}).status_code == 404
    client.delete("/api/memories", headers=bob)  # "forget everything" is Bob's only
    assert len(client.get("/api/memories", headers=alice).json()["items"]) == 1


def test_settings_belong_to_one_user(client, settings, tmp_path):
    settings.settings_path = str(tmp_path / "settings.json")
    alice, bob = bearer(settings, ALICE), bearer(settings, BOB)
    client.patch("/api/settings", headers=alice, json={"tools": {"weather": False}})
    assert client.get("/api/settings", headers=alice).json()["tools"]["weather"]["enabled"] is False
    assert client.get("/api/settings", headers=bob).json()["tools"]["weather"]["enabled"] is True


def test_supabase_user_is_checked_with_supabase():
    settings = Settings(_env_file=None, supabase_url="https://p.supabase.test", supabase_publishable_key="pk")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/user" and request.headers["apikey"] == "pk"
        if request.headers["Authorization"] == "Bearer ok":
            return httpx.Response(200, json={"id": ALICE, "email": "a@example.com", "is_anonymous": False})
        return httpx.Response(401, json={"msg": "invalid JWT"})

    transport = httpx.MockTransport(handler)
    assert supabase_user(settings, "ok", transport) == SupabaseUser(ALICE, "a@example.com", False)
    assert supabase_user(settings, "expired", transport) is None
