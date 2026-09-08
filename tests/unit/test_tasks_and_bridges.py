"""Unit tests for Phase 4: Tasks, Missions, and Cross-Department Bridges."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus, DataClassification
from domain.enums.roles import SystemRole
from domain.enums.tasks import BridgeStatus, TaskPriority, TaskStatus
from domain.models.agents import Agent, Department
from domain.models.tasks import CrossDepartmentBridge, Task
from domain.schemas.tasks import (
    BridgeCreate,
    TaskCreate,
    TaskDelegationCreate,
    TaskStatusTransition,
)
from services.bridges.service import (
    BridgeError,
    approve_bridge,
    request_bridge,
    revoke_bridge,
)
from services.tasks.service import (
    TaskError,
    create_task,
    delegate_task,
    transition_task_status,
)


@pytest.mark.asyncio
async def test_worker_cannot_request_bridge():
    """Worker agents are forbidden from requesting cross-department bridges."""
    mock_session = AsyncMock()
    req = BridgeCreate(
        source_department_id=uuid.uuid4(),
        target_department_id=uuid.uuid4(),
        purpose="Attempt bridge by worker",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    with pytest.raises(BridgeError, match="Workers cannot request cross-department bridges"):
        await request_bridge(
            session=mock_session,
            data=req,
            requester_id=uuid.uuid4(),
            requester_role=SystemRole.WORKER,
        )


@pytest.mark.asyncio
async def test_bridge_same_department_rejected():
    """Bridges must connect two distinct departments."""
    mock_session = AsyncMock()
    same_id = uuid.uuid4()
    req = BridgeCreate(
        source_department_id=same_id,
        target_department_id=same_id,
        purpose="Self-bridge not allowed",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    with pytest.raises(BridgeError, match="Source and target departments must be different"):
        await request_bridge(
            session=mock_session,
            data=req,
            requester_id=uuid.uuid4(),
            requester_role=SystemRole.DEPARTMENT_MANAGER,
        )


@pytest.mark.asyncio
async def test_bridge_lifecycle():
    """Requesting, approving, and revoking a bridge."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    src_dept_id = uuid.uuid4()
    tgt_dept_id = uuid.uuid4()

    dept1 = Department(
        id=src_dept_id,
        name="Research",
        purpose="R&D",
        status="ACTIVE",
        data_classification=DataClassification.INTERNAL,
        created_at=datetime.now(UTC),
    )
    dept2 = Department(
        id=tgt_dept_id,
        name="Engineering",
        purpose="Engineering",
        status="ACTIVE",
        data_classification=DataClassification.INTERNAL,
        created_at=datetime.now(UTC),
    )

    # Department lookups
    dept_res1 = MagicMock()
    dept_res1.scalar_one_or_none.return_value = dept1
    dept_res2 = MagicMock()
    dept_res2.scalar_one_or_none.return_value = dept2

    mock_session.execute.side_effect = [dept_res1, dept_res2, MagicMock()]

    req = BridgeCreate(
        source_department_id=src_dept_id,
        target_department_id=tgt_dept_id,
        purpose="Sync on AI architecture models",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    manager_id = uuid.uuid4()
    bridge = await request_bridge(
        session=mock_session,
        data=req,
        requester_id=manager_id,
        requester_role=SystemRole.DEPARTMENT_MANAGER,
    )

    assert bridge.status == BridgeStatus.PENDING
    assert bridge.source_department_id == src_dept_id
    assert bridge.target_department_id == tgt_dept_id

    # Approve bridge
    mock_session.execute.side_effect = None
    bridge_lookup = MagicMock()
    bridge_lookup.scalar_one_or_none.return_value = bridge
    mock_session.execute.return_value = bridge_lookup

    owner_id = uuid.uuid4()
    approved = await approve_bridge(
        session=mock_session,
        bridge_id=bridge.id,
        approver_id=owner_id,
        approver_role="OWNER",
        reason="Architecture collaboration approved",
    )
    assert approved.status == BridgeStatus.ACTIVE
    assert approved.approved_by == owner_id

    # Revoke bridge
    revoked = await revoke_bridge(
        session=mock_session,
        bridge_id=bridge.id,
        revoker_id=owner_id,
        revoker_role="OWNER",
        reason="Project completed",
    )
    assert revoked.status == BridgeStatus.REVOKED
    assert revoked.revoked_at is not None


@pytest.mark.asyncio
async def test_cross_department_task_requires_bridge():
    """Creating a task across departments without an active bridge must fail."""
    mock_session = AsyncMock()
    dept1_id = uuid.uuid4()
    dept2_id = uuid.uuid4()

    dept1 = Department(
        id=dept1_id,
        name="Marketing",
        purpose="Marketing",
        status="ACTIVE",
        data_classification=DataClassification.INTERNAL,
        created_at=datetime.now(UTC),
    )
    dept2 = Department(
        id=dept2_id,
        name="Finance",
        purpose="Finance",
        status="ACTIVE",
        data_classification=DataClassification.INTERNAL,
        created_at=datetime.now(UTC),
    )

    r1 = MagicMock()
    r1.scalar_one_or_none.return_value = dept1
    r2 = MagicMock()
    r2.scalar_one_or_none.return_value = dept2
    r_bridge = MagicMock()
    r_bridge.scalars.return_value.first.return_value = None  # No active bridge!

    mock_session.execute.side_effect = [r1, r2, r_bridge]

    req = TaskCreate(
        title="Cross Audit",
        description="Audit marketing spend with finance",
        origin_department_id=dept1_id,
        assigned_department_id=dept2_id,
    )

    with pytest.raises(TaskError, match="requires an active CrossDepartmentBridge"):
        await create_task(
            session=mock_session,
            data=req,
            creator_id=uuid.uuid4(),
            creator_role="OWNER",
        )


@pytest.mark.asyncio
async def test_task_status_state_machine():
    """Valid and invalid status transitions on tasks."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    task = Task(
        id=uuid.uuid4(),
        title="Develop Core Feature",
        description="Feature implementation",
        priority=TaskPriority.HIGH,
        status=TaskStatus.CREATED,
        origin_department_id=uuid.uuid4(),
        assigned_department_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    task_res = MagicMock()
    task_res.scalar_one_or_none.return_value = task
    mock_session.execute.return_value = task_res

    # 1. Invalid transition directly to COMPLETED from CREATED
    with pytest.raises(TaskError, match="Invalid transition"):
        await transition_task_status(
            session=mock_session,
            task_id=task.id,
            transition=TaskStatusTransition(
                status=TaskStatus.COMPLETED,
                reason="Premature completion",
            ),
            actor_id=uuid.uuid4(),
            actor_role="OWNER",
        )

    # 2. Valid transition: CREATED -> ASSIGNED
    t1 = await transition_task_status(
        session=mock_session,
        task_id=task.id,
        transition=TaskStatusTransition(
            status=TaskStatus.ASSIGNED,
            reason="Worker assigned",
        ),
        actor_id=uuid.uuid4(),
        actor_role="OWNER",
    )
    assert t1.status == TaskStatus.ASSIGNED

    # 3. Valid transition: ASSIGNED -> IN_PROGRESS
    t2 = await transition_task_status(
        session=mock_session,
        task_id=task.id,
        transition=TaskStatusTransition(
            status=TaskStatus.IN_PROGRESS,
            reason="Work begun",
        ),
        actor_id=uuid.uuid4(),
        actor_role="OWNER",
    )
    assert t2.status == TaskStatus.IN_PROGRESS

    # 4. Valid transition: IN_PROGRESS -> COMPLETED
    t3 = await transition_task_status(
        session=mock_session,
        task_id=task.id,
        transition=TaskStatusTransition(
            status=TaskStatus.COMPLETED,
            reason="Work delivered and verified",
            output_artifacts={"commit_sha": "abc1234"},
        ),
        actor_id=uuid.uuid4(),
        actor_role="OWNER",
    )
    assert t3.status == TaskStatus.COMPLETED
    assert t3.completed_at is not None
    assert t3.output_artifacts == {"commit_sha": "abc1234"}

    # 5. Terminal state cannot transition anywhere
    with pytest.raises(TaskError, match="Invalid transition"):
        await transition_task_status(
            session=mock_session,
            task_id=task.id,
            transition=TaskStatusTransition(
                status=TaskStatus.IN_PROGRESS,
                reason="Attempt reopen",
            ),
            actor_id=uuid.uuid4(),
            actor_role="OWNER",
        )


@pytest.mark.asyncio
async def test_task_delegation_across_bridge():
    """Delegating a task to an agent in a bridged department succeeds."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute.return_value = MagicMock()

    dept1_id = uuid.uuid4()
    dept2_id = uuid.uuid4()
    bridge_id = uuid.uuid4()
    target_agent_id = uuid.uuid4()

    task = Task(
        id=uuid.uuid4(),
        title="Backend Optimization",
        description="Profile and optimize query paths",
        priority=TaskPriority.HIGH,
        status=TaskStatus.ASSIGNED,
        origin_department_id=dept1_id,
        assigned_department_id=dept1_id,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    bridge = CrossDepartmentBridge(
        id=bridge_id,
        source_department_id=dept1_id,
        target_department_id=dept2_id,
        purpose="Engineering to Operations delegation",
        status=BridgeStatus.ACTIVE,
        allowed_data_classification=DataClassification.INTERNAL,
        requested_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=2),
        created_at=datetime.now(UTC),
    )

    target_agent = Agent(
        id=target_agent_id,
        display_name="Ops Worker Delta",
        role=SystemRole.WORKER,
        department_id=dept2_id,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    task_res = MagicMock()
    task_res.scalar_one_or_none.return_value = task

    bridge_res = MagicMock()
    bridge_res.scalar_one_or_none.return_value = bridge

    agent_res = MagicMock()
    agent_res.scalar_one_or_none.return_value = target_agent

    mock_session.execute.side_effect = [task_res, bridge_res, agent_res, MagicMock()]

    del_req = TaskDelegationCreate(
        task_id=task.id,
        bridge_id=bridge_id,
        delegated_to_agent_id=target_agent_id,
        notes="Please profile DB queries",
    )

    delegation = await delegate_task(
        session=mock_session,
        data=del_req,
        delegator_id=uuid.uuid4(),
        delegator_role=SystemRole.DEPARTMENT_MANAGER,
    )

    assert delegation.task_id == task.id
    assert delegation.bridge_id == bridge_id
    assert delegation.delegated_to_agent_id == target_agent_id
    assert task.assigned_agent_id == target_agent_id
    assert task.assigned_department_id == dept2_id
