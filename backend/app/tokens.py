"""Short-lived, HMAC-signed session tokens (SECURITY.md T7).

Format: base64url(session_id.expires_at.user_id.anonymous) + "." +
base64url(hmac_sha256). The user is the Supabase account id, or "local" when
the server has no accounts (AUTH_MODE=off).
The token is the only secret allowed in a URL, and it expires in 15 minutes.
"""

import base64
import hashlib
import hmac
import secrets
import re
import time
from dataclasses import dataclass

TOKEN_TTL_SECONDS = 15 * 60
LOCAL_USER = "local"
USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class SessionClaims:
    session_id: str
    expires_at: int
    user_id: str = LOCAL_USER
    # A guest who signed in with the access code, not an email.
    anonymous: bool = False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def issue_token(
    key: bytes, now: float | None = None, user_id: str = LOCAL_USER, anonymous: bool = False
) -> tuple[str, SessionClaims]:
    if not USER_ID.match(user_id):
        raise ValueError("invalid user id")
    issued = int(now if now is not None else time.time())
    claims = SessionClaims(
        session_id=secrets.token_hex(8), expires_at=issued + TOKEN_TTL_SECONDS, user_id=user_id, anonymous=anonymous
    )
    payload = f"{claims.session_id}.{claims.expires_at}.{user_id}.{int(anonymous)}".encode()
    return f"{_b64(payload)}.{_b64(_sign(key, payload))}", claims


def verify_token(key: bytes, token: str, now: float | None = None) -> SessionClaims | None:
    """Return the claims, or None if the token is malformed, forged or expired."""
    try:
        payload_part, signature_part = token.split(".")
        payload = _unb64(payload_part)
        signature = _unb64(signature_part)
        if not hmac.compare_digest(signature, _sign(key, payload)):
            return None
        session_id, expires_at, user_id, anonymous = payload.decode().split(".")
        if not USER_ID.match(user_id) or anonymous not in ("0", "1"):
            return None
        claims = SessionClaims(
            session_id=session_id, expires_at=int(expires_at), user_id=user_id, anonymous=anonymous == "1"
        )
    except (ValueError, UnicodeDecodeError):
        return None
    current = now if now is not None else time.time()
    return claims if current < claims.expires_at else None
