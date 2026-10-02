"""Structured JSON logs (architecture.md 11).

Logs carry metadata only: no audio, no API keys, no transcript text.
Pass context with `extra={"session_id": ..., "turn_id": ...}`.
"""

import json
import logging
import re
import time

CONTEXT_FIELDS = ("session_id", "turn_id", "event", "code", "client")
TOKEN_IN_URL = re.compile(r"(token=)[^&\s\"']+")


class RedactTokens(logging.Filter):
    """Uvicorn logs WebSocket URLs, which carry the session token. Hide it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                TOKEN_IN_URL.sub(r"\1[redacted]", a) if isinstance(a, str) else a
                for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = TOKEN_IN_URL.sub(r"\1[redacted]", record.msg)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": round(time.time(), 3),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        return json.dumps(entry)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("talkback")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactTokens) for f in logger.filters):
            logger.addFilter(RedactTokens())
