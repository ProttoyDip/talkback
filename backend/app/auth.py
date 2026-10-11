"""Who is calling: Supabase sign-in for POST /api/session, session tokens after.

The browser signs in with Supabase Auth (email link, or a guest with the
access code) and sends its Supabase access token only to POST /api/session.
The server checks it with Supabase (GET /auth/v1/user), so a revoked user
fails at once and no JWT library is needed. Every other route and the
WebSocket use the short session token that carries the user id.
"""

import logging
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .tokens import USER_ID, SessionClaims, verify_token

log = logging.getLogger("talkback.auth")
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class SupabaseUser:
    id: str
    email: str | None
    anonymous: bool


def supabase_user(
    settings: Settings, access_token: str, transport: httpx.BaseTransport | None = None
) -> SupabaseUser | None:
    """The signed-in Supabase user, or None if the token is not valid (or Supabase is down)."""
    key = settings.supabase_publishable_key or settings.supabase_secret_key.get_secret_value()
    if not (settings.supabase_url and key and access_token):
        return None
    try:
        with httpx.Client(timeout=5, follow_redirects=False, transport=transport) as client:
            response = client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError:
        log.warning("supabase auth not reachable")
        return None
    if response.status_code != 200:
        return None
    body = response.json()
    user_id = str(body.get("id", ""))
    if not USER_ID.match(user_id):
        return None
    email = body.get("email") or None
    return SupabaseUser(id=user_id, email=email, anonymous=bool(body.get("is_anonymous", False)))


def session_claims(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessionClaims:
    """REST routes: the session token from Authorization: Bearer, with its user."""
    claims = verify_token(settings.signing_key(), credentials.credentials) if credentials else None
    if claims is None:
        raise HTTPException(401, "Invalid or expired session token", headers={"WWW-Authenticate": "Bearer"})
    return claims


Claims = Annotated[SessionClaims, Depends(session_claims)]
