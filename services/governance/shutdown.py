"""Emergency shutdown service — owner emergency switch and override controls."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from domain.enums.governance import SystemRunState
from domain.models.governance import SystemState
from domain.schemas.audit import AuditEventCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


async def get_system_state(session: AsyncSession) -> SystemState:
    """Retrieve the current persistent system state."""
    result = await session.execute(
        select(SystemState).where(SystemState.singleton.is_(True)).with_for_update()
    )
    state = result.scalar_one_or_none()
    if state is None:
        # Failsafe: if row is missing, seed normal state
        state = SystemState(
            id=uuid.uuid4(),
            singleton=True,
            run_state=SystemRunState.NORMAL,
            updated_at=datetime.now(UTC),
        )
        session.add(state)
        await session.flush()
    return state


async def trigger_emergency_shutdown(
    session: AsyncSession,
    owner_id: uuid.UUID,
    reason: str,
    audit_engine: AsyncEngine | None = None,
) -> SystemState:
    """Trigger system-wide emergency shutdown.

    Only the System Owner can invoke this.
    Blocks all non-owner operations and agent tool executions.
    """
    now = datetime.now(UTC)
    state = await get_system_state(session)
    state.run_state = SystemRunState.EMERGENCY_SHUTDOWN
    state.shutdown_reason = reason
    state.updated_by = owner_id
    state.updated_at = now

    logger.critical("emergency_shutdown_triggered", owner_id=str(owner_id), reason=reason)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=owner_id,
            actor_role="OWNER",
            action="emergency_shutdown",
            decision="ALLOW",
            reason=reason,
            payload={"run_state": SystemRunState.EMERGENCY_SHUTDOWN},
        ),
    )

    return state


async def override_system_state(
    session: AsyncSession,
    owner_id: uuid.UUID,
    target_state: SystemRunState,
    reason: str,
    audit_engine: AsyncEngine | None = None,
) -> SystemState:
    """Owner override to restore or adjust system run state."""
    now = datetime.now(UTC)
    state = await get_system_state(session)
    previous_state = state.run_state

    state.run_state = target_state
    if target_state == SystemRunState.NORMAL:
        state.shutdown_reason = None
    else:
        state.shutdown_reason = reason
    state.updated_by = owner_id
    state.updated_at = now

    logger.info(
        "system_run_state_overridden",
        owner_id=str(owner_id),
        previous_state=previous_state,
        new_state=target_state,
        reason=reason,
    )

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=owner_id,
            actor_role="OWNER",
            action="owner_override",
            decision="ALLOW",
            reason=reason,
            payload={"previous_state": previous_state, "target_state": target_state},
        ),
    )

    return state
