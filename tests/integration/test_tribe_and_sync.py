"""Integration tests for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tribe_adapter_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of department-tribe mapping, skill certification,

    and external task ingestion.
    """
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Fetch departments
    dept_res = await client.get("/departments", headers=headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    eng_dept = next(d for d in depts if d["name"] == "Engineering")

    # 2. Map Department to External Tribe / Squad
    map_res = await client.post(
        "/tribe/mappings",
        headers=headers,
        json={
            "department_id": eng_dept["id"],
            "tribe_name": "Autonomous Core",
            "squad_name": "Distributed Mesh Squad",
            "external_team_id": "ext_squad_999",
        },
    )
    assert map_res.status_code == 200
    mapping = map_res.json()
    assert mapping["tribe_name"] == "Autonomous Core"
    assert mapping["squad_name"] == "Distributed Mesh Squad"
    assert mapping["sync_status"] == "SYNCED"

    # 3. List Tribe Mappings
    list_map_res = await client.get(
        f"/tribe/mappings?department_id={eng_dept['id']}",
        headers=headers,
    )
    assert list_map_res.status_code == 200
    assert len(list_map_res.json()) >= 1

    # 4. Provision Agent in Department
    agent_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Mesh Systems Specialist",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert agent_res.status_code == 200
    agent_id = agent_res.json()["id"]

    # 5. Register Skill in Skill Matrix
    skill_res = await client.post(
        f"/tribe/skills/{agent_id}",
        headers=headers,
        json={
            "skill_name": "Gossip Protocol Optimization",
            "proficiency_level": "EXPERT",
        },
    )
    assert skill_res.status_code == 200
    skill = skill_res.json()
    skill_id = skill["id"]
    assert skill["proficiency_level"] == "EXPERT"
    assert not skill["is_verified"]

    # 6. Verify Agent Skill (as Owner)
    verify_res = await client.post(
        f"/tribe/skills/{skill_id}/verify",
        headers=headers,
        json={"is_verified": True},
    )
    assert verify_res.status_code == 200
    verified_skill = verify_res.json()
    assert verified_skill["is_verified"] is True
    assert verified_skill["verified_by"] is not None

    # 7. List Agent Skills
    list_skills_res = await client.get(
        f"/tribe/skills/{agent_id}",
        headers=headers,
    )
    assert list_skills_res.status_code == 200
    assert len(list_skills_res.json()) >= 1

    # 8. Ingest External Task (e.g. from JIRA or GitHub)
    ingest_res = await client.post(
        "/tribe/tasks/ingest",
        headers=headers,
        json={
            "external_system": "JIRA",
            "external_task_id": "HIVE-1024",
            "title": "Mitigate network partition flapping in cluster gossip",
            "description": "Observed flapping under high packet drop simulation.",
            "department_id": eng_dept["id"],
            "priority": "CRITICAL",
        },
    )
    assert ingest_res.status_code == 200
    sync_mapping = ingest_res.json()
    assert sync_mapping["external_system"] == "JIRA"
    assert sync_mapping["external_task_id"] == "HIVE-1024"
    assert sync_mapping["sync_direction"] == "INBOUND"

    # 9. List Task Sync Mappings
    list_sync_res = await client.get(
        f"/tribe/tasks/sync?task_id={sync_mapping['task_id']}",
        headers=headers,
    )
    assert list_sync_res.status_code == 200
    assert len(list_sync_res.json()) == 1
