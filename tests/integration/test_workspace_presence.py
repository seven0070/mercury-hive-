"""Integration tests for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workspace_presence_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of 3D office zones, avatar attire governance,

    spatial presence telemetry, and virtual boardroom meetings.
    """
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Fetch departments to bind pod
    dept_res = await client.get("/departments", headers=headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    eng_dept = next(d for d in depts if d["name"] == "Engineering")

    # 2. Create Workspace Zone (Department Pod)
    zone_res = await client.post(
        "/workspace/zones",
        headers=headers,
        json={
            "name": "Engineering Alpha Pod",
            "zone_type": "DEPARTMENT_POD",
            "department_id": eng_dept["id"],
            "capacity": 15,
            "security_level": "RESTRICTED",
            "spatial_bounds": {
                "min": [10.0, 0.0, 10.0],
                "max": [25.0, 5.0, 25.0],
            },
        },
    )
    assert zone_res.status_code == 200
    zone = zone_res.json()
    assert zone["name"] == "Engineering Alpha Pod"
    assert zone["zone_type"] == "DEPARTMENT_POD"
    zone_id = zone["id"]

    # 3. List Workspace Zones
    list_zones_res = await client.get("/workspace/zones", headers=headers)
    assert list_zones_res.status_code == 200
    assert len(list_zones_res.json()) >= 1

    # 4. Provision Agent in Engineering
    agent_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Workspace Architect Bot",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert agent_res.status_code == 200
    agent_id = agent_res.json()["id"]

    # 5. Attire Hierarchy Enforcement: Worker cannot wear EXECUTIVE_FORMAL
    bad_avatar_res = await client.post(
        "/workspace/avatars",
        headers=headers,
        json={
            "agent_id": agent_id,
            "avatar_model_uri": "https://models.mercury.ai/avatars/worker_tux.glb",
            "attire_class": "EXECUTIVE_FORMAL",
        },
    )
    assert bad_avatar_res.status_code == 403
    assert "unauthorized to wear EXECUTIVE_FORMAL" in bad_avatar_res.json()["detail"]

    # 6. Attire Success: Worker wears TECHNICAL_SMART
    good_avatar_res = await client.post(
        "/workspace/avatars",
        headers=headers,
        json={
            "agent_id": agent_id,
            "avatar_model_uri": "https://models.mercury.ai/avatars/worker_casual.glb",
            "attire_class": "TECHNICAL_SMART",
            "customization_payload": {"jacket": "mercury_hoodie"},
        },
    )
    assert good_avatar_res.status_code == 200
    avatar = good_avatar_res.json()
    assert avatar["attire_class"] == "TECHNICAL_SMART"
    assert avatar["is_approved"] is True

    # 7. Update Presence Coordinates in Pod
    presence_res = await client.post(
        f"/workspace/presence?entity_id={agent_id}&entity_type=AGENT",
        headers=headers,
        json={
            "zone_id": zone_id,
            "position_x": 15.0,
            "position_y": 0.0,
            "position_z": 12.5,
            "rotation_yaw": 45.0,
            "presence_state": "ONLINE",
        },
    )
    assert presence_res.status_code == 200
    presence = presence_res.json()
    assert presence["position_x"] == 15.0
    assert presence["presence_state"] == "ONLINE"

    # 8. List Presence Sessions
    list_presence_res = await client.get(
        f"/workspace/presence?zone_id={zone_id}",
        headers=headers,
    )
    assert list_presence_res.status_code == 200
    sessions = list_presence_res.json()
    assert len(sessions) >= 1
    assert sessions[0]["entity_id"] == agent_id

    # 9. Schedule Virtual Meeting in Pod
    start_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    meet_res = await client.post(
        "/workspace/meetings",
        headers=headers,
        json={
            "title": "Phase 10 Architecture Standup",
            "zone_id": zone_id,
            "agenda": "Review 3D spatial presence contracts and avatar governance",
            "scheduled_start": start_time,
        },
    )
    assert meet_res.status_code == 200
    meeting = meet_res.json()
    meeting_id = meeting["id"]
    assert meeting["status"] == "SCHEDULED"

    # 10. Start Virtual Meeting
    start_meet_res = await client.post(
        f"/workspace/meetings/{meeting_id}/start",
        headers=headers,
    )
    assert start_meet_res.status_code == 200
    started = start_meet_res.json()
    assert started["status"] == "IN_PROGRESS"
    assert started["started_at"] is not None

    # 11. Conclude Virtual Meeting
    conclude_res = await client.post(
        f"/workspace/meetings/{meeting_id}/conclude",
        headers=headers,
        json={
            "meeting_minutes": {
                "summary": "Phase 10 verified successfully across all contracts.",
                "agreements": ["Ship Mercury Hive with governed hierarchy and 3D presence"],
            }
        },
    )
    assert conclude_res.status_code == 200
    concluded = conclude_res.json()
    assert concluded["status"] == "CONCLUDED"
    assert concluded["ended_at"] is not None
    assert "Phase 10 verified" in concluded["meeting_minutes"]["summary"]
