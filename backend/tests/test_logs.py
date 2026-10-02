import logging

from app.logs import RedactTokens


def test_session_token_is_redacted_from_uvicorn_logs():
    record = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", "/ws/session?token=abc.def"),
        None,
    )
    RedactTokens().filter(record)
    message = record.getMessage()
    assert "abc.def" not in message
    assert "token=[redacted]" in message
