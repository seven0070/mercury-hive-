"""Unit tests for production authentication hardening.

Tests rate limiting, TOTP MFA, and session management.
"""

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import RuntimeSettings
from apps.api.dependencies import get_audit_engine, get_db, get_settings
from domain.models.base import Base
from domain.models.owner import Owner
from domain.models.refresh_token import RefreshToken
from domain.models.session import OwnerSession
from services.identity.hashing import hash_password
from services.identity.rate_limiter import (
    SlidingWindowRateLimiter,
    login_rate_limiter,
    refresh_rate_limiter,
)
from services.identity.router import router as auth_router
from services.identity.totp import (
    generate_totp_code,
    generate_totp_secret,
    verify_totp_code,
)

# Test constants
TEST_EMAIL = "owner@mercury-hive.test"
TEST_PASSWORD = "test-owner-secure-password-16"
TEST_JWT_SECRET = "test-jwt-secret-key-must-be-at-least-32-bytes-long!"


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    """Rate limiter allows requests under limit and blocks with 429 when exceeded."""
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=10)
    key = "test_ip_127.0.0.1"

    # First 3 attempts are allowed
    for _ in range(3):
        await limiter.check(key)
        await limiter.record_attempt(key)

    # 4th attempt is blocked with 429
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(key)
    assert exc_info.value.status_code == 429
    assert "Too many attempts" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers

    # Reset allows immediate next attempt
    await limiter.reset(key)
    await limiter.check(key)


def test_totp_generation_and_verification():
    """Valid TOTP code generated from secret passes verification with clock tolerance."""
    secret = generate_totp_secret()
    now = time.time()

    code = generate_totp_code(secret, timestamp=now)
    assert len(code) == 6
    assert code.isdigit()

    # Exact timestamp verifies
    assert verify_totp_code(secret, code, timestamp=now) is True

    # Clock drift within 1 window (+25s) verifies
    assert verify_totp_code(secret, code, timestamp=now + 25) is True

    # Clock drift within -1 window (-25s) verifies
    assert verify_totp_code(secret, code, timestamp=now - 25) is True

    # Large clock drift (> 60s) fails
    assert verify_totp_code(secret, code, timestamp=now + 75) is False

    # Invalid code fails
    assert verify_totp_code(secret, "000000", timestamp=now) is False


# ---------------------------------------------------------------------------
# Fixtures for end-to-end API hardening tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def reset_rate_limiters():
    """Ensure rate limiters are completely cleared before and after each test."""
    await login_rate_limiter.clear_all()
    await refresh_rate_limiter.clear_all()
    yield
    await login_rate_limiter.clear_all()
    await refresh_rate_limiter.clear_all()


@pytest.fixture
def test_settings() -> RuntimeSettings:
    """Settings instance configured for tests."""
    return RuntimeSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key=TEST_JWT_SECRET,
        jwt_algorithm="HS256",
        jwt_issuer="mercury-hive",
        jwt_audience="mercury-hive-api",
        jwt_access_token_minutes=5,
        jwt_refresh_token_hours=24,
        jwt_session_days=7,
        owner_mfa_enabled=False,
        owner_mfa_secret=None,
    )


@pytest.fixture
async def auth_test_context(test_settings: RuntimeSettings):
    """Isolated in-memory database and FastAPI client for auth hardening verification."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: Base.metadata.create_all(
                sc, tables=[Owner.__table__, OwnerSession.__table__, RefreshToken.__table__]
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid.uuid4()
    pw_hash = hash_password(TEST_PASSWORD)

    async with session_factory() as session:
        owner = Owner(
            id=owner_id,
            email=TEST_EMAIL,
            password_hash=pw_hash,
            status="ACTIVE",
            singleton=True,
            created_at=datetime.now(UTC),
        )
        session.add(owner)
        await session.commit()

    app = FastAPI()
    app.include_router(auth_router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_audit_engine] = lambda: engine

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield {
            "client": client,
            "owner_id": owner_id,
            "session_factory": session_factory,
            "settings": test_settings,
        }

    await engine.dispose()


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_rate_limiting_exceeded(auth_test_context):
    """Brute force requests to /auth/login (>5 failed attempts in 1 min) return HTTP 429."""
    client = auth_test_context["client"]
    target_ip = "203.0.113.10"

    # First 5 failed attempts return 401
    for attempt in range(1, 6):
        response = await client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": "wrong-password"},
            headers={"X-Forwarded-For": target_ip},
        )
        assert response.status_code == 401, (
            f"Attempt {attempt} expected 401, got {response.status_code}"
        )
        assert response.json()["detail"] == "Invalid credentials"

    # 6th attempt from the same IP must be rate-limited with HTTP 429
    res_blocked = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": "wrong-password"},
        headers={"X-Forwarded-For": target_ip},
    )
    assert res_blocked.status_code == 429
    assert "Too many attempts" in res_blocked.json()["detail"]
    assert "Retry-After" in res_blocked.headers
    retry_after = int(res_blocked.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    # A different IP is NOT blocked
    res_other_ip = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert res_other_ip.status_code == 401


@pytest.mark.asyncio
async def test_login_success_resets_rate_limiter(auth_test_context):
    """Successful login resets failed attempt counter for the client IP."""
    client = auth_test_context["client"]
    target_ip = "203.0.113.20"

    # 4 failed attempts from target IP
    for _ in range(4):
        res = await client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": "wrong-password"},
            headers={"X-Forwarded-For": target_ip},
        )
        assert res.status_code == 401

    # Successful login resets the rate limiter window for target IP
    res_success = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"X-Forwarded-For": target_ip},
    )
    assert res_success.status_code == 200
    assert "access_token" in res_success.json()

    # The client can now make up to 5 more failed attempts before getting 429
    for attempt in range(1, 6):
        res = await client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": "wrong-password"},
            headers={"X-Forwarded-For": target_ip},
        )
        assert res.status_code == 401, f"Attempt {attempt} after reset should be 401"

    # 6th attempt after reset is blocked
    res_blocked = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": "wrong-password"},
        headers={"X-Forwarded-For": target_ip},
    )
    assert res_blocked.status_code == 429


@pytest.mark.asyncio
async def test_refresh_rate_limiting(auth_test_context):
    """Rate limiting on /auth/refresh returns 429 when max attempts exceeded."""
    client = auth_test_context["client"]
    target_ip = "203.0.113.30"

    # Send 20 failed refresh attempts
    for attempt in range(1, 21):
        res = await client.post(
            "/auth/refresh",
            json={"refresh_token": f"invalid-refresh-token-{attempt}"},
            headers={"X-Forwarded-For": target_ip},
        )
        assert res.status_code == 401, f"Attempt {attempt} expected 401, got {res.status_code}"

    # 21st attempt exceeds limit (20) and triggers HTTP 429
    res_blocked = await client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid-refresh-token-21"},
        headers={"X-Forwarded-For": target_ip},
    )
    assert res_blocked.status_code == 429
    assert "Retry-After" in res_blocked.headers


# ---------------------------------------------------------------------------
# TOTP MFA Verification Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_totp_mfa_verification_when_enabled(auth_test_context):
    """When MFA is enabled, owner login requires valid TOTP code; rejects invalid or missing."""
    client = auth_test_context["client"]
    settings = auth_test_context["settings"]

    # Configure TOTP MFA on settings
    totp_secret = generate_totp_secret()
    settings.owner_mfa_enabled = True
    settings.owner_mfa_secret = totp_secret

    # 1. Login with correct password but missing TOTP code -> 401
    res_missing = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert res_missing.status_code == 401
    assert res_missing.json()["detail"] == "Invalid credentials"

    # 2. Login with correct password but invalid TOTP code -> 401
    res_invalid = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "totp_code": "000000"},
    )
    assert res_invalid.status_code == 401
    assert res_invalid.json()["detail"] == "Invalid credentials"

    # 3. Login with correct password and valid TOTP code -> 200
    valid_code = generate_totp_code(totp_secret)
    res_valid = await client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "totp_code": valid_code},
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 300


# ---------------------------------------------------------------------------
# Active Session Management & Revocation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_session_listing(auth_test_context):
    """GET /auth/sessions lists active non-revoked sessions with is_current indicator."""
    client = auth_test_context["client"]

    # Unauthenticated call returns 401
    res_unauth = await client.get("/auth/sessions")
    assert res_unauth.status_code == 401

    # Login 1 (Session 1)
    res_login1 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert res_login1.status_code == 200

    # Login 2 (Session 2)
    res_login2 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert res_login2.status_code == 200
    token2 = res_login2.json()["access_token"]

    # List sessions using Session 2 token
    res_sessions = await client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_sessions.status_code == 200
    sessions = res_sessions.json()
    assert len(sessions) == 2

    # Verify session schemas and current flag
    current_count = sum(1 for s in sessions if s["is_current"])
    other_count = sum(1 for s in sessions if not s["is_current"])
    assert current_count == 1
    assert other_count == 1
    for s in sessions:
        assert "id" in s
        assert "created_at" in s
        assert "expires_at" in s


@pytest.mark.asyncio
async def test_single_session_revocation_invalidates_refresh(auth_test_context):
    """Revoking a session immediately causes subsequent /auth/refresh to return 401."""
    client = auth_test_context["client"]

    # Login 1 (Session 1)
    res1 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    t1 = res1.json()

    # Login 2 (Session 2)
    res2 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    t2 = res2.json()

    # Get sessions to find Session 1 ID
    res_sess = await client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
    )
    sessions = res_sess.json()
    sess_1 = next(s for s in sessions if not s["is_current"])

    # Revoke Session 1
    res_del = await client.delete(
        f"/auth/sessions/{sess_1['id']}",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
    )
    assert res_del.status_code == 204

    # Subsequent /auth/refresh for Session 1 must immediately fail with 401
    res_ref1 = await client.post(
        "/auth/refresh",
        json={"refresh_token": t1["refresh_token"]},
    )
    assert res_ref1.status_code == 401
    assert res_ref1.json()["detail"] == "Invalid credentials"

    # Session 2 refresh token remains fully functional
    res_ref2 = await client.post(
        "/auth/refresh",
        json={"refresh_token": t2["refresh_token"]},
    )
    assert res_ref2.status_code == 200
    assert "access_token" in res_ref2.json()

    # Revoking an already-revoked or non-existent session returns 404
    fake_id = uuid.uuid4()
    res_fake = await client.delete(
        f"/auth/sessions/{fake_id}",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
    )
    assert res_fake.status_code == 404


@pytest.mark.asyncio
async def test_revoke_all_sessions_endpoints(auth_test_context):
    """DELETE /auth/sessions revokes all sessions (or others if include_current=False)."""
    client = auth_test_context["client"]

    # Create 3 sessions
    res1 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    t1 = res1.json()

    res2 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    t2 = res2.json()

    res3 = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    t3 = res3.json()

    # Revoke other sessions (include_current=False, default)
    res_del_others = await client.delete(
        "/auth/sessions?include_current=false",
        headers={"Authorization": f"Bearer {t3['access_token']}"},
    )
    assert res_del_others.status_code == 200
    assert res_del_others.json()["revoked_count"] == 2

    # Sessions 1 and 2 refresh tokens are immediately revoked
    assert (
        await client.post("/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post("/auth/refresh", json={"refresh_token": t2["refresh_token"]})
    ).status_code == 401

    # Session 3 refresh token remains valid
    res_ref3 = await client.post(
        "/auth/refresh", json={"refresh_token": t3["refresh_token"]}
    )
    assert res_ref3.status_code == 200
    t3_new = res_ref3.json()

    # Now revoke all sessions including current (include_current=True)
    res_del_all = await client.delete(
        "/auth/sessions?include_current=true",
        headers={"Authorization": f"Bearer {t3_new['access_token']}"},
    )
    assert res_del_all.status_code == 200
    assert res_del_all.json()["revoked_count"] == 1

    # Session 3 refresh token is now also revoked
    assert (
        await client.post(
            "/auth/refresh", json={"refresh_token": t3_new["refresh_token"]}
        )
    ).status_code == 401

