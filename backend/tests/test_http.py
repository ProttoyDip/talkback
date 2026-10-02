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


def test_built_frontend_is_served_when_configured(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import mount_frontend

    (tmp_path / "index.html").write_text("<h1>TalkBack</h1>")
    application = FastAPI()

    @application.get("/health")
    def health():
        return {"status": "ok"}

    mount_frontend(application, str(tmp_path))
    with TestClient(application) as c:
        assert c.get("/").text == "<h1>TalkBack</h1>"
        assert c.get("/health").json() == {"status": "ok"}  # API routes still win
