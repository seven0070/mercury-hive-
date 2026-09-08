"""Workspace and spatial presence service: zones, attire governance, and meetings."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.roles import SystemRole
from domain.enums.workspace import (
    AttireClass,
    MeetingRole,
    MeetingStatus,
    PresenceState,
)
from domain.models.agents import Agent
from domain.models.workspace import (
    AvatarProfile,
    MeetingParticipant,
    PresenceSession,
    VirtualMeeting,
    WorkspaceZone,
)
from domain.schemas.audit import AuditEventCreate
from domain.schemas.workspace import (
    AvatarProfileCreate,
    PresenceUpdate,
    VirtualMeetingCreate,
    WorkspaceZoneCreate,
)
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class WorkspaceError(Exception):
    """3D workspace, avatar attire, or presence policy violations."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _validate_attire_hierarchy(role: str, attire_class: AttireClass) -> None:
    """Ensure corporate attire conforms strictly to organizational hierarchy."""
    if attire_class == AttireClass.EXECUTIVE_FORMAL and role not in ["OWNER", SystemRole.CEO.value]:
        raise WorkspaceError(
            f"Role '{role}' is unauthorized to wear EXECUTIVE_FORMAL attire",
            status_code=403,
        )

    if attire_class == AttireClass.BUSINESS_PROFESSIONAL and role in [
        SystemRole.WORKER.value,
        SystemRole.TEMPORARY_SUB_AGENT.value,
    ]:
        raise WorkspaceError(
            "Workers and Subagents cannot wear BUSINESS_PROFESSIONAL attire",
            status_code=403,
        )


async def create_zone(
    session: AsyncSession,
    data: WorkspaceZoneCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> WorkspaceZone:
    """Create a new spatial zone or departmental pod."""
    if creator_role not in ["OWNER", "CEO", "DEPARTMENT_MANAGER"]:
        raise WorkspaceError("Only Owner, CEO, or Managers can configure zones", status_code=403)

    zone = WorkspaceZone(
        id=uuid.uuid4(),
        name=data.name,
        zone_type=data.zone_type.value,
        department_id=data.department_id,
        capacity=data.capacity,
        security_level=data.security_level,
        spatial_bounds=data.spatial_bounds,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(zone)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=creator_id,
            actor_role=creator_role,
            target_type="WORKSPACE_ZONE",
            target_id=zone.id,
            action="create_zone",
            decision="ALLOW",
            reason=f"Created zone {data.name} ({data.zone_type.value})",
            payload={"zone_type": data.zone_type.value, "security": data.security_level},
        ),
    )

    return zone


async def list_zones(
    session: AsyncSession,
    zone_type: str | None = None,
) -> list[WorkspaceZone]:
    """List spatial zones in the 3D office."""
    stmt = select(WorkspaceZone).where(WorkspaceZone.is_active.is_(True))
    if zone_type:
        stmt = stmt.where(WorkspaceZone.zone_type == zone_type)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_avatar_profile(
    session: AsyncSession,
    data: AvatarProfileCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> AvatarProfile:
    """Create or update a governed 3D avatar profile with hierarchical attire rules."""
    agent_role = "OWNER"
    if data.agent_id:
        agent_res = await session.execute(select(Agent).where(Agent.id == data.agent_id))
        agent = agent_res.scalar_one_or_none()
        if not agent:
            raise WorkspaceError("Target agent not found", status_code=404)
        agent_role = agent.role

    _validate_attire_hierarchy(agent_role, data.attire_class)

    now = datetime.now(UTC)
    profile = AvatarProfile(
        id=uuid.uuid4(),
        agent_id=data.agent_id,
        avatar_model_uri=data.avatar_model_uri,
        attire_class=data.attire_class.value,
        customization_payload=data.customization_payload,
        is_approved=True,
        approved_by=creator_id if creator_role == "OWNER" else None,
        created_at=now,
        updated_at=now,
    )
    session.add(profile)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=creator_id,
            actor_role=creator_role,
            target_type="AVATAR_PROFILE",
            target_id=profile.id,
            action="create_avatar_profile",
            decision="ALLOW",
            reason=f"Avatar registered with attire class {data.attire_class.value}",
            payload={"attire": data.attire_class.value},
        ),
    )

    return profile


async def update_presence(
    session: AsyncSession,
    entity_id: uuid.UUID,
    entity_type: str,
    data: PresenceUpdate,
) -> PresenceSession:
    """Update real-time spatial location, orientation, and presence state."""
    zone_res = await session.execute(select(WorkspaceZone).where(WorkspaceZone.id == data.zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone or not zone.is_active:
        raise WorkspaceError("Target workspace zone not found or inactive", status_code=404)

    now = datetime.now(UTC)
    sess_res = await session.execute(
        select(PresenceSession).where(PresenceSession.entity_id == entity_id)
    )
    presence = sess_res.scalar_one_or_none()

    if presence:
        presence.zone_id = data.zone_id
        presence.position_x = data.position_x
        presence.position_y = data.position_y
        presence.position_z = data.position_z
        presence.rotation_yaw = data.rotation_yaw
        presence.presence_state = data.presence_state.value
        presence.current_task_id = data.current_task_id
        presence.last_heartbeat_at = now
    else:
        presence = PresenceSession(
            id=uuid.uuid4(),
            entity_id=entity_id,
            entity_type=entity_type,
            zone_id=data.zone_id,
            position_x=data.position_x,
            position_y=data.position_y,
            position_z=data.position_z,
            rotation_yaw=data.rotation_yaw,
            presence_state=data.presence_state.value,
            current_task_id=data.current_task_id,
            last_heartbeat_at=now,
        )
        session.add(presence)

    return presence


async def list_active_presence(
    session: AsyncSession,
    zone_id: uuid.UUID | None = None,
) -> list[PresenceSession]:
    """List online entities currently occupying spatial zones."""
    stmt = select(PresenceSession).where(
        PresenceSession.presence_state.in_(
            [PresenceState.ONLINE.value, PresenceState.IN_MEETING.value]
        )
    )
    if zone_id:
        stmt = stmt.where(PresenceSession.zone_id == zone_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def schedule_meeting(
    session: AsyncSession,
    data: VirtualMeetingCreate,
    host_id: uuid.UUID,
    host_role: str,
) -> VirtualMeeting:
    """Schedule a virtual boardroom or departmental conclave."""
    zone_res = await session.execute(select(WorkspaceZone).where(WorkspaceZone.id == data.zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone or not zone.is_active:
        raise WorkspaceError("Target meeting zone not found or inactive", status_code=404)

    meeting = VirtualMeeting(
        id=uuid.uuid4(),
        title=data.title,
        zone_id=data.zone_id,
        host_id=host_id,
        status=MeetingStatus.SCHEDULED.value,
        agenda=data.agenda,
        scheduled_start=data.scheduled_start,
    )
    session.add(meeting)

    participant = MeetingParticipant(
        id=uuid.uuid4(),
        meeting_id=meeting.id,
        entity_id=host_id,
        role_in_meeting=MeetingRole.HOST.value,
        joined_at=datetime.now(UTC),
    )
    session.add(participant)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=host_id,
            actor_role=host_role,
            target_type="VIRTUAL_MEETING",
            target_id=meeting.id,
            action="schedule_meeting",
            decision="ALLOW",
            reason=f"Scheduled meeting '{data.title}' in zone {zone.name}",
            payload={"zone_name": zone.name},
        ),
    )

    return meeting


async def start_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
) -> VirtualMeeting:
    """Initiate a scheduled virtual meeting."""
    meet_res = await session.execute(select(VirtualMeeting).where(VirtualMeeting.id == meeting_id))
    meeting = meet_res.scalar_one_or_none()
    if not meeting:
        raise WorkspaceError("Meeting not found", status_code=404)

    if meeting.status != MeetingStatus.SCHEDULED.value:
        raise WorkspaceError(f"Cannot start meeting in status {meeting.status}", status_code=400)

    now = datetime.now(UTC)
    meeting.status = MeetingStatus.IN_PROGRESS.value
    meeting.started_at = now

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="VIRTUAL_MEETING",
            target_id=meeting.id,
            action="start_meeting",
            decision="ALLOW",
            reason=f"Started meeting '{meeting.title}'",
        ),
    )

    return meeting


async def conclude_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    minutes: dict | None,
    actor_id: uuid.UUID,
    actor_role: str,
) -> VirtualMeeting:
    """Conclude a virtual meeting and record minutes."""
    meet_res = await session.execute(select(VirtualMeeting).where(VirtualMeeting.id == meeting_id))
    meeting = meet_res.scalar_one_or_none()
    if not meeting:
        raise WorkspaceError("Meeting not found", status_code=404)

    if meeting.status != MeetingStatus.IN_PROGRESS.value:
        raise WorkspaceError(f"Cannot conclude meeting in status {meeting.status}", status_code=400)

    now = datetime.now(UTC)
    meeting.status = MeetingStatus.CONCLUDED.value
    meeting.ended_at = now
    meeting.meeting_minutes = minutes

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="VIRTUAL_MEETING",
            target_id=meeting.id,
            action="conclude_meeting",
            decision="ALLOW",
            reason=f"Concluded meeting '{meeting.title}'",
        ),
    )

    return meeting
