"""Integration tests for owner bootstrap."""

import pytest


@pytest.mark.asyncio
async def test_no_signup_endpoint(client):
    """No public signup endpoint exists."""
    response = await client.post(
        "/auth/signup",
        json={"email": "hack@example.com", "password": "trytoregister1234"},
    )
    assert response.status_code in (404, 405)

    response = await client.post(
        "/auth/register",
        json={"email": "hack@example.com", "password": "trytoregister1234"},
    )
    assert response.status_code in (404, 405)
