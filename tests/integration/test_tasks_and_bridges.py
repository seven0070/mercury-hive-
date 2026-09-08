"""Integration tests for Phase 4: Tasks, Bridges, and Delegation APIs."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tasks_and_bridges_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of department isolation, bridges, and task engine."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Fetch departments (Engineering and Product)
    dept_res = await client.get("/departments", headers=headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    eng_dept = next(d for d in depts if d["name"] == "Engineering")
    prod_dept = next(d for d in depts if d["name"] == "Product")

    # 2. Attempt cross-department task WITHOUT active bridge -> Must Fail
    fail_task_res = await client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Unbridged Feature Spec",
            "description": "Attempting cross-department task without bridge",
            "origin_department_id": eng_dept["id"],
            "assigned_department_id": prod_dept["id"],
        },
    )
    assert fail_task_res.status_code == 400
    assert "requires an active CrossDepartmentBridge" in fail_task_res.text

    # 3. Request a cross-department bridge between Engineering and Product
    bridge_expiry = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    req_bridge_res = await client.post(
        "/bridges",
        headers=headers,
        json={
            "source_department_id": eng_dept["id"],
            "target_department_id": prod_dept["id"],
            "purpose": "Sync technical specifications and acceptance criteria",
            "allowed_data_classification": "INTERNAL",
            "expires_at": bridge_expiry,
        },
    )
    assert req_bridge_res.status_code == 200, req_bridge_res.text
    bridge = req_bridge_res.json()
    assert bridge["status"] == "PENDING"
    bridge_id = bridge["id"]

    # 4. Approve bridge
    appr_bridge_res = await client.post(
        f"/bridges/{bridge_id}/approve",
        headers=headers,
        json={"reason": "Approved collaboration on product spec"},
    )
    assert appr_bridge_res.status_code == 200, appr_bridge_res.text
    assert appr_bridge_res.json()["status"] == "ACTIVE"

    # 5. Create cross-department task WITH active bridge -> Succeeded
    create_task_res = await client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Build Architecture Spec",
            "description": "Draft high-level architecture for real-time telemetry",
            "priority": "HIGH",
            "origin_department_id": eng_dept["id"],
            "assigned_department_id": prod_dept["id"],
            "budget_allocated": 1500.0,
        },
    )
    assert create_task_res.status_code == 200, create_task_res.text
    task = create_task_res.json()
    task_id = task["id"]
    assert task["status"] == "CREATED"
    assert task["priority"] == "HIGH"

    # 6. Provision an agent in the Product department
    prod_agent_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Product Spec Writer",
            "role": "WORKER",
            "department_id": prod_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert prod_agent_res.status_code == 200
    prod_agent = prod_agent_res.json()

    # 7. Assign task to the Product agent
    assign_res = await client.post(
        f"/tasks/{task_id}/assign?agent_id={prod_agent['id']}",
        headers=headers,
    )
    assert assign_res.status_code == 200, assign_res.text
    assert assign_res.json()["status"] == "ASSIGNED"
    assert assign_res.json()["assigned_agent_id"] == prod_agent["id"]

    # 8. Transition task to IN_PROGRESS
    prog_res = await client.post(
        f"/tasks/{task_id}/transition",
        headers=headers,
        json={
            "status": "IN_PROGRESS",
            "reason": "Starting draft of specification",
        },
    )
    assert prog_res.status_code == 200
    assert prog_res.json()["status"] == "IN_PROGRESS"

    # 9. Transition task to COMPLETED with artifacts
    comp_res = await client.post(
        f"/tasks/{task_id}/transition",
        headers=headers,
        json={
            "status": "COMPLETED",
            "reason": "Spec drafted, verified, and signed off",
            "output_artifacts": {"spec_doc_url": "s3://artifacts/spec_v1.pdf"},
        },
    )
    assert comp_res.status_code == 200
    comp_task = comp_res.json()
    assert comp_task["status"] == "COMPLETED"
    assert comp_task["completed_at"] is not None
    assert comp_task["output_artifacts"]["spec_doc_url"] == "s3://artifacts/spec_v1.pdf"
