"""Unit tests for Phase 9: Owner Console Aggregator."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.governance import SystemRunState
from domain.models.governance import ConstitutionRecord, SystemState
from domain.schemas.governance import OwnerConsoleSummary
from services.governance.router import api_owner_console_summary


@pytest.mark.asyncio
async def test_owner_console_summary_metrics():
    """Verify aggregated metrics calculation for Web Owner Console."""
    mock_session = AsyncMock()

    system_state = SystemState(
        singleton=True,
        run_state=SystemRunState.NORMAL.value,
        shutdown_reason=None,
        updated_at=datetime.now(UTC),
        updated_by=uuid.uuid4(),
    )

    constitution = ConstitutionRecord(
        id=uuid.uuid4(),
        schema_version=1,
        policy_version=1,
        sha256_hash="abc1234567890def",
        is_active=True,
        activated_at=datetime.now(UTC),
    )

    r_state = MagicMock(scalar_one_or_none=MagicMock(return_value=system_state))
    r_appr = MagicMock(scalar_one=MagicMock(return_value=3))
    r_act = MagicMock(scalar_one=MagicMock(return_value=12))
    r_susp = MagicMock(scalar_one=MagicMock(return_value=1))
    r_dept = MagicMock(scalar_one=MagicMock(return_value=10))
    r_task = MagicMock(scalar_one=MagicMock(return_value=5))
    r_bridge = MagicMock(scalar_one=MagicMock(return_value=2))
    r_cand = MagicMock(scalar_one=MagicMock(return_value=4))
    r_const = MagicMock(scalar_one_or_none=MagicMock(return_value=constitution))
    r_audit = MagicMock(scalar_one=MagicMock(return_value=85))

    mock_session.execute.side_effect = [
        r_state,
        r_appr,
        r_act,
        r_susp,
        r_dept,
        r_task,
        r_bridge,
        r_cand,
        r_const,
        r_audit,
    ]

    mock_owner = MagicMock(owner_id=uuid.uuid4())

    summary: OwnerConsoleSummary = await api_owner_console_summary(
        session=mock_session,
        owner=mock_owner,
    )

    assert summary.system_run_state == SystemRunState.NORMAL
    assert summary.pending_approvals_count == 3
    assert summary.active_agents_count == 12
    assert summary.suspended_agents_count == 1
    assert summary.departments_count == 10
    assert summary.active_tasks_count == 5
    assert summary.active_bridges_count == 2
    assert summary.evolution_candidates_count == 4
    assert summary.recent_audit_count == 85
    assert summary.constitution_hash == "abc1234567890def"
