from app.tokens import TOKEN_TTL_SECONDS, issue_token, verify_token

KEY = b"k" * 48


def test_valid_token_round_trip():
    token, claims = issue_token(KEY, now=1000)
    assert verify_token(KEY, token, now=1001) == claims


def test_expired_token_is_rejected():
    token, _ = issue_token(KEY, now=1000)
    assert verify_token(KEY, token, now=1000 + TOKEN_TTL_SECONDS) is None


def test_token_signed_with_another_key_is_rejected():
    token, _ = issue_token(b"other" * 10, now=1000)
    assert verify_token(KEY, token, now=1001) is None


def test_tampered_expiry_is_rejected():
    import base64

    token, claims = issue_token(KEY, now=1000)
    _, signature = token.split(".")
    forged_payload = f"{claims.session_id}.{claims.expires_at + 10_000}".encode()
    forged = base64.urlsafe_b64encode(forged_payload).rstrip(b"=").decode()
    assert verify_token(KEY, f"{forged}.{signature}", now=1001) is None


def test_malformed_tokens_are_rejected():
    for bad in ["", "abc", "a.b.c", "!!!.???", "a.b"]:
        assert verify_token(KEY, bad, now=1001) is None
