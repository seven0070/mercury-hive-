"""Cross-department bridge lifecycle, isolation controls, and permission auditing."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.agent_status import DataClassification
from domain.enums.roles import SystemRole
from domain.enums.tasks import BridgeStatus
from domain.models.agents import Department
from domain.models.tasks import CrossDepartmentBridge
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tasks import BridgeCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class BridgeError(Exception):
    """Business logic errors for cross-department bridges."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def request_bridge(
    session: AsyncSession,
    data: BridgeCreate,
    requester_id: uuid.UUID,
    requester_role: str,
) -> CrossDepartmentBridge:
    """Request a cross-department bridge with strict boundary verification.

    Rules:
    - Workers cannot request bridges (only Managers, HR, CEO, Owner).
    - Source and target departments must exist, be ACTIVE, and be distinct.
    - Bridge expires in the future.
    - Bridges start in PENDING state awaiting approval.
    """
    if requester_role == SystemRole.WORKER:
        raise BridgeError("Workers cannot request cross-department bridges")

    if data.source_department_id == data.target_department_id:
        raise BridgeError("Source and target departments must be different")

    if data.expires_at <= datetime.now(UTC):
        raise BridgeError("Bridge expiration must be in the future")

    # Verify both departments
    src_res = await session.execute(
        select(Department).where(Department.id == data.source_department_id)
    )
    src_dept = src_res.scalar_one_or_none()
    if not src_dept or src_dept.status != "ACTIVE":
        raise BridgeError("Source department not found or not active")

    tgt_res = await session.execute(
        select(Department).where(Department.id == data.target_department_id)
    )
    tgt_dept = tgt_res.scalar_one_or_none()
    if not tgt_dept or tgt_dept.status != "ACTIVE":
        raise BridgeError("Target department not found or not active")

    # Prevent accidental downgrade of confidential/restricted data
    if (
        src_dept.data_classification
        in [DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED]
        and tgt_dept.data_classification == DataClassification.PUBLIC
        and requester_role not in ["OWNER", SystemRole.CEO]
    ):
        raise BridgeError(
            "Bridging confidential or restricted data to a public "
            "department requires CEO or Owner approval"
        )

    bridge = CrossDepartmentBridge(
        id=uuid.uuid4(),
        source_department_id=data.source_department_id,
        target_department_id=data.target_department_id,
        purpose=data.purpose,
        status=BridgeStatus.PENDING,
        allowed_data_classification=data.allowed_data_classification,
        data_sharing_scopes=data.data_sharing_scopes,
        requested_by=requester_id,
        expires_at=data.expires_at,
        created_at=datetime.now(UTC),
    )
    session.add(bridge)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=requester_id,
            actor_role=requester_role,
            action="bridge_requested",
            decision="ALLOW",
            reason=f"Bridge requested from {src_dept.name} to {tgt_dept.name}",
            target_id=bridge.id,
            target_type="CROSS_DEPARTMENT_BRIDGE",
            payload={
                "source_department_id": str(bridge.source_department_id),
                "target_department_id": str(bridge.target_department_id),
                "allowed_data_classification": bridge.allowed_data_classification,
            },
        ),
    )
    return bridge


async def get_bridge(
    session: AsyncSession,
    bridge_id: uuid.UUID,
) -> CrossDepartmentBridge | None:
    """Fetch bridge by ID."""
    res = await session.execute(
        select(CrossDepartmentBridge).where(CrossDepartmentBridge.id == bridge_id)
    )
    return res.scalar_one_or_none()


async def approve_bridge(
    session: AsyncSession,
    bridge_id: uuid.UUID,
    approver_id: uuid.UUID,
    approver_role: str,
    reason: str,
) -> CrossDepartmentBridge:
    """Approve a proposed bridge and activate it."""
    if approver_role not in ["OWNER", SystemRole.CEO, SystemRole.DEPARTMENT_MANAGER]:
        raise BridgeError("Only Managers, CEO, or Owner can approve bridges")

    bridge = await get_bridge(session, bridge_id)
    if not bridge:
        raise BridgeError("Bridge not found")

    if bridge.status != BridgeStatus.PENDING:
        raise BridgeError(f"Cannot approve bridge in status {bridge.status}")

    now = datetime.now(UTC)
    if bridge.expires_at <= now:
        bridge.status = BridgeStatus.EXPIRED
        raise BridgeError("Cannot approve expired bridge")

    bridge.status = BridgeStatus.ACTIVE
    bridge.approved_by = approver_id

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=approver_id,
            actor_role=approver_role,
            action="bridge_approved",
            decision="ALLOW",
            reason=reason,
            target_id=bridge.id,
            target_type="CROSS_DEPARTMENT_BRIDGE",
        ),
    )
    return bridge


async def revoke_bridge(
    session: AsyncSession,
    bridge_id: uuid.UUID,
    revoker_id: uuid.UUID,
    revoker_role: str,
    reason: str,
) -> CrossDepartmentBridge:
    """Revoke an active bridge immediately."""
    bridge = await get_bridge(session, bridge_id)
    if not bridge:
        raise BridgeError("Bridge not found")

    bridge.status = BridgeStatus.REVOKED
    bridge.revoked_at = datetime.now(UTC)
    bridge.revocation_reason = reason

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=revoker_id,
            actor_role=revoker_role,
            action="bridge_revoked",
            decision="ALLOW",
            reason=reason,
            target_id=bridge.id,
            target_type="CROSS_DEPARTMENT_BRIDGE",
        ),
    )
    return bridge


async def check_active_bridge(
    session: AsyncSession,
    source_dept_id: uuid.UUID,
    target_dept_id: uuid.UUID,
) -> CrossDepartmentBridge | None:
    """Check if an active, unexpired bridge exists between two departments (bidirectional)."""
    now = datetime.now(UTC)
    res = await session.execute(
        select(CrossDepartmentBridge).where(
            CrossDepartmentBridge.status == BridgeStatus.ACTIVE,
            CrossDepartmentBridge.expires_at > now,
            or_(
                (CrossDepartmentBridge.source_department_id == source_dept_id)
                & (CrossDepartmentBridge.target_department_id == target_dept_id),
                (CrossDepartmentBridge.source_department_id == target_dept_id)
                & (CrossDepartmentBridge.target_department_id == source_dept_id),
            ),
        )
    )
    return res.scalars().first()


async def list_bridges(
    session: AsyncSession,
    department_id: uuid.UUID | None = None,
    status: BridgeStatus | None = None,
    limit: int = 100,
) -> list[CrossDepartmentBridge]:
    """List cross-department bridges with optional filtering."""
    query = (
        select(CrossDepartmentBridge).order_by(CrossDepartmentBridge.created_at.desc()).limit(limit)
    )
    if department_id:
        query = query.where(
            or_(
                CrossDepartmentBridge.source_department_id == department_id,
                CrossDepartmentBridge.target_department_id == department_id,
            )
        )
    if status:
        query = query.where(CrossDepartmentBridge.status == status)

    res = await session.execute(query)
    return list(res.scalars().all())
