import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

ORIGIN = "http://localhost:5173"
SECRET = "test-secret-" + "x" * 40


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, session_secret=SECRET, allowed_origins=ORIGIN, voice_engine="none")


@pytest.fixture
def client(settings: Settings):
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def token(client: TestClient) -> str:
    return client.post("/api/session").json()["token"]
