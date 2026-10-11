"""TalkBack orchestrator: FastAPI app and HTTP routes (architecture.md 2.2)."""

from typing import Annotated

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException

from .auth import Claims, supabase_user
from .protocol import AuthConfig, SessionToken, SessionUser
from .config import Settings, get_settings
from .logs import setup_logging
from .memory_routes import router as memory_router
from .session import router as session_router
from .settings_routes import settings_router, skills_router
from .tokens import LOCAL_USER, issue_token

setup_logging()

app = FastAPI(title="TalkBack orchestrator")
app.include_router(session_router)
app.include_router(memory_router)
app.include_router(settings_router)
app.include_router(skills_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth-config")
def auth_config(settings: Annotated[Settings, Depends(get_settings)]) -> AuthConfig:
    """How this server signs people in. Public: the publishable key is meant for browsers."""
    accounts = settings.auth_mode != "off" and bool(settings.supabase_url and settings.supabase_publishable_key)
    return AuthConfig(
        mode=settings.auth_mode if accounts else "off",
        supabase_url=settings.supabase_url if accounts else None,
        publishable_key=settings.supabase_publishable_key if accounts else None,
        access_code=bool(settings.access_code.get_secret_value()),
    )


@app.post("/api/session")
def create_session(
    settings: Annotated[Settings, Depends(get_settings)],
    x_access_code: Annotated[str, Header(max_length=200)] = "",
    authorization: Annotated[str, Header(max_length=4096)] = "",
) -> SessionToken:
    """Issue a 15-minute token for one WebSocket session (SECURITY.md T7).

    With ACCESS_CODE set, every caller must send it (SECURITY.md T8): sign-up
    is open, so the code is what protects the API credits. With accounts on,
    the caller also sends its Supabase access token, and the session belongs
    to that user. Every REST route and the WebSocket need the session token,
    so this one check gates them all.
    """
    expected = settings.access_code.get_secret_value()
    if expected and not hmac.compare_digest(x_access_code.encode(), expected.encode()):
        raise HTTPException(401, "access_code_required")

    mode = auth_config(settings).mode
    user = SessionUser(id=LOCAL_USER)
    access_token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if mode != "off" and access_token:
        found = supabase_user(settings, access_token)
        if found is None:
            raise HTTPException(401, "sign_in_required")
        user = SessionUser(id=found.id, email=found.email, anonymous=found.anonymous)
    elif mode == "required":
        raise HTTPException(401, "sign_in_required")

    token, claims = issue_token(settings.signing_key(), user_id=user.id, anonymous=user.anonymous)
    return SessionToken(token=token, expires_at=claims.expires_at, user=user)


@app.get("/api/me")
def me(claims: Claims) -> SessionUser:
    """The session's user (the email stays in the browser's Supabase session)."""
    return SessionUser(id=claims.user_id, anonymous=claims.anonymous)


def mount_frontend(application: FastAPI, directory: str) -> None:
    """Serve the built frontend. Added last, so API routes win."""
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    if directory and (Path(directory) / "index.html").is_file():
        application.mount("/", StaticFiles(directory=directory, html=True), name="frontend")


mount_frontend(app, get_settings().frontend_dist)
