"""Unit tests for JWT access tokens and refresh token utilities."""

import time
import uuid

import jwt as pyjwt
import pytest

from services.identity.tokens import (
    TokenError,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    validate_access_token,
)

SECRET = "test-secret-key-for-testing-at-least-32-bytes-long"
OWNER_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()


def test_create_and_validate_access_token():
    """Create and validate an access token."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET)
    claims = validate_access_token(token, SECRET)
    assert claims.sub == OWNER_ID
    assert claims.sid == SESSION_ID
    assert claims.token_type == "access"
    assert claims.iss == "mercury-hive"
    assert claims.aud == "mercury-hive-api"


def test_expired_token_rejected():
    """Expired token raises TokenError."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET, expires_minutes=-1)
    with pytest.raises(TokenError, match="expired"):
        validate_access_token(token, SECRET)


def test_wrong_secret_rejected():
    """Token signed with different secret is rejected."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET)
    with pytest.raises(TokenError):
        validate_access_token(token, "different-secret-also-at-least-32-bytes-long")


def test_wrong_issuer_rejected():
    """Token with wrong issuer is rejected."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET, issuer="wrong-issuer")
    with pytest.raises(TokenError, match="issuer"):
        validate_access_token(token, SECRET)


def test_wrong_audience_rejected():
    """Token with wrong audience is rejected."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET, audience="wrong-audience")
    with pytest.raises(TokenError, match="audience"):
        validate_access_token(token, SECRET)


def test_wrong_algorithm_rejected():
    """Token signed with different algorithm is rejected."""
    payload = {"sub": str(OWNER_ID), "type": "access"}
    token = pyjwt.encode(payload, SECRET, algorithm="HS384")
    with pytest.raises(TokenError):
        validate_access_token(token, SECRET)


def test_missing_claims_rejected():
    """Token with missing required claims is rejected."""
    payload = {"sub": str(OWNER_ID)}  # Missing sid, jti, type, etc.
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(TokenError):
        validate_access_token(token, SECRET)


def test_invalid_uuid_claims_rejected():
    """Token with non-UUID sub/sid/jti is rejected."""
    now = int(time.time())
    payload = {
        "sub": "not-a-uuid",
        "sid": str(SESSION_ID),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "iss": "mercury-hive",
        "aud": "mercury-hive-api",
    }
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(TokenError, match="uuid"):
        validate_access_token(token, SECRET)


def test_tampered_token_rejected():
    """Tampered token is rejected."""
    token = create_access_token(OWNER_ID, SESSION_ID, SECRET)
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(TokenError):
        validate_access_token(tampered, SECRET)


def test_refresh_token_generation():
    """Refresh token is 64 hex chars (32 bytes)."""
    token = generate_refresh_token()
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_refresh_token_hash_deterministic():
    """Same refresh token produces same hash."""
    token = generate_refresh_token()
    h1 = hash_refresh_token(token)
    h2 = hash_refresh_token(token)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex
