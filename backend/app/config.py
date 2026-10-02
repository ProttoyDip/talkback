"""Settings loaded from environment variables or backend/.env (SECURITY.md T6)."""

import logging
import secrets
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("talkback.config")

MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    session_secret: SecretStr = SecretStr("")
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    nebius_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    voicechat_url: str = ""

    @field_validator("session_secret")
    @classmethod
    def secret_long_enough(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw and len(raw) < MIN_SECRET_LENGTH:
            raise ValueError(f"SESSION_SECRET must be at least {MIN_SECRET_LENGTH} characters")
        return value

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(o.strip() for o in self.allowed_origins.split(",") if o.strip())

    def signing_key(self) -> bytes:
        return self.session_secret.get_secret_value().encode()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.session_secret.get_secret_value():
        # Fine for local development; tokens stop working after a restart.
        log.warning("SESSION_SECRET is empty; using a random secret for this process")
        settings.session_secret = SecretStr(secrets.token_urlsafe(48))
    return settings
