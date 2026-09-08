"""Unit tests for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus, DepartmentStatus
from domain.enums.roles import SystemRole
from domain.enums.tasks import TaskPriority, TaskStatus
from domain.enums.tribe import SkillProficiency, SyncDirection, SyncStatus
from domain.models.agents import Agent, Department
from domain.models.tasks import Task
from domain.models.tribe import AgentSkill, TaskSyncMapping
from domain.schemas.tribe import (
    AgentSkillCreate,
    ExternalTaskIngestRequest,
    TaskSyncCreate,
    TribeMappingCreate,
)
from services.tribe.service import (
    TribeError,
    create_tribe_mapping,
    ingest_external_task,
    register_agent_skill,
    sync_task_mapping,
    verify_agent_skill,
)


@pytest.mark.asyncio
async def test_create_tribe_mapping_department_not_found():
    """Mapping fails if target department does not exist."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    data = TribeMappingCreate(
        department_id=uuid.uuid4(),
        tribe_name="Core Platforms",
        squad_name="Data Eng Squad",
        external_team_id="team_ext_123",
    )

    with pytest.raises(TribeError, match="Department not found"):
        await create_tribe_mapping(mock_session, data, uuid.uuid4(), "OWNER")


@pytest.mark.asyncio
async def test_create_tribe_mapping_success():
    """Valid department successfully maps to external tribe/squad."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    dept_id = uuid.uuid4()
    dept = Department(
        id=dept_id,
        name="Platform Engineering",
        purpose="Infrastructure",
        status=DepartmentStatus.ACTIVE.value,
        data_classification="CONFIDENTIAL",
        budget=10000.0,
        created_at=datetime.now(UTC),
    )

    r_dept = MagicMock()
    r_dept.scalar_one_or_none.return_value = dept
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_dept, r_audit]

    data = TribeMappingCreate(
        department_id=dept_id,
        tribe_name="Infrastructure Tribe",
        squad_name="Kubernetes Ops",
        external_team_id="ops_ext_456",
    )

    mapping = await create_tribe_mapping(mock_session, data, uuid.uuid4(), "OWNER")

    assert mapping.tribe_name == "Infrastructure Tribe"
    assert mapping.squad_name == "Kubernetes Ops"
    assert mapping.sync_status == SyncStatus.SYNCED.value
    assert mock_session.add.call_count >= 1


@pytest.mark.asyncio
async def test_register_agent_skill_inactive_agent():
    """Cannot register skills for inactive or missing agents."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    data = AgentSkillCreate(
        skill_name="Distributed Consensus",
        proficiency_level=SkillProficiency.EXPERT,
    )

    with pytest.raises(TribeError, match="Target agent not found or not active"):
        await register_agent_skill(mock_session, uuid.uuid4(), data, uuid.uuid4(), "OWNER")


@pytest.mark.asyncio
async def test_register_agent_skill_success():
    """Active agent can register a capability in the skill matrix."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        display_name="Consensus Worker",
        role=SystemRole.WORKER.value,
        department_id=uuid.uuid4(),
        status=AgentStatus.ACTIVE.value,
        persona_source="base",
        persona_disclosure="AI",
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent
    r_existing = MagicMock()
    r_existing.scalar_one_or_none.return_value = None
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_agent, r_existing, r_audit]

    data = AgentSkillCreate(
        skill_name="Raft Protocols",
        proficiency_level=SkillProficiency.MASTER,
    )

    skill = await register_agent_skill(mock_session, agent_id, data, uuid.uuid4(), "OWNER")

    assert skill.skill_name == "Raft Protocols"
    assert skill.proficiency_level == SkillProficiency.MASTER.value
    assert not skill.is_verified
    assert mock_session.add.call_count >= 1


@pytest.mark.asyncio
async def test_verify_agent_skill_unauthorized_role():
    """Worker agents cannot verify skills."""
    mock_session = AsyncMock()

    with pytest.raises(TribeError, match="Only Owner, CEO, HR, or Managers"):
        await verify_agent_skill(
            session=mock_session,
            skill_id=uuid.uuid4(),
            is_verified=True,
            verifier_id=uuid.uuid4(),
            verifier_role="WORKER",
        )


@pytest.mark.asyncio
async def test_verify_agent_skill_success():
    """Authorized role can verify an agent skill."""
    mock_session = AsyncMock()

    skill_id = uuid.uuid4()
    verifier_id = uuid.uuid4()

    skill = AgentSkill(
        id=skill_id,
        agent_id=uuid.uuid4(),
        skill_name="Formal Methods Verification",
        proficiency_level=SkillProficiency.EXPERT.value,
        is_verified=False,
        created_at=datetime.now(UTC),
    )

    r_skill = MagicMock()
    r_skill.scalar_one_or_none.return_value = skill
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_skill, r_audit]

    verified = await verify_agent_skill(
        session=mock_session,
        skill_id=skill_id,
        is_verified=True,
        verifier_id=verifier_id,
        verifier_role="OWNER",
    )

    assert verified.is_verified is True
    assert verified.verified_by == verifier_id


@pytest.mark.asyncio
async def test_sync_task_mapping_duplicate_rejected():
    """Duplicate external task mappings are rejected."""
    mock_session = AsyncMock()

    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        title="Internal Task",
        description="Internal Desc",
        priority=TaskPriority.HIGH.value,
        status=TaskStatus.ASSIGNED.value,
        origin_department_id=uuid.uuid4(),
        assigned_department_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    existing_mapping = TaskSyncMapping(
        id=uuid.uuid4(),
        task_id=task_id,
        external_system="JIRA",
        external_task_id="ENG-101",
        sync_direction=SyncDirection.BIDIRECTIONAL.value,
        sync_status=SyncStatus.SYNCED.value,
        last_synced_at=datetime.now(UTC),
    )

    r_task = MagicMock()
    r_task.scalar_one_or_none.return_value = task
    r_dup = MagicMock()
    r_dup.scalar_one_or_none.return_value = existing_mapping

    mock_session.execute.side_effect = [r_task, r_dup]

    data = TaskSyncCreate(
        task_id=task_id,
        external_system="JIRA",
        external_task_id="ENG-101",
    )

    with pytest.raises(TribeError, match="already linked"):
        await sync_task_mapping(mock_session, data, uuid.uuid4(), "OWNER")


@pytest.mark.asyncio
async def test_ingest_external_task_success():
    """Ingesting external ticket creates task and sync mapping."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    dept_id = uuid.uuid4()
    dept = Department(
        id=dept_id,
        name="Security Engineering",
        purpose="Defensive Ops",
        status=DepartmentStatus.ACTIVE.value,
        data_classification="RESTRICTED",
        budget=50000.0,
        created_at=datetime.now(UTC),
    )

    r_dept = MagicMock()
    r_dept.scalar_one_or_none.return_value = dept
    r_dup = MagicMock()
    r_dup.scalar_one_or_none.return_value = None
    r_audit = MagicMock()
    r_audit.scalar_one_or_none.return_value = uuid.uuid4()

    mock_session.execute.side_effect = [r_dept, r_dup, r_audit]

    data = ExternalTaskIngestRequest(
        external_system="GITHUB_ISSUES",
        external_task_id="REPO-404",
        title="Audit memory leaks in cryptographic provider",
        description="Detailed vulnerability disclosure and reproduction steps.",
        department_id=dept_id,
        priority="HIGH",
    )

    task, sync_mapping = await ingest_external_task(
        session=mock_session,
        data=data,
        actor_id=uuid.uuid4(),
        actor_role="OWNER",
    )

    assert "[GITHUB_ISSUES]" in task.title
    assert task.status == TaskStatus.CREATED.value
    assert sync_mapping.external_task_id == "REPO-404"
    assert sync_mapping.sync_direction == SyncDirection.INBOUND.value
    assert mock_session.add.call_count >= 2
