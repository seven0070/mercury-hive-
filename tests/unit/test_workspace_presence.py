"""Unit tests for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.roles import SystemRole
from domain.enums.workspace import (
    AttireClass,
    MeetingStatus,
    PresenceState,
    ZoneType,
)
from domain.models.agents import Agent
from domain.models.workspace import (
    PresenceSession,
    WorkspaceZone,
)
from domain.schemas.workspace import (
    AvatarProfileCreate,
    PresenceUpdate,
    VirtualMeetingCreate,
    WorkspaceZoneCreate,
)
from services.workspace.service import (
    WorkspaceError,
    _validate_attire_hierarchy,
    conclude_meeting,
    create_avatar_profile,
    create_zone,
    schedule_meeting,
    start_meeting,
    update_presence,
)


def test_attire_hierarchy_enforcement():
    """Hierarchy rules strictly block unauthorized attire classes."""
    # Workers cannot wear EXECUTIVE_FORMAL
    with pytest.raises(WorkspaceError, match="unauthorized to wear EXECUTIVE_FORMAL"):
        _validate_attire_hierarchy(SystemRole.WORKER.value, AttireClass.EXECUTIVE_FORMAL)

    # Managers cannot wear EXECUTIVE_FORMAL
    with pytest.raises(WorkspaceError, match="unauthorized to wear EXECUTIVE_FORMAL"):
        _validate_attire_hierarchy(
            SystemRole.DEPARTMENT_MANAGER.value, AttireClass.EXECUTIVE_FORMAL
        )

    # Workers cannot wear BUSINESS_PROFESSIONAL
    with pytest.raises(WorkspaceError, match="cannot wear BUSINESS_PROFESSIONAL"):
        _validate_attire_hierarchy(SystemRole.WORKER.value, AttireClass.BUSINESS_PROFESSIONAL)

    # CEO and OWNER can wear EXECUTIVE_FORMAL
    _validate_attire_hierarchy("OWNER", AttireClass.EXECUTIVE_FORMAL)
    _validate_attire_hierarchy(SystemRole.CEO.value, AttireClass.EXECUTIVE_FORMAL)

    # Managers can wear BUSINESS_PROFESSIONAL
    _validate_attire_hierarchy(
        SystemRole.DEPARTMENT_MANAGER.value, AttireClass.BUSINESS_PROFESSIONAL
    )

    # Workers can wear TECHNICAL_SMART
    _validate_attire_hierarchy(SystemRole.WORKER.value, AttireClass.TECHNICAL_SMART)


@pytest.mark.asyncio
async def test_create_zone_unauthorized():
    """Worker role cannot create spatial zones."""
    mock_session = AsyncMock()
    data = WorkspaceZoneCreate(
        name="Security Pod",
        zone_type=ZoneType.DEPARTMENT_POD,
        capacity=10,
        spatial_bounds={"min": [0, 0, 0], "max": [10, 10, 5]},
    )

    with pytest.raises(WorkspaceError, match="Only Owner, CEO, or Managers"):
        await create_zone(mock_session, data, uuid.uuid4(), SystemRole.WORKER.value)


@pytest.mark.asyncio
async def test_create_zone_success():
    """Owner successfully creates a new spatial zone."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()
    mock_session.execute.return_value = r_audit

    data = WorkspaceZoneCreate(
        name="Executive Boardroom",
        zone_type=ZoneType.BOARDROOM,
        capacity=25,
        security_level="TOP_SECRET",
        spatial_bounds={"min": [-20, -20, 0], "max": [20, 20, 10]},
    )

    zone = await create_zone(mock_session, data, uuid.uuid4(), "OWNER")

    assert zone.name == "Executive Boardroom"
    assert zone.zone_type == ZoneType.BOARDROOM.value
    assert zone.security_level == "TOP_SECRET"
    assert mock_session.add.call_count >= 1


@pytest.mark.asyncio
async def test_create_avatar_profile_target_agent_not_found():
    """Creating avatar profile for non-existent agent fails."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    data = AvatarProfileCreate(
        agent_id=uuid.uuid4(),
        avatar_model_uri="https://models.mercury.ai/worker_v1.glb",
        attire_class=AttireClass.TECHNICAL_SMART,
    )

    with pytest.raises(WorkspaceError, match="Target agent not found"):
        await create_avatar_profile(mock_session, data, uuid.uuid4(), "OWNER")


@pytest.mark.asyncio
async def test_create_avatar_profile_success():
    """Owner registers valid avatar profile."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="DevBot",
        role=SystemRole.WORKER.value,
        department_id=uuid.uuid4(),
        status="ACTIVE",
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_agent, r_audit]

    data = AvatarProfileCreate(
        agent_id=agent_id,
        avatar_model_uri="https://models.mercury.ai/worker_v1.glb",
        attire_class=AttireClass.TECHNICAL_SMART,
        customization_payload={"hair_color": "dark_slate"},
    )

    profile = await create_avatar_profile(mock_session, data, uuid.uuid4(), "OWNER")

    assert profile.agent_id == agent_id
    assert profile.attire_class == AttireClass.TECHNICAL_SMART.value
    assert profile.is_approved is True
    assert mock_session.add.call_count >= 1


@pytest.mark.asyncio
async def test_update_presence_zone_inactive_or_missing():
    """Presence update fails if target zone does not exist or is inactive."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    data = PresenceUpdate(
        zone_id=uuid.uuid4(),
        position_x=12.5,
        position_y=0.0,
        position_z=3.0,
    )

    with pytest.raises(WorkspaceError, match="Target workspace zone not found or inactive"):
        await update_presence(mock_session, uuid.uuid4(), "AGENT", data)


@pytest.mark.asyncio
async def test_update_presence_existing_session():
    """Updating presence modifies coordinates and timestamp on existing record."""
    mock_session = AsyncMock()
    zone_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    zone = WorkspaceZone(
        id=zone_id,
        name="Commons Area",
        zone_type=ZoneType.COMMONS.value,
        is_active=True,
    )
    existing_presence = PresenceSession(
        id=uuid.uuid4(),
        entity_id=entity_id,
        entity_type="AGENT",
        zone_id=zone_id,
        position_x=1.0,
        position_y=1.0,
        position_z=0.0,
        rotation_yaw=0.0,
        presence_state=PresenceState.ONLINE.value,
        last_heartbeat_at=datetime.now(UTC),
    )

    r_zone = MagicMock()
    r_zone.scalar_one_or_none.return_value = zone
    r_sess = MagicMock()
    r_sess.scalar_one_or_none.return_value = existing_presence

    mock_session.execute.side_effect = [r_zone, r_sess]

    data = PresenceUpdate(
        zone_id=zone_id,
        position_x=5.5,
        position_y=10.2,
        position_z=0.0,
        rotation_yaw=90.0,
        presence_state=PresenceState.IN_MEETING,
    )

    result = await update_presence(mock_session, entity_id, "AGENT", data)

    assert result.position_x == 5.5
    assert result.position_y == 10.2
    assert result.rotation_yaw == 90.0
    assert result.presence_state == PresenceState.IN_MEETING.value


@pytest.mark.asyncio
async def test_virtual_meeting_lifecycle():
    """Meeting schedules, starts, and concludes with minutes."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    zone_id = uuid.uuid4()
    host_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    zone = WorkspaceZone(
        id=zone_id,
        name="Boardroom A",
        zone_type=ZoneType.BOARDROOM.value,
        is_active=True,
    )

    # 1. Schedule Meeting
    r_zone = MagicMock()
    r_zone.scalar_one_or_none.return_value = zone
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()
    mock_session.execute.side_effect = [r_zone, r_audit]

    sched_data = VirtualMeetingCreate(
        title="Q3 Strategy Conclave",
        zone_id=zone_id,
        agenda="Review quarterly agent productivity",
        scheduled_start=datetime.now(UTC),
    )

    meeting = await schedule_meeting(mock_session, sched_data, host_id, "OWNER")
    assert meeting.status == MeetingStatus.SCHEDULED.value
    assert meeting.title == "Q3 Strategy Conclave"

    # 2. Start Meeting
    meeting.id = meeting_id
    r_meet1 = MagicMock()
    r_meet1.scalar_one_or_none.return_value = meeting
    mock_session.execute.side_effect = [r_meet1, r_audit]

    started = await start_meeting(mock_session, meeting_id, host_id, "OWNER")
    assert started.status == MeetingStatus.IN_PROGRESS.value
    assert started.started_at is not None

    # Cannot start again while in progress
    r_meet_invalid = MagicMock()
    r_meet_invalid.scalar_one_or_none.return_value = started
    mock_session.execute.side_effect = [r_meet_invalid]
    with pytest.raises(WorkspaceError, match="Cannot start meeting in status"):
        await start_meeting(mock_session, meeting_id, host_id, "OWNER")

    # 3. Conclude Meeting
    r_meet2 = MagicMock()
    r_meet2.scalar_one_or_none.return_value = started
    mock_session.execute.side_effect = [r_meet2, r_audit]

    minutes = {"decisions": ["Approve evolution candidate EV-10"], "action_items": []}
    concluded = await conclude_meeting(mock_session, meeting_id, minutes, host_id, "OWNER")

    assert concluded.status == MeetingStatus.CONCLUDED.value
    assert concluded.ended_at is not None
    assert concluded.meeting_minutes == minutes
