"""Task and mission engine with department isolation and state transitions."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.agent_status import AgentStatus
from domain.enums.tasks import BridgeStatus, TaskPriority, TaskStatus
from domain.models.agents import Agent, Department
from domain.models.tasks import CrossDepartmentBridge, Task, TaskDelegation
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tasks import (
    TaskCreate,
    TaskDelegationCreate,
    TaskStatusTransition,
)
from services.audit.service import log_audit_event
from services.bridges.service import check_active_bridge

logger = structlog.get_logger()

# Valid task state transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.AWAITING_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.AWAITING_REVIEW: {
        TaskStatus.COMPLETED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.FAILED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskError(Exception):
    """Business logic errors for tasks and delegations."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def create_task(
    session: AsyncSession,
    data: TaskCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> Task:
    """Create a new task or mission enforcing department isolation.

    Rules:
    - If origin_department != assigned_department, an ACTIVE bridge MUST exist.
    - If assigned_agent_id is provided, agent must exist, be ACTIVE,
      and belong to assigned_department.
    """
    # 1. Check departments
    orig_res = await session.execute(
        select(Department).where(Department.id == data.origin_department_id)
    )
    orig_dept = orig_res.scalar_one_or_none()
    if not orig_dept or orig_dept.status != "ACTIVE":
        raise TaskError("Origin department not found or not active")

    assign_res = await session.execute(
        select(Department).where(Department.id == data.assigned_department_id)
    )
    assign_dept = assign_res.scalar_one_or_none()
    if not assign_dept or assign_dept.status != "ACTIVE":
        raise TaskError("Assigned department not found or not active")

    # 2. Inter-department boundary enforcement
    if data.origin_department_id != data.assigned_department_id:
        bridge = await check_active_bridge(
            session, data.origin_department_id, data.assigned_department_id
        )
        if not bridge:
            raise TaskError(
                f"Cross-department task between '{orig_dept.name}' and '{assign_dept.name}' "
                "requires an active CrossDepartmentBridge"
            )

    # 3. Check assigned agent if provided
    initial_status = TaskStatus.CREATED
    if data.assigned_agent_id:
        agent_res = await session.execute(select(Agent).where(Agent.id == data.assigned_agent_id))
        agent = agent_res.scalar_one_or_none()
        if not agent or agent.status != AgentStatus.ACTIVE:
            raise TaskError("Assigned agent not found or not active")
        if agent.department_id != data.assigned_department_id:
            raise TaskError("Assigned agent does not belong to the assigned department")
        initial_status = TaskStatus.ASSIGNED

    task = Task(
        id=uuid.uuid4(),
        title=data.title,
        description=data.description,
        priority=data.priority,
        status=initial_status,
        origin_department_id=data.origin_department_id,
        assigned_department_id=data.assigned_department_id,
        assigned_agent_id=data.assigned_agent_id,
        created_by=creator_id,
        parent_task_id=data.parent_task_id,
        required_capabilities=data.required_capabilities,
        input_artifacts=data.input_artifacts,
        output_artifacts=None,
        budget_allocated=data.budget_allocated,
        budget_spent=0.0,
        deadline=data.deadline,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(task)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=creator_id,
            actor_role=creator_role,
            action="task_created",
            decision="ALLOW",
            reason=f"Task '{task.title}' created in department {assign_dept.name}",
            target_id=task.id,
            target_type="TASK",
            payload={
                "origin_department_id": str(task.origin_department_id),
                "assigned_department_id": str(task.assigned_department_id),
                "priority": task.priority,
            },
        ),
    )
    return task


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Fetch task by ID."""
    res = await session.execute(select(Task).where(Task.id == task_id))
    return res.scalar_one_or_none()


async def assign_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    assigner_id: uuid.UUID,
    assigner_role: str,
) -> Task:
    """Assign an agent to an existing task."""
    task = await get_task(session, task_id)
    if not task:
        raise TaskError("Task not found")

    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise TaskError(f"Cannot assign task in terminal status {task.status}")

    agent_res = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_res.scalar_one_or_none()
    if not agent or agent.status != AgentStatus.ACTIVE:
        raise TaskError("Agent not found or not active")

    if agent.department_id != task.assigned_department_id:
        # Cross-department check
        bridge = await check_active_bridge(
            session, task.assigned_department_id, agent.department_id
        )
        if not bridge:
            raise TaskError("Assigning agent from different department requires an active bridge")

    task.assigned_agent_id = agent_id
    task.status = TaskStatus.ASSIGNED
    task.updated_at = datetime.now(UTC)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=assigner_id,
            actor_role=assigner_role,
            action="task_assigned",
            decision="ALLOW",
            reason=f"Task assigned to agent {agent.display_name}",
            target_id=task.id,
            target_type="TASK",
            payload={"agent_id": str(agent_id)},
        ),
    )
    return task


async def transition_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    transition: TaskStatusTransition,
    actor_id: uuid.UUID,
    actor_role: str,
) -> Task:
    """Perform a validated status transition on a task."""
    task = await get_task(session, task_id)
    if not task:
        raise TaskError("Task not found")

    current_status = TaskStatus(task.status)
    target_status = transition.status

    allowed = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise TaskError(
            f"Invalid transition from {current_status} to {target_status}. Allowed: {allowed}"
        )

    now = datetime.now(UTC)
    task.status = target_status
    task.updated_at = now

    if transition.output_artifacts:
        task.output_artifacts = transition.output_artifacts

    if target_status == TaskStatus.COMPLETED:
        task.completed_at = now

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=actor_id,
            actor_role=actor_role,
            action="task_status_transition",
            decision="ALLOW",
            reason=transition.reason,
            target_id=task.id,
            target_type="TASK",
            payload={
                "from_status": current_status,
                "to_status": target_status,
            },
        ),
    )
    return task


async def delegate_task(
    session: AsyncSession,
    data: TaskDelegationCreate,
    delegator_id: uuid.UUID,
    delegator_role: str,
) -> TaskDelegation:
    """Delegate a task across an active department bridge."""
    task = await get_task(session, data.task_id)
    if not task:
        raise TaskError("Task not found")

    bridge_res = await session.execute(
        select(CrossDepartmentBridge).where(
            CrossDepartmentBridge.id == data.bridge_id,
            CrossDepartmentBridge.status == BridgeStatus.ACTIVE,
            CrossDepartmentBridge.expires_at > datetime.now(UTC),
        )
    )
    bridge = bridge_res.scalar_one_or_none()
    if not bridge:
        raise TaskError("Active, unexpired cross-department bridge required for delegation")

    target_agent_res = await session.execute(
        select(Agent).where(Agent.id == data.delegated_to_agent_id)
    )
    target_agent = target_agent_res.scalar_one_or_none()
    if not target_agent or target_agent.status != AgentStatus.ACTIVE:
        raise TaskError("Delegation target agent not found or not active")

    # Ensure target agent is in one of the bridged departments
    bridged_depts = {bridge.source_department_id, bridge.target_department_id}
    if target_agent.department_id not in bridged_depts:
        raise TaskError("Target agent does not belong to either bridged department")

    delegation = TaskDelegation(
        id=uuid.uuid4(),
        task_id=data.task_id,
        bridge_id=data.bridge_id,
        delegated_from_agent_id=delegator_id,
        delegated_to_agent_id=data.delegated_to_agent_id,
        notes=data.notes,
        created_at=datetime.now(UTC),
    )
    session.add(delegation)

    # Reassign task to target agent
    task.assigned_agent_id = data.delegated_to_agent_id
    task.assigned_department_id = target_agent.department_id
    task.status = TaskStatus.ASSIGNED
    task.updated_at = datetime.now(UTC)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=delegator_id,
            actor_role=delegator_role,
            action="task_delegated",
            decision="ALLOW",
            reason=f"Task delegated to agent {target_agent.display_name} via bridge {bridge.id}",
            target_id=task.id,
            target_type="TASK",
            payload={
                "delegated_to_agent_id": str(data.delegated_to_agent_id),
                "bridge_id": str(data.bridge_id),
            },
        ),
    )
    return delegation


async def list_tasks(
    session: AsyncSession,
    department_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: int = 100,
) -> list[Task]:
    """List tasks with optional filtering."""
    query = select(Task).order_by(Task.created_at.desc()).limit(limit)
    if department_id:
        query = query.where(Task.assigned_department_id == department_id)
    if agent_id:
        query = query.where(Task.assigned_agent_id == agent_id)
    if status:
        query = query.where(Task.status == status)
    if priority:
        query = query.where(Task.priority == priority)

    res = await session.execute(query)
    return list(res.scalars().all())
