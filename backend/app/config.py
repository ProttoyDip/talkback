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
    memory_db_path: str = "data/memories.sqlite3"

    # Which voice engine serves sessions: "cascade" (plan B), "fake" (X1),
    # "voicechat" (X7), or "none" (accept audio, no replies).
    voice_engine: str = "cascade"

    # Plan B speech: NVIDIA API catalog (build.nvidia.com), Riva gRPC.
    # Function IDs and voice come from NVIDIA's model pages; change them here
    # if NVIDIA updates the catalog.
    nvidia_api_key: SecretStr = SecretStr("")
    riva_server: str = "grpc.nvcf.nvidia.com:443"
    asr_function_id: str = "d8dd4e9b-fbf5-4fb0-9dba-8cf436c8d965"  # parakeet-ctc-0.6b-asr
    tts_function_id: str = "877104f7-e885-42b9-8de8-f6e4c6303969"  # magpie-tts-multilingual
    tts_voice: str = "Magpie-Multilingual.EN-US.Leo"
    # Silence (ms) before the recognizer decides the user has finished.
    # Lower is faster but may cut slow speakers off; tune with the eval set.
    asr_stop_history_ms: int = 500

    # Spoken replies: Nemotron 3 Nano. Nebius first, OpenRouter as backup.
    nebius_llm_model: str = "nvidia/nvidia-nemotron-3-nano-30b-a3b"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_llm_model: str = "nvidia/nemotron-3-nano-30b-a3b"

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
