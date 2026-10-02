import time

from app.tokens import TOKEN_TTL_SECONDS


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_token_expires_in_15_minutes(client):
    body = client.post("/api/session").json()
    assert body["token"]
    assert abs(body["expires_at"] - (time.time() + TOKEN_TTL_SECONDS)) < 5


def test_session_tokens_are_unique(client):
    first = client.post("/api/session").json()["token"]
    second = client.post("/api/session").json()["token"]
    assert first != second
