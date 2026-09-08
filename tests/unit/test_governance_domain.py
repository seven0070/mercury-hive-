"""Unit tests for Phase 2 governance domain logic and permissions engine."""

import uuid

import pytest

from domain.enums.governance import ApprovalStatus, RiskLevel, SystemRunState
from services.permissions.engine import Decision, authorize


@pytest.mark.asyncio
async def test_authorize_normal_state_owner_allowed():
    """Owner is allowed during normal system state."""
    owner_id = uuid.uuid4()
    result = await authorize(
        actor_id=owner_id,
        actor_role="OWNER",
        actor_status="ACTIVE",
        action="read",
        resource="system",
        system_run_state=SystemRunState.NORMAL,
    )
    assert result.decision == Decision.ALLOW
    assert result.reason == "owner_authorized"


@pytest.mark.asyncio
async def test_authorize_emergency_shutdown_blocks_non_owner():
    """Non-owner roles are immediately denied during emergency shutdown."""
    agent_id = uuid.uuid4()
    result = await authorize(
        actor_id=agent_id,
        actor_role="WORKER",
        actor_status="ACTIVE",
        action="execute_tool",
        resource="calculator",
        system_run_state=SystemRunState.EMERGENCY_SHUTDOWN,
    )
    assert result.decision == Decision.DENY
    assert result.reason == "emergency_shutdown_active"


@pytest.mark.asyncio
async def test_authorize_emergency_shutdown_allows_owner():
    """Owner remains authorized to operate and override during emergency shutdown."""
    owner_id = uuid.uuid4()
    result = await authorize(
        actor_id=owner_id,
        actor_role="OWNER",
        actor_status="ACTIVE",
        action="emergency_override",
        resource="system",
        system_run_state=SystemRunState.EMERGENCY_SHUTDOWN,
    )
    assert result.decision == Decision.ALLOW
    assert result.reason == "owner_authorized"


def test_approval_status_enums():
    """Verify approval status enums."""
    assert ApprovalStatus.PENDING == "PENDING"
    assert ApprovalStatus.APPROVED == "APPROVED"
    assert ApprovalStatus.REJECTED == "REJECTED"
    assert ApprovalStatus.CANCELLED == "CANCELLED"


def test_risk_level_enums():
    """Verify risk level enums."""
    assert RiskLevel.LOW == "LOW"
    assert RiskLevel.MEDIUM == "MEDIUM"
    assert RiskLevel.HIGH == "HIGH"
    assert RiskLevel.CRITICAL == "CRITICAL"
