"""Integration tests for Phase 3: Agents, Departments, and Scoped Permissions."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_department_and_agent_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of department and agent management."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Verify seeded departments exist
    dept_list_resp = await client.get("/departments", headers=headers)
    assert dept_list_resp.status_code == 200, dept_list_resp.text
    departments = dept_list_resp.json()
    assert len(departments) >= 10
    dept_names = {d["name"] for d in departments}
    assert "Engineering" in dept_names
    assert "Research" in dept_names

    eng_dept = next(d for d in departments if d["name"] == "Engineering")
    eng_dept_id = eng_dept["id"]

    # 2. Propose a new custom department
    new_dept_name = f"Special Projects {uuid.uuid4().hex[:6]}"
    prop_resp = await client.post(
        "/departments/proposals",
        headers=headers,
        json={
            "name": new_dept_name,
            "purpose": "Experimental skunkworks initiative",
            "data_classification": "SECRET",
            "budget": 250000.0,
        },
    )
    assert prop_resp.status_code == 200, prop_resp.text
    proposed_dept = prop_resp.json()
    assert proposed_dept["status"] == "PROPOSED"
    proposed_dept_id = proposed_dept["id"]

    # 3. Owner approves proposed department
    appr_resp = await client.post(
        f"/departments/{proposed_dept_id}/approve",
        headers=headers,
    )
    assert appr_resp.status_code == 200, appr_resp.text
    assert appr_resp.json()["status"] == "ACTIVE"

    # 4. Provision a Manager agent
    manager_resp = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Chief Architect Alpha",
            "role": "DEPARTMENT_MANAGER",
            "department_id": eng_dept_id,
            "persona_source": "SYSTEM_CORE",
            "system_prompt_version": "1.0.0",
        },
    )
    assert manager_resp.status_code == 200, manager_resp.text
    manager = manager_resp.json()
    manager_id = manager["id"]
    assert manager["status"] == "ACTIVE"
    assert manager["role"] == "DEPARTMENT_MANAGER"

    # 5. Provision a Worker agent under that manager
    worker_resp = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Frontend Worker 01",
            "role": "WORKER",
            "department_id": eng_dept_id,
            "manager_id": manager_id,
            "system_prompt_version": "1.0.0",
        },
    )
    assert worker_resp.status_code == 200, worker_resp.text
    worker = worker_resp.json()
    worker_id = worker["id"]

    # 6. Issue a scoped permission grant
    grant_resp = await client.post(
        "/permissions/grant",
        headers=headers,
        json={
            "agent_id": worker_id,
            "department_id": eng_dept_id,
            "allowed_actions": ["READ_CODE", "WRITE_TESTS"],
            "allowed_tools": ["git_cli", "test_runner"],
            "budget_limit": 500.0,
        },
    )
    assert grant_resp.status_code == 200, grant_resp.text
    grant = grant_resp.json()
    grant_id = grant["id"]
    assert grant["allowed_actions"] == ["READ_CODE", "WRITE_TESTS"]

    # 7. List grants for worker
    grants_resp = await client.get(f"/agents/{worker_id}/grants", headers=headers)
    assert grants_resp.status_code == 200
    worker_grants = grants_resp.json()
    assert any(g["id"] == grant_id for g in worker_grants)

    # 8. Suspend worker
    suspend_resp = await client.post(
        f"/agents/{worker_id}/suspend",
        headers=headers,
        json={"reason": "Security investigation"},
    )
    assert suspend_resp.status_code == 200, suspend_resp.text
    assert suspend_resp.json()["status"] == "SUSPENDED"

    # 9. Restore worker
    restore_resp = await client.post(
        f"/agents/{worker_id}/restore",
        headers=headers,
        json={"reason": "Investigation cleared"},
    )
    assert restore_resp.status_code == 200, restore_resp.text
    assert restore_resp.json()["status"] == "ACTIVE"

    # 10. Terminate worker
    term_resp = await client.post(
        f"/agents/{worker_id}/terminate",
        headers=headers,
        json={"reason": "Decommissioned permanently"},
    )
    assert term_resp.status_code == 200, term_resp.text
    assert term_resp.json()["status"] == "TERMINATED"
