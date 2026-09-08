"""Agent registry, lifecycle transitions, and permission grant management."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.agent_status import AgentStatus
from domain.enums.roles import SystemRole
from domain.models.agents import Agent, Department, PermissionGrant
from domain.schemas.agents import AgentCreate, AgentUpdate, PermissionGrantCreate
from domain.schemas.audit import AuditEventCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class AgentRegistryError(Exception):
    """Business logic errors in agent lifecycle management."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def create_agent(
    session: AsyncSession,
    data: AgentCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> Agent:
    """Register a new AI Agent with strict organizational authority enforcement.

    Governance Rules:
    - Workers cannot create permanent agents.
    - Temporary sub-agents require parent_agent_id.
    - Department must exist and be active if specified.
    """
    # Rule 1: Worker cannot create permanent agents
    if creator_role == SystemRole.WORKER and data.role != SystemRole.TEMPORARY_SUB_AGENT:
        raise AgentRegistryError("Workers cannot create permanent agents")

    # Rule 2: Temporary sub-agents require parent
    if data.role == SystemRole.TEMPORARY_SUB_AGENT and not data.parent_agent_id:
        raise AgentRegistryError("Temporary sub-agents must have a parent agent")

    # Rule 3: Department check
    if data.department_id:
        dept_res = await session.execute(
            select(Department).where(Department.id == data.department_id)
        )
        dept = dept_res.scalar_one_or_none()
        if not dept or dept.status != "ACTIVE":
            raise AgentRegistryError("Assigned department not found or not active")

    agent = Agent(
        id=uuid.uuid4(),
        display_name=data.display_name,
        role=data.role,
        department_id=data.department_id,
        manager_id=data.manager_id,
        status=AgentStatus.ACTIVE,
        persona_source=data.persona_source,
        persona_disclosure=data.persona_disclosure,
        system_prompt_version=data.system_prompt_version,
        avatar_profile_id=data.avatar_profile_id,
        parent_agent_id=data.parent_agent_id,
        created_at=datetime.now(UTC),
    )
    session.add(agent)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=creator_id,
            actor_role=creator_role,
            action="agent_created",
            decision="ALLOW",
            reason=f"Agent {agent.display_name} created with role {agent.role}",
            target_id=agent.id,
            target_type="AGENT",
            payload={"role": agent.role, "department_id": str(agent.department_id)},
        ),
    )

    return agent


async def get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    """Fetch an agent by ID."""
    res = await session.execute(select(Agent).where(Agent.id == agent_id))
    return res.scalar_one_or_none()


async def list_agents(
    session: AsyncSession,
    department_id: uuid.UUID | None = None,
    role: SystemRole | None = None,
    status: AgentStatus | None = None,
    limit: int = 100,
) -> list[Agent]:
    """List agents with optional filtering."""
    query = select(Agent).order_by(Agent.created_at.desc()).limit(limit)
    if department_id:
        query = query.where(Agent.department_id == department_id)
    if role:
        query = query.where(Agent.role == role)
    if status:
        query = query.where(Agent.status == status)
    res = await session.execute(query)
    return list(res.scalars().all())


async def update_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    data: AgentUpdate,
    updater_id: uuid.UUID,
    updater_role: str,
) -> Agent:
    """Update non-sensitive agent metadata."""
    agent = await get_agent(session, agent_id)
    if not agent:
        raise AgentRegistryError("Agent not found")

    if data.display_name is not None:
        agent.display_name = data.display_name
    if data.system_prompt_version is not None:
        agent.system_prompt_version = data.system_prompt_version
    if data.persona_disclosure is not None:
        agent.persona_disclosure = data.persona_disclosure

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=updater_id,
            actor_role=updater_role,
            action="agent_updated",
            decision="ALLOW",
            target_id=agent.id,
            target_type="AGENT",
        ),
    )
    return agent


async def suspend_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
    actor_role: str,
) -> Agent:
    """Suspend an agent and automatically revoke all active permission grants."""
    if actor_role == SystemRole.WORKER:
        raise AgentRegistryError("Workers cannot suspend agents")

    agent = await get_agent(session, agent_id)
    if not agent:
        raise AgentRegistryError("Agent not found")

    now = datetime.now(UTC)
    agent.status = AgentStatus.SUSPENDED
    agent.suspended_at = now

    # Revoke all active permission grants
    await session.execute(
        update(PermissionGrant)
        .where(PermissionGrant.agent_id == agent_id, PermissionGrant.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="agent_suspended")
    )

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=actor_id,
            actor_role=actor_role,
            action="agent_suspended",
            decision="ALLOW",
            reason=reason,
            target_id=agent.id,
            target_type="AGENT",
        ),
    )
    return agent


async def terminate_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
    actor_role: str,
) -> Agent:
    """Permanently terminate an agent and revoke all grants."""
    if actor_role == SystemRole.WORKER:
        raise AgentRegistryError("Workers cannot terminate agents")

    agent = await get_agent(session, agent_id)
    if not agent:
        raise AgentRegistryError("Agent not found")

    now = datetime.now(UTC)
    agent.status = AgentStatus.TERMINATED
    agent.terminated_at = now
    agent.termination_reason = reason

    # Revoke active grants
    await session.execute(
        update(PermissionGrant)
        .where(PermissionGrant.agent_id == agent_id, PermissionGrant.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="agent_terminated")
    )

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=actor_id,
            actor_role=actor_role,
            action="agent_terminated",
            decision="ALLOW",
            reason=reason,
            target_id=agent.id,
            target_type="AGENT",
        ),
    )
    return agent


async def restore_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
    actor_role: str,
) -> Agent:
    """Restore a suspended agent back to ACTIVE status."""
    if actor_role == SystemRole.WORKER:
        raise AgentRegistryError("Workers cannot restore agents")

    agent = await get_agent(session, agent_id)
    if not agent:
        raise AgentRegistryError("Agent not found")

    if agent.status == AgentStatus.TERMINATED:
        raise AgentRegistryError("Terminated agents cannot be restored")

    agent.status = AgentStatus.ACTIVE
    agent.suspended_at = None

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=actor_id,
            actor_role=actor_role,
            action="agent_restored",
            decision="ALLOW",
            reason=reason,
            target_id=agent.id,
            target_type="AGENT",
        ),
    )
    return agent


# ============================================================
# Permission Grants
# ============================================================


async def issue_permission_grant(
    session: AsyncSession,
    data: PermissionGrantCreate,
    issuer_id: uuid.UUID,
    issuer_role: str,
) -> PermissionGrant:
    """Issue a scoped, revocable permission grant to an agent."""
    agent = await get_agent(session, data.agent_id)
    if not agent or agent.status != AgentStatus.ACTIVE:
        raise AgentRegistryError("Cannot grant permissions to inactive or missing agent")

    # Agents cannot grant permissions to themselves
    if issuer_id == data.agent_id:
        raise AgentRegistryError("Agents cannot grant permissions to themselves")

    grant = PermissionGrant(
        id=uuid.uuid4(),
        agent_id=data.agent_id,
        task_id=data.task_id,
        department_id=data.department_id,
        allowed_actions=data.allowed_actions,
        allowed_tools=data.allowed_tools,
        memory_scopes=data.memory_scopes,
        budget_limit=data.budget_limit,
        expires_at=data.expires_at,
        approval_requirements=data.approval_requirements,
        issued_by=issuer_id,
        created_at=datetime.now(UTC),
    )
    session.add(grant)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=issuer_id,
            actor_role=issuer_role,
            action="permission_granted",
            decision="ALLOW",
            target_id=grant.id,
            target_type="PERMISSION_GRANT",
            payload={
                "agent_id": str(data.agent_id),
                "allowed_actions": data.allowed_actions,
                "allowed_tools": data.allowed_tools,
            },
        ),
    )
    return grant


async def revoke_permission_grant(
    session: AsyncSession,
    grant_id: uuid.UUID,
    reason: str,
    revoker_id: uuid.UUID,
    revoker_role: str,
) -> PermissionGrant:
    """Revoke an active permission grant."""
    res = await session.execute(
        select(PermissionGrant).where(PermissionGrant.id == grant_id).with_for_update()
    )
    grant = res.scalar_one_or_none()
    if not grant:
        raise AgentRegistryError("Permission grant not found")

    if grant.revoked_at is not None:
        raise AgentRegistryError("Permission grant is already revoked")

    grant.revoked_at = datetime.now(UTC)
    grant.revocation_reason = reason

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=revoker_id,
            actor_role=revoker_role,
            action="permission_revoked",
            decision="ALLOW",
            reason=reason,
            target_id=grant.id,
            target_type="PERMISSION_GRANT",
        ),
    )
    return grant


async def list_agent_grants(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> list[PermissionGrant]:
    """List active and historical grants for an agent."""
    res = await session.execute(
        select(PermissionGrant)
        .where(PermissionGrant.agent_id == agent_id)
        .order_by(PermissionGrant.created_at.desc())
    )
    return list(res.scalars().all())
