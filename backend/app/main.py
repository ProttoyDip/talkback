"""TalkBack orchestrator: FastAPI app and HTTP routes (architecture.md 2.2)."""

from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .config import Settings, get_settings
from .logs import setup_logging
from .session import router as session_router
from .tokens import issue_token

setup_logging()

app = FastAPI(title="TalkBack orchestrator")
app.include_router(session_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class SessionToken(BaseModel):
    token: str
    expires_at: int


@app.post("/api/session")
def create_session(settings: Annotated[Settings, Depends(get_settings)]) -> SessionToken:
    """Issue a 15-minute token for one WebSocket session (SECURITY.md T7)."""
    token, claims = issue_token(settings.signing_key())
    return SessionToken(token=token, expires_at=claims.expires_at)
