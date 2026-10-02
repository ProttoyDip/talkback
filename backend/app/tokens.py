"""Short-lived, HMAC-signed session tokens (SECURITY.md T7).

Format: base64url(session_id.expires_at) + "." + base64url(hmac_sha256).
The token is the only secret allowed in a URL, and it expires in 15 minutes.
"""

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

TOKEN_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class SessionClaims:
    session_id: str
    expires_at: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def issue_token(key: bytes, now: float | None = None) -> tuple[str, SessionClaims]:
    issued = int(now if now is not None else time.time())
    claims = SessionClaims(session_id=secrets.token_hex(8), expires_at=issued + TOKEN_TTL_SECONDS)
    payload = f"{claims.session_id}.{claims.expires_at}".encode()
    return f"{_b64(payload)}.{_b64(_sign(key, payload))}", claims


def verify_token(key: bytes, token: str, now: float | None = None) -> SessionClaims | None:
    """Return the claims, or None if the token is malformed, forged or expired."""
    try:
        payload_part, signature_part = token.split(".")
        payload = _unb64(payload_part)
        signature = _unb64(signature_part)
        if not hmac.compare_digest(signature, _sign(key, payload)):
            return None
        session_id, expires_at = payload.decode().split(".")
        claims = SessionClaims(session_id=session_id, expires_at=int(expires_at))
    except (ValueError, UnicodeDecodeError):
        return None
    current = now if now is not None else time.time()
    return claims if current < claims.expires_at else None
