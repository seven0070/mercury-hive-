"""Pydantic schemas for Phase 2 governance, approvals, and emergency controls."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from domain.enums.governance import RiskLevel, SystemRunState


class EmergencyShutdownRequest(BaseModel):
    """Payload to trigger emergency shutdown."""

    reason: str = Field(..., min_length=5, max_length=1000)


class OwnerOverrideRequest(BaseModel):
    """Payload for owner override / reactivation."""

    reason: str = Field(..., min_length=5, max_length=1000)
    target_state: SystemRunState = SystemRunState.NORMAL


class EmergencyShutdownResponse(BaseModel):
    """Current system emergency run state."""

    run_state: SystemRunState
    shutdown_reason: str | None
    updated_at: datetime
    updated_by: uuid.UUID | None

    model_config = {"from_attributes": True}


class ApprovalCreate(BaseModel):
    """Request to create an approval item."""

    action_type: str = Field(..., max_length=100)
    requested_by: uuid.UUID
    task_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    """Decision submitted for an approval."""

    reason: str = Field(..., min_length=1, max_length=1000)


class ApprovalResponse(BaseModel):
    """Response representation of an approval."""

    id: uuid.UUID
    action_type: str
    requested_by: uuid.UUID
    task_id: uuid.UUID | None
    target_id: uuid.UUID | None
    risk_level: str
    status: str
    decision: str | None
    decided_by: uuid.UUID | None
    reason: str | None
    created_at: datetime
    decided_at: datetime | None

    model_config = {"from_attributes": True}


class OwnerDashboardResponse(BaseModel):
    """Owner high-level company and security governance dashboard."""

    system_run_state: SystemRunState
    shutdown_reason: str | None
    pending_approvals_count: int
    constitution_policy_version: int
    constitution_hash: str
    recent_audit_count: int
