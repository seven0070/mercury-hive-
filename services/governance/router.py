"""API router for Phase 2 governance, emergency controls, and approvals."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.governance import ApprovalStatus, SystemRunState
from domain.models.audit_event import AuditEvent
from domain.models.governance import Approval, ConstitutionRecord
from domain.schemas.audit import AuditEventResponse
from domain.schemas.governance import (
    ApprovalCreate,
    ApprovalDecisionRequest,
    ApprovalResponse,
    EmergencyShutdownRequest,
    EmergencyShutdownResponse,
    OwnerDashboardResponse,
    OwnerOverrideRequest,
)
from services.governance.approvals import (
    ApprovalError,
    create_approval,
    decide_approval,
    list_approvals,
)
from services.governance.shutdown import (
    get_system_state,
    override_system_state,
    trigger_emergency_shutdown,
)

router = APIRouter(tags=["governance"])


# ============================================================
# Emergency Controls & Owner Dashboard
# ============================================================


@router.post("/owner/emergency-shutdown", response_model=EmergencyShutdownResponse)
async def api_emergency_shutdown(
    request: EmergencyShutdownRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EmergencyShutdownResponse:
    """Trigger system-wide emergency shutdown. Only accessible by Owner."""
    state = await trigger_emergency_shutdown(session, owner.owner_id, request.reason)
    return EmergencyShutdownResponse(
        run_state=SystemRunState(state.run_state),
        shutdown_reason=state.shutdown_reason,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )


@router.post("/owner/override", response_model=EmergencyShutdownResponse)
async def api_owner_override(
    request: OwnerOverrideRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EmergencyShutdownResponse:
    """Owner override to restore normal state or set target run state."""
    state = await override_system_state(
        session, owner.owner_id, request.target_state, request.reason
    )
    return EmergencyShutdownResponse(
        run_state=SystemRunState(state.run_state),
        shutdown_reason=state.shutdown_reason,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )


@router.get("/owner/dashboard", response_model=OwnerDashboardResponse)
async def api_owner_dashboard(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> OwnerDashboardResponse:
    """Retrieve owner executive dashboard summary."""
    state = await get_system_state(session)

    # Count pending approvals
    result = await session.execute(
        select(func.count(Approval.id)).where(Approval.status == ApprovalStatus.PENDING)
    )
    pending_count = result.scalar_one() or 0

    # Get active constitution record
    c_result = await session.execute(
        select(ConstitutionRecord).where(ConstitutionRecord.is_active.is_(True))
    )
    constitution = c_result.scalar_one_or_none()

    # Count recent audit events
    a_result = await session.execute(select(func.count(AuditEvent.id)))
    audit_count = a_result.scalar_one() or 0

    return OwnerDashboardResponse(
        system_run_state=SystemRunState(state.run_state),
        shutdown_reason=state.shutdown_reason,
        pending_approvals_count=pending_count,
        constitution_policy_version=constitution.policy_version if constitution else 1,
        constitution_hash=constitution.sha256_hash if constitution else "",
        recent_audit_count=audit_count,
    )


@router.get("/owner/audit", response_model=list[AuditEventResponse])
async def api_owner_audit_logs(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    limit: int = Query(default=50, ge=1, le=500),
    event_type: str | None = None,
) -> list[AuditEventResponse]:
    """Retrieve immutable audit logs for owner inspection."""
    query = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type.upper())
    result = await session.execute(query)
    return [AuditEventResponse.model_validate(event) for event in result.scalars().all()]


# ============================================================
# Approvals
# ============================================================


@router.post("/approvals", response_model=ApprovalResponse)
async def api_create_approval(
    request: ApprovalCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ApprovalResponse:
    """Submit an action requiring review/approval."""
    approval = await create_approval(session, request)
    return ApprovalResponse.model_validate(approval)


@router.get("/approvals", response_model=list[ApprovalResponse])
async def api_list_approvals(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    status: ApprovalStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ApprovalResponse]:
    """List approvals with optional status filter."""
    approvals = await list_approvals(session, status=status, limit=limit)
    return [ApprovalResponse.model_validate(app) for app in approvals]


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def api_approve(
    approval_id: uuid.UUID,
    request: ApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ApprovalResponse:
    """Approve a pending request."""
    try:
        approval = await decide_approval(
            session=session,
            approval_id=approval_id,
            decision=ApprovalStatus.APPROVED,
            decided_by=owner.owner_id,
            decider_role="OWNER",
            reason=request.reason,
        )
        return ApprovalResponse.model_validate(approval)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def api_reject(
    approval_id: uuid.UUID,
    request: ApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ApprovalResponse:
    """Reject a pending request."""
    try:
        approval = await decide_approval(
            session=session,
            approval_id=approval_id,
            decision=ApprovalStatus.REJECTED,
            decided_by=owner.owner_id,
            decider_role="OWNER",
            reason=request.reason,
        )
        return ApprovalResponse.model_validate(approval)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
