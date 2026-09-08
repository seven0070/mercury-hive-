"""Unit tests for Phase 3: Agent registry, lifecycle, and permissions."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus, DataClassification, DepartmentStatus
from domain.enums.roles import SystemRole
from domain.models.agents import Agent
from domain.schemas.agents import (
    AgentCreate,
    DepartmentCreate,
    PermissionGrantCreate,
)
from services.agent_registry.service import (
    AgentRegistryError,
    create_agent,
    issue_permission_grant,
    restore_agent,
    revoke_permission_grant,
    suspend_agent,
    terminate_agent,
)
from services.departments.service import (
    DepartmentError,
    approve_department,
    propose_department,
)


@pytest.mark.asyncio
async def test_worker_cannot_create_permanent_agent():
    """Worker role attempting to create a permanent worker agent must be blocked."""
    mock_session = AsyncMock()
    creator_id = uuid.uuid4()

    req = AgentCreate(
        display_name="Sub-Worker",
        role=SystemRole.WORKER,
    )

    with pytest.raises(AgentRegistryError, match="Workers cannot create permanent agents"):
        await create_agent(
            session=mock_session,
            data=req,
            creator_id=creator_id,
            creator_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_subagent_requires_parent_id():
    """Temporary sub-agents must provide a parent agent ID."""
    mock_session = AsyncMock()
    creator_id = uuid.uuid4()

    req = AgentCreate(
        display_name="Temp Worker",
        role=SystemRole.TEMPORARY_SUB_AGENT,
        parent_agent_id=None,
    )

    with pytest.raises(AgentRegistryError, match="Temporary sub-agents must have a parent agent"):
        await create_agent(
            session=mock_session,
            data=req,
            creator_id=creator_id,
            creator_role=SystemRole.DEPARTMENT_MANAGER,
        )


@pytest.mark.asyncio
async def test_owner_can_create_valid_agent():
    """Owner can successfully provision an agent."""
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute.return_value = MagicMock()

    creator_id = uuid.uuid4()
    req = AgentCreate(
        display_name="Lead Engineer",
        role=SystemRole.DEPARTMENT_MANAGER,
        persona_source="SYSTEM",
        system_prompt_version="1.0.0",
    )

    agent = await create_agent(
        session=mock_session,
        data=req,
        creator_id=creator_id,
        creator_role="OWNER",
    )

    assert agent.display_name == "Lead Engineer"
    assert agent.role == SystemRole.DEPARTMENT_MANAGER
    assert agent.status == AgentStatus.ACTIVE
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_worker_cannot_suspend_or_terminate_agent():
    """Workers cannot suspend or terminate agents."""
    mock_session = AsyncMock()
    agent_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    with pytest.raises(AgentRegistryError, match="Workers cannot suspend agents"):
        await suspend_agent(
            session=mock_session,
            agent_id=agent_id,
            reason="Illegal suspension",
            actor_id=actor_id,
            actor_role=SystemRole.WORKER,
        )

    with pytest.raises(AgentRegistryError, match="Workers cannot terminate agents"):
        await terminate_agent(
            session=mock_session,
            agent_id=agent_id,
            reason="Illegal termination",
            actor_id=actor_id,
            actor_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_agent_suspension_and_restoration():
    """Agent suspension sets status to SUSPENDED and restoration restores to ACTIVE."""
    agent_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    test_agent = Agent(
        id=agent_id,
        display_name="Test Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = test_agent
    mock_session.execute.return_value = mock_result

    # Suspend
    suspended = await suspend_agent(
        session=mock_session,
        agent_id=agent_id,
        reason="Routine maintenance",
        actor_id=owner_id,
        actor_role="OWNER",
    )
    assert suspended.status == AgentStatus.SUSPENDED
    assert suspended.suspended_at is not None

    # Restore
    restored = await restore_agent(
        session=mock_session,
        agent_id=agent_id,
        reason="Maintenance complete",
        actor_id=owner_id,
        actor_role="OWNER",
    )
    assert restored.status == AgentStatus.ACTIVE
    assert restored.suspended_at is None


@pytest.mark.asyncio
async def test_terminated_agent_cannot_be_restored():
    """Terminated agents cannot be restored."""
    agent_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    test_agent = Agent(
        id=agent_id,
        display_name="Terminated Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.TERMINATED,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
        terminated_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = test_agent
    mock_session.execute.return_value = mock_result

    with pytest.raises(AgentRegistryError, match="Terminated agents cannot be restored"):
        await restore_agent(
            session=mock_session,
            agent_id=agent_id,
            reason="Attempt revive",
            actor_id=owner_id,
            actor_role="OWNER",
        )


@pytest.mark.asyncio
async def test_agent_cannot_grant_permissions_to_itself():
    """Agents cannot grant permissions to themselves."""
    agent_id = uuid.uuid4()

    test_agent = Agent(
        id=agent_id,
        display_name="Greedy Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = test_agent
    mock_session.execute.return_value = mock_result

    grant_req = PermissionGrantCreate(
        agent_id=agent_id,
        allowed_actions=["EXECUTE_CODE"],
        allowed_tools=["terminal"],
    )

    with pytest.raises(AgentRegistryError, match="Agents cannot grant permissions to themselves"):
        await issue_permission_grant(
            session=mock_session,
            data=grant_req,
            issuer_id=agent_id,  # issuer is the agent itself!
            issuer_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_permission_grant_and_revocation():
    """Valid permission grant creation and revocation."""
    agent_id = uuid.uuid4()
    issuer_id = uuid.uuid4()

    test_agent = Agent(
        id=agent_id,
        display_name="Good Bot",
        role=SystemRole.WORKER,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = test_agent
    mock_session.execute.return_value = mock_result

    grant_req = PermissionGrantCreate(
        agent_id=agent_id,
        allowed_actions=["READ_DATA"],
        allowed_tools=["file_reader"],
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )

    grant = await issue_permission_grant(
        session=mock_session,
        data=grant_req,
        issuer_id=issuer_id,
        issuer_role="OWNER",
    )

    assert grant.agent_id == agent_id
    assert grant.issued_by == issuer_id
    assert grant.allowed_actions == ["READ_DATA"]

    # Revocation test
    mock_grant_res = MagicMock()
    mock_grant_res.scalar_one_or_none.return_value = grant
    mock_session.execute.return_value = mock_grant_res

    revoked = await revoke_permission_grant(
        session=mock_session,
        grant_id=grant.id,
        reason="Project completed",
        revoker_id=issuer_id,
        revoker_role="OWNER",
    )
    assert revoked.revoked_at is not None
    assert revoked.revocation_reason == "Project completed"


@pytest.mark.asyncio
async def test_department_proposal_and_approval():
    """Department proposals enter PROPOSED state and require OWNER approval."""
    proposer_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # No existing dept with name
    mock_session.execute.return_value = mock_res

    dept_req = DepartmentCreate(
        name="Quantum Computing",
        purpose="R&D into quantum algorithms",
        data_classification=DataClassification.CONFIDENTIAL,
        budget=50000.0,
    )

    dept = await propose_department(
        session=mock_session,
        data=dept_req,
        proposer_id=proposer_id,
        proposer_role=SystemRole.CEO,
    )

    assert dept.name == "Quantum Computing"
    assert dept.status == DepartmentStatus.PROPOSED

    # Non-owner cannot approve
    with pytest.raises(DepartmentError, match="Only the System Owner can approve"):
        await approve_department(
            session=mock_session,
            department_id=dept.id,
            approver_id=proposer_id,
            approver_role=SystemRole.CEO,
        )

    # Owner can approve
    mock_dept_res = MagicMock()
    mock_dept_res.scalar_one_or_none.return_value = dept
    mock_session.execute.return_value = mock_dept_res

    approved_dept = await approve_department(
        session=mock_session,
        department_id=dept.id,
        approver_id=uuid.uuid4(),
        approver_role="OWNER",
    )
    assert approved_dept.status == DepartmentStatus.ACTIVE
