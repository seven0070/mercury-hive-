"""Integration tests for authentication flows.

Tests run against the isolated test database with pre-created owner.
All auth failures must return generic 401.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_OWNER_EMAIL, TEST_OWNER_PASSWORD


@pytest.mark.asyncio
async def test_successful_login(client: AsyncClient):
    """Successful login returns access + refresh tokens."""
    response = await client.post(
        "/auth/login",
        json={"email": TEST_OWNER_EMAIL, "password": TEST_OWNER_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 300  # 5 minutes


@pytest.mark.asyncio
async def test_wrong_password_returns_401(client: AsyncClient):
    """Wrong password returns generic 401."""
    response = await client.post(
        "/auth/login",
        json={"email": TEST_OWNER_EMAIL, "password": "wrong-password-here!!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_unknown_owner_returns_401(client: AsyncClient):
    """Unknown email returns generic 401 (same as wrong password)."""
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "any-password-here!!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_refresh_rotation(client: AsyncClient, auth_tokens: dict):
    """Refresh rotation returns new valid tokens."""
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": auth_tokens["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # New tokens should be different
    assert data["refresh_token"] != auth_tokens["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_replay_revokes_session(client: AsyncClient, auth_tokens: dict):
    """Replaying an already-used refresh token revokes the session."""
    old_refresh = auth_tokens["refresh_token"]

    # First refresh succeeds
    r1 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200

    # Replay the old token — session should be revoked
    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401

    # Even the new token from r1 should now be invalid (session revoked)
    new_refresh = r1.json()["refresh_token"]
    r3 = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient, auth_tokens: dict):
    """Logout revokes the session. Refresh token becomes invalid."""
    access = auth_tokens["access_token"]
    refresh = auth_tokens["refresh_token"]

    # Logout
    response = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 204

    # Refresh should fail (session revoked)
    r = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, auth_tokens: dict):
    """GET /auth/me returns owner profile without sensitive fields."""
    access = auth_tokens["access_token"]
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_OWNER_EMAIL
    assert data["status"] == "ACTIVE"
    assert "password_hash" not in data
    assert "password" not in data
