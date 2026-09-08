"""Approval service — state machine, risk policies, and decision recording."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.governance import ApprovalStatus, RiskLevel
from domain.models.governance import Approval
from domain.schemas.audit import AuditEventCreate
from domain.schemas.governance import ApprovalCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class ApprovalError(Exception):
    """Business logic errors in approval processing."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def create_approval(
    session: AsyncSession,
    data: ApprovalCreate,
) -> Approval:
    """Create a new pending approval item."""
    approval = Approval(
        id=uuid.uuid4(),
        action_type=data.action_type,
        requested_by=data.requested_by,
        task_id=data.task_id,
        target_id=data.target_id,
        risk_level=data.risk_level,
        status=ApprovalStatus.PENDING,
        reason=data.reason,
        created_at=datetime.now(UTC),
    )
    session.add(approval)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=data.requested_by,
            actor_role="SYSTEM",
            action="approval_created",
            decision="ALLOW",
            reason=data.reason,
            target_id=approval.id,
            target_type="APPROVAL",
            payload={"action_type": data.action_type, "risk_level": data.risk_level},
        ),
    )

    return approval


async def list_approvals(
    session: AsyncSession,
    status: ApprovalStatus | None = None,
    limit: int = 50,
) -> list[Approval]:
    """List approvals with optional status filtering."""
    query = select(Approval).order_by(Approval.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(Approval.status == status)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_approval(
    session: AsyncSession,
    approval_id: uuid.UUID,
) -> Approval | None:
    """Get approval by ID."""
    result = await session.execute(select(Approval).where(Approval.id == approval_id))
    return result.scalar_one_or_none()


async def decide_approval(
    session: AsyncSession,
    approval_id: uuid.UUID,
    decision: ApprovalStatus,
    decided_by: uuid.UUID,
    decider_role: str,
    reason: str,
) -> Approval:
    """Submit approval decision (APPROVED or REJECTED).

    Rules:
    - Status must currently be PENDING.
    - CRITICAL risk actions strictly require OWNER role.
    """
    if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        raise ApprovalError("Invalid decision; must be APPROVED or REJECTED")

    result = await session.execute(
        select(Approval).where(Approval.id == approval_id).with_for_update()
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise ApprovalError("Approval not found")

    if approval.status != ApprovalStatus.PENDING:
        raise ApprovalError(f"Approval already in status: {approval.status}")

    # Governance rule: CRITICAL actions require OWNER role
    if approval.risk_level == RiskLevel.CRITICAL and decider_role != "OWNER":
        raise ApprovalError("CRITICAL risk actions require System Owner approval")

    now = datetime.now(UTC)
    approval.status = decision
    approval.decision = decision
    approval.decided_by = decided_by
    approval.reason = reason
    approval.decided_at = now

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=decided_by,
            actor_role=decider_role,
            action=f"approval_{decision.lower()}",
            decision="ALLOW",
            reason=reason,
            target_id=approval.id,
            target_type="APPROVAL",
            payload={"action_type": approval.action_type, "risk_level": approval.risk_level},
        ),
    )

    return approval
