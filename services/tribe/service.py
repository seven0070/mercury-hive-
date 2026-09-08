"""Tribe adapter service: department topology, skill matrix, and cross-system task sync."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tasks import TaskPriority, TaskStatus
from domain.enums.tribe import SyncDirection, SyncStatus
from domain.models.agents import Agent, Department
from domain.models.tasks import Task
from domain.models.tribe import AgentSkill, TaskSyncMapping, TribeMapping
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tribe import (
    AgentSkillCreate,
    ExternalTaskIngestRequest,
    TaskSyncCreate,
    TribeMappingCreate,
)
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class TribeError(Exception):
    """Tribe adapter or synchronization errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def create_tribe_mapping(
    session: AsyncSession,
    data: TribeMappingCreate,
    actor_id: uuid.UUID,
    actor_role: str,
) -> TribeMapping:
    """Map a Mercury Hive department to an external Tribe/Squad topology."""
    dept_res = await session.execute(select(Department).where(Department.id == data.department_id))
    dept = dept_res.scalar_one_or_none()
    if not dept:
        raise TribeError("Department not found", status_code=404)

    mapping = TribeMapping(
        id=uuid.uuid4(),
        department_id=data.department_id,
        tribe_name=data.tribe_name,
        squad_name=data.squad_name,
        external_team_id=data.external_team_id,
        sync_status=SyncStatus.SYNCED.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(mapping)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="TRIBE_MAPPING",
            target_id=mapping.id,
            action="create_tribe_mapping",
            decision="ALLOW",
            reason=f"Mapped department {dept.name} to tribe {data.tribe_name}/{data.squad_name}",
            payload={
                "department_id": str(data.department_id),
                "external_team_id": data.external_team_id,
            },
        ),
    )

    return mapping


async def list_tribe_mappings(
    session: AsyncSession,
    department_id: uuid.UUID | None = None,
) -> list[TribeMapping]:
    """List all department-to-tribe mappings."""
    stmt = select(TribeMapping).order_by(TribeMapping.created_at.desc())
    if department_id:
        stmt = stmt.where(TribeMapping.department_id == department_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def register_agent_skill(
    session: AsyncSession,
    agent_id: uuid.UUID,
    data: AgentSkillCreate,
    actor_id: uuid.UUID,
    actor_role: str,
) -> AgentSkill:
    """Register an agent capability in the organizational skill matrix."""
    agent_res = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_res.scalar_one_or_none()
    if not agent or agent.status != "ACTIVE":
        raise TribeError("Target agent not found or not active", status_code=404)

    # Check existing skill
    existing_res = await session.execute(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_name == data.skill_name,
        )
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        existing.proficiency_level = data.proficiency_level.value
        skill = existing
    else:
        skill = AgentSkill(
            id=uuid.uuid4(),
            agent_id=agent_id,
            skill_name=data.skill_name,
            proficiency_level=data.proficiency_level.value,
            is_verified=False,
            created_at=datetime.now(UTC),
        )
        session.add(skill)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="AGENT_SKILL",
            target_id=skill.id,
            action="register_agent_skill",
            decision="ALLOW",
            reason=f"Skill '{data.skill_name}' registered for agent {agent.display_name}",
            payload={
                "skill_name": data.skill_name,
                "proficiency": data.proficiency_level.value,
            },
        ),
    )

    return skill


async def verify_agent_skill(
    session: AsyncSession,
    skill_id: uuid.UUID,
    is_verified: bool,
    verifier_id: uuid.UUID,
    verifier_role: str,
) -> AgentSkill:
    """Certify and verify an agent skill. Restricted to Owner, CEO, HR, or Managers."""
    if verifier_role not in ["OWNER", "CEO", "DIGITAL_HR", "DEPARTMENT_MANAGER"]:
        raise TribeError("Only Owner, CEO, HR, or Managers can verify skills", status_code=403)

    skill_res = await session.execute(select(AgentSkill).where(AgentSkill.id == skill_id))
    skill = skill_res.scalar_one_or_none()
    if not skill:
        raise TribeError("Agent skill not found", status_code=404)

    skill.is_verified = is_verified
    skill.verified_by = verifier_id if is_verified else None

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=verifier_id,
            actor_role=verifier_role,
            target_type="AGENT_SKILL",
            target_id=skill.id,
            action="verify_agent_skill",
            decision="ALLOW",
            reason=f"Skill '{skill.skill_name}' verified={is_verified} by {verifier_role}",
            payload={"is_verified": is_verified},
        ),
    )

    return skill


async def list_agent_skills(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> list[AgentSkill]:
    """List all skills declared for an agent."""
    stmt = (
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .order_by(AgentSkill.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def sync_task_mapping(
    session: AsyncSession,
    data: TaskSyncCreate,
    actor_id: uuid.UUID,
    actor_role: str,
) -> TaskSyncMapping:
    """Link an internal task to an external tracker issue/ticket."""
    task_res = await session.execute(select(Task).where(Task.id == data.task_id))
    task = task_res.scalar_one_or_none()
    if not task:
        raise TribeError("Task not found", status_code=404)

    # Check for duplicate mapping
    dup_res = await session.execute(
        select(TaskSyncMapping).where(
            TaskSyncMapping.external_system == data.external_system,
            TaskSyncMapping.external_task_id == data.external_task_id,
        )
    )
    if dup_res.scalar_one_or_none():
        raise TribeError(
            f"External task {data.external_system}:{data.external_task_id} is already linked",
            status_code=400,
        )

    mapping = TaskSyncMapping(
        id=uuid.uuid4(),
        task_id=data.task_id,
        external_system=data.external_system,
        external_task_id=data.external_task_id,
        sync_direction=data.sync_direction.value,
        sync_status=SyncStatus.SYNCED.value,
        last_synced_at=datetime.now(UTC),
    )
    session.add(mapping)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="TASK_SYNC",
            target_id=mapping.id,
            action="sync_task_mapping",
            decision="ALLOW",
            reason=(f"Linked task {task.title} to {data.external_system}:{data.external_task_id}"),
            payload={
                "external_system": data.external_system,
                "external_task_id": data.external_task_id,
            },
        ),
    )

    return mapping


async def ingest_external_task(
    session: AsyncSession,
    data: ExternalTaskIngestRequest,
    actor_id: uuid.UUID,
    actor_role: str,
) -> tuple[Task, TaskSyncMapping]:
    """Ingest an external ticket as a governed internal Mercury Hive task."""
    dept_res = await session.execute(select(Department).where(Department.id == data.department_id))
    dept = dept_res.scalar_one_or_none()
    if not dept:
        raise TribeError("Target department not found", status_code=404)

    # Check duplicate external task
    dup_res = await session.execute(
        select(TaskSyncMapping).where(
            TaskSyncMapping.external_system == data.external_system,
            TaskSyncMapping.external_task_id == data.external_task_id,
        )
    )
    if dup_res.scalar_one_or_none():
        raise TribeError(
            f"External task {data.external_system}:{data.external_task_id} already ingested",
            status_code=400,
        )

    priority_val = (
        data.priority
        if data.priority in [p.value for p in TaskPriority]
        else TaskPriority.MEDIUM.value
    )

    now = datetime.now(UTC)
    task = Task(
        id=uuid.uuid4(),
        title=f"[{data.external_system}] {data.title}",
        description=data.description,
        priority=priority_val,
        status=TaskStatus.CREATED.value,
        origin_department_id=data.department_id,
        assigned_department_id=data.department_id,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    session.add(task)

    sync_mapping = TaskSyncMapping(
        id=uuid.uuid4(),
        task_id=task.id,
        external_system=data.external_system,
        external_task_id=data.external_task_id,
        sync_direction=SyncDirection.INBOUND.value,
        sync_status=SyncStatus.SYNCED.value,
        last_synced_at=now,
    )
    session.add(sync_mapping)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="TASK",
            target_id=task.id,
            action="ingest_external_task",
            decision="ALLOW",
            reason=f"Ingested external task {data.external_system}:{data.external_task_id}",
            payload={
                "external_system": data.external_system,
                "external_task_id": data.external_task_id,
            },
        ),
    )

    return task, sync_mapping


async def list_task_sync_mappings(
    session: AsyncSession,
    task_id: uuid.UUID | None = None,
) -> list[TaskSyncMapping]:
    """List task synchronization mappings."""
    stmt = select(TaskSyncMapping).order_by(TaskSyncMapping.last_synced_at.desc())
    if task_id:
        stmt = stmt.where(TaskSyncMapping.task_id == task_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())
