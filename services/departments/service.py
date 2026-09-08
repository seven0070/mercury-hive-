"""Department management and lifecycle service."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.agent_status import DepartmentStatus
from domain.models.agents import Department
from domain.schemas.agents import DepartmentCreate
from domain.schemas.audit import AuditEventCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class DepartmentError(Exception):
    """Department domain errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def list_departments(
    session: AsyncSession,
    status: DepartmentStatus | None = None,
) -> list[Department]:
    """List departments with optional status filter."""
    query = select(Department).order_by(Department.name.asc())
    if status:
        query = query.where(Department.status == status)
    res = await session.execute(query)
    return list(res.scalars().all())


async def get_department(
    session: AsyncSession,
    department_id: uuid.UUID,
) -> Department | None:
    """Fetch department by ID."""
    res = await session.execute(select(Department).where(Department.id == department_id))
    return res.scalar_one_or_none()


async def propose_department(
    session: AsyncSession,
    data: DepartmentCreate,
    proposer_id: uuid.UUID,
    proposer_role: str,
) -> Department:
    """Propose a new department.

    Governance rule:
    Agents may propose departments, but they enter status PROPOSED
    and cannot be activated without owner approval.
    """
    # Check name uniqueness
    existing = await session.execute(select(Department).where(Department.name == data.name))
    if existing.scalar_one_or_none():
        raise DepartmentError(f"Department with name '{data.name}' already exists")

    dept = Department(
        id=uuid.uuid4(),
        name=data.name,
        purpose=data.purpose,
        status=DepartmentStatus.PROPOSED,
        data_classification=data.data_classification,
        budget=data.budget,
        workspace_metadata=data.workspace_metadata,
        created_at=datetime.now(UTC),
    )
    session.add(dept)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=proposer_id,
            actor_role=proposer_role,
            action="department_proposed",
            decision="ALLOW",
            reason=f"Department '{dept.name}' proposed",
            target_id=dept.id,
            target_type="DEPARTMENT",
        ),
    )
    return dept


async def approve_department(
    session: AsyncSession,
    department_id: uuid.UUID,
    approver_id: uuid.UUID,
    approver_role: str,
) -> Department:
    """Approve a proposed department and activate it."""
    if approver_role != "OWNER":
        raise DepartmentError("Only the System Owner can approve departments")

    dept = await get_department(session, department_id)
    if not dept:
        raise DepartmentError("Department not found")

    dept.status = DepartmentStatus.ACTIVE
    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=approver_id,
            actor_role=approver_role,
            action="department_approved",
            decision="ALLOW",
            target_id=dept.id,
            target_type="DEPARTMENT",
        ),
    )
    return dept


async def suspend_department(
    session: AsyncSession,
    department_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    reason: str,
) -> Department:
    """Suspend an active department."""
    if actor_role != "OWNER":
        raise DepartmentError("Only the System Owner can suspend departments")

    dept = await get_department(session, department_id)
    if not dept:
        raise DepartmentError("Department not found")

    dept.status = DepartmentStatus.SUSPENDED
    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=actor_id,
            actor_role=actor_role,
            action="department_suspended",
            decision="ALLOW",
            reason=reason,
            target_id=dept.id,
            target_type="DEPARTMENT",
        ),
    )
    return dept
