"""TalkBack orchestrator: FastAPI app and HTTP routes (architecture.md 2.2)."""

from typing import Annotated

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import Settings, get_settings
from .logs import setup_logging
from .memory_routes import router as memory_router
from .session import router as session_router
from .settings_routes import settings_router, skills_router
from .tokens import issue_token

setup_logging()

app = FastAPI(title="TalkBack orchestrator")
app.include_router(session_router)
app.include_router(memory_router)
app.include_router(settings_router)
app.include_router(skills_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class SessionToken(BaseModel):
    token: str
    expires_at: int


@app.post("/api/session")
def create_session(
    settings: Annotated[Settings, Depends(get_settings)],
    x_access_code: Annotated[str, Header(max_length=200)] = "",
) -> SessionToken:
    """Issue a 15-minute token for one WebSocket session (SECURITY.md T7).

    With ACCESS_CODE set, the caller must send it (SECURITY.md T8). Every REST
    route and the WebSocket need a token, so this one check gates them all.
    """
    expected = settings.access_code.get_secret_value()
    if expected and not hmac.compare_digest(x_access_code.encode(), expected.encode()):
        raise HTTPException(401, "access_code_required")
    token, claims = issue_token(settings.signing_key())
    return SessionToken(token=token, expires_at=claims.expires_at)


def mount_frontend(application: FastAPI, directory: str) -> None:
    """Serve the built frontend. Added last, so API routes win."""
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    if directory and (Path(directory) / "index.html").is_file():
        application.mount("/", StaticFiles(directory=directory, html=True), name="frontend")


mount_frontend(app, get_settings().frontend_dist)
