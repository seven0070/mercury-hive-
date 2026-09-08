"""Integration tests for Phase 5: Tool Gateway, Scoped Memory, and Rollback APIs."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tools_memory_and_rollback_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of tool catalog, execution, memory, and rollbacks."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Verify seeded tool catalog
    catalog_res = await client.get("/tools/catalog", headers=headers)
    assert catalog_res.status_code == 200
    tools = catalog_res.json()
    assert len(tools) >= 5
    tool_names = {t["name"] for t in tools}
    assert "file_reader" in tool_names
    assert "file_writer" in tool_names

    # 2. Register a new tool
    reg_tool_res = await client.post(
        "/tools/catalog",
        headers=headers,
        json={
            "name": "custom_linter",
            "description": "Lints and verifies source code syntax",
            "risk_level": "LOW",
            "is_enabled": True,
        },
    )
    assert reg_tool_res.status_code == 200
    assert reg_tool_res.json()["name"] == "custom_linter"

    # 3. Provision an Engineering Worker Agent
    dept_res = await client.get("/departments", headers=headers)
    eng_dept = next(d for d in dept_res.json() if d["name"] == "Engineering")

    agent_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "DevOps Bot Sigma",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert agent_res.status_code == 200
    agent = agent_res.json()
    agent_id = agent["id"]

    # 4. Create a task for DevOps Bot
    task_res = await client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Refactor Infrastructure Config",
            "description": "Update YAML configuration",
            "origin_department_id": eng_dept["id"],
            "assigned_department_id": eng_dept["id"],
            "assigned_agent_id": agent_id,
        },
    )
    assert task_res.status_code == 200
    task_id = task_res.json()["id"]

    # 5. Grant permissions to the agent (file_writer tool + TASK memory scope)
    grant_res = await client.post(
        "/permissions/grant",
        headers=headers,
        json={
            "agent_id": agent_id,
            "allowed_tools": ["file_writer", "custom_linter"],
            "allowed_actions": ["WRITE", "LINT"],
            "memory_scopes": ["TASK", "DEPARTMENT"],
        },
    )
    assert grant_res.status_code == 200

    # 6. Execute tool with automatic rollback generation
    exec_res = await client.post(
        "/tools/execute",
        headers=headers,
        json={
            "tool_name": "file_writer",
            "agent_id": agent_id,
            "task_id": task_id,
            "parameters": {
                "path": "sandbox/helm-chart.yaml",
                "content": "replicas: 3\nimage: nginx:latest",
            },
        },
    )
    assert exec_res.status_code == 200, exec_res.text
    execution = exec_res.json()
    assert execution["status"] == "SUCCESS"
    assert execution["result"]["status"] == "written"

    # 7. Store scoped memory
    mem_res = await client.post(
        f"/memory/{agent_id}",
        headers=headers,
        json={
            "scope": "TASK",
            "scope_id": task_id,
            "key": "deploy_target",
            "value": {"cluster": "production-us-east-1", "namespace": "core"},
        },
    )
    assert mem_res.status_code == 200, mem_res.text
    mem = mem_res.json()
    assert mem["key"] == "deploy_target"
    assert mem["version"] == 1

    # 8. Fetch memory back
    fetch_mem_res = await client.get(
        f"/memory/{agent_id}/TASK/deploy_target?scope_id={task_id}",
        headers=headers,
    )
    assert fetch_mem_res.status_code == 200
    assert fetch_mem_res.json()["value"]["cluster"] == "production-us-east-1"

    # 9. Verify Rollback Artifact was created
    rollbacks_res = await client.get(f"/rollbacks?task_id={task_id}", headers=headers)
    assert rollbacks_res.status_code == 200
    rollbacks = rollbacks_res.json()
    assert len(rollbacks) >= 1
    rollback_id = rollbacks[0]["id"]
    assert rollbacks[0]["status"] == "AVAILABLE"

    # 10. Execute Rollback
    revert_res = await client.post(
        f"/rollbacks/{rollback_id}/execute",
        headers=headers,
        json={"reason": "Config deployment triggered rollback test"},
    )
    assert revert_res.status_code == 200, revert_res.text
    assert revert_res.json()["status"] == "EXECUTED"
    assert revert_res.json()["reverted_at"] is not None
