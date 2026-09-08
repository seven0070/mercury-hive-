"""Integration tests for emergency shutdown, owner override, and dashboard."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_emergency_shutdown_lifecycle(client: AsyncClient, auth_tokens: dict):
    """Owner can trigger emergency shutdown, inspect dashboard, and override back to normal."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Trigger emergency shutdown
    response = await client.post(
        "/owner/emergency-shutdown",
        headers=headers,
        json={"reason": "Suspected anomalous worker activity detected"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["run_state"] == "EMERGENCY_SHUTDOWN"
    assert data["shutdown_reason"] == "Suspected anomalous worker activity detected"

    # 2. Inspect owner dashboard
    dash_resp = await client.get("/owner/dashboard", headers=headers)
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["system_run_state"] == "EMERGENCY_SHUTDOWN"
    assert dash["shutdown_reason"] == "Suspected anomalous worker activity detected"

    # 3. Owner override to restore normal state
    override_resp = await client.post(
        "/owner/override",
        headers=headers,
        json={
            "target_state": "NORMAL",
            "reason": "Investigation completed, system clear",
        },
    )
    assert override_resp.status_code == 200
    res = override_resp.json()
    assert res["run_state"] == "NORMAL"
    assert res["shutdown_reason"] is None

    # 4. Verify dashboard is back to NORMAL
    dash_resp2 = await client.get("/owner/dashboard", headers=headers)
    assert dash_resp2.status_code == 200
    assert dash_resp2.json()["system_run_state"] == "NORMAL"
