"""Integration tests for approval records lifecycle."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_approval_lifecycle(client: AsyncClient, auth_tokens: dict):
    """Create approval, verify list, approve, and verify state transition."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Create a pending approval
    req_by = str(uuid.uuid4())
    create_resp = await client.post(
        "/approvals",
        headers=headers,
        json={
            "action_type": "deploy_new_tool",
            "requested_by": req_by,
            "risk_level": "HIGH",
            "reason": "Requesting tool activation for Research department",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    approval = create_resp.json()
    approval_id = approval["id"]
    assert approval["status"] == "PENDING"
    assert approval["risk_level"] == "HIGH"

    # 2. List approvals, verify item is present
    list_resp = await client.get("/approvals?status=PENDING", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(item["id"] == approval_id for item in items)

    # 3. Owner approves request
    approve_resp = await client.post(
        f"/approvals/{approval_id}/approve",
        headers=headers,
        json={"reason": "Approved after reviewing sandboxed test results"},
    )
    assert approve_resp.status_code == 200
    decided = approve_resp.json()
    assert decided["status"] == "APPROVED"
    assert decided["decision"] == "APPROVED"
    assert decided["decided_at"] is not None

    # 4. Attempting to approve again fails (must be PENDING)
    double_resp = await client.post(
        f"/approvals/{approval_id}/approve",
        headers=headers,
        json={"reason": "Attempting redundant approval"},
    )
    assert double_resp.status_code == 400
