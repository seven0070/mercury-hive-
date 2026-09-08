"""Security tests for authentication.

Verifies JWT validation, generic error messages, and no secret leakage.
"""

import time
import uuid

import jwt as pyjwt
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_expired_access_token(client: AsyncClient):
    """Expired access token returns 401."""
    # Create an expired token manually
    now = int(time.time())
    payload = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": now - 600,
        "nbf": now - 600,
        "exp": now - 300,  # Expired 5 minutes ago
        "iss": "mercury-hive",
        "aud": "mercury-hive-api",
    }
    import os

    secret = os.environ.get("JWT_SECRET_KEY", "test-secret-key-for-jwt-signing-only")
    token = pyjwt.encode(payload, secret, algorithm="HS256")

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_no_auth_header(client: AsyncClient):
    """Missing auth header returns 401."""
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_not_in_error_response(client: AsyncClient):
    """Password is never echoed in error responses."""
    password = "my-secret-password-attempt"
    response = await client.post(
        "/auth/login",
        json={"email": "test@test.com", "password": password},
    )
    assert password not in response.text
    assert "password" not in response.text.lower() or "credentials" in response.text.lower()


@pytest.mark.asyncio
async def test_no_signup_endpoint_exists(client: AsyncClient):
    """No signup endpoint exists — 404 or 405."""
    for path in ["/auth/signup", "/auth/register", "/signup", "/register"]:
        response = await client.post(path, json={"email": "a@b.com", "password": "x" * 20})
        assert response.status_code in (404, 405), f"{path} returned {response.status_code}"
