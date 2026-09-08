"""Integration tests for Phase 9: Owner Console Aggregator API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_owner_console_summary_endpoint(client: AsyncClient, auth_tokens: dict):
    """Test the /owner/console/summary endpoint returns complete operational metrics."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    res = await client.get("/owner/console/summary", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "system_run_state" in data
    assert "pending_approvals_count" in data
    assert "active_agents_count" in data
    assert "departments_count" in data
    assert "active_tasks_count" in data
    assert "active_bridges_count" in data
    assert "evolution_candidates_count" in data
    assert "recent_audit_count" in data
    assert "constitution_hash" in data
