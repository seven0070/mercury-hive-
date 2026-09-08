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

_cached_run_state: SystemRunState = SystemRunState.NORMAL
_cached_shutdown_reason: str | None = None


def get_cached_run_state() -> tuple[SystemRunState, str | None]:
    """Get the current in-memory cached run state and optional reason."""
    return _cached_run_state, _cached_shutdown_reason


def set_cached_run_state(state: SystemRunState, reason: str | None = None) -> None:
    """Set the in-memory cached run state and optional reason."""
    global _cached_run_state, _cached_shutdown_reason
    _cached_run_state = state
    _cached_shutdown_reason = reason


async def get_system_state(session: AsyncSession, for_update: bool = False) -> SystemState:
    """Retrieve the current persistent system state."""
    query = select(SystemState).where(SystemState.singleton.is_(True))
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    state = result.scalar_one_or_none()
    if state is None:
        # Failsafe: if row is missing, seed state using current cached state
        state = SystemState(
            id=uuid.uuid4(),
            singleton=True,
            run_state=(
                _cached_run_state.value
                if isinstance(_cached_run_state, SystemRunState)
                else _cached_run_state
            ),
            shutdown_reason=_cached_shutdown_reason,
            updated_at=datetime.now(UTC),
        )
        session.add(state)
        await session.flush()
    else:
        set_cached_run_state(SystemRunState(state.run_state), state.shutdown_reason)
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
    state = await get_system_state(session, for_update=True)
    state.run_state = SystemRunState.EMERGENCY_SHUTDOWN
    state.shutdown_reason = reason
    state.updated_by = owner_id
    state.updated_at = now
    set_cached_run_state(SystemRunState.EMERGENCY_SHUTDOWN, reason)

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
    state = await get_system_state(session, for_update=True)
    previous_state = state.run_state

    state.run_state = target_state
    if target_state == SystemRunState.NORMAL:
        state.shutdown_reason = None
    else:
        state.shutdown_reason = reason
    state.updated_by = owner_id
    state.updated_at = now
    set_cached_run_state(target_state, state.shutdown_reason)

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
