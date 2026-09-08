"""Automated repair and state rollback service."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tools import RollbackStatus
from domain.models.tools import RollbackArtifact
from domain.schemas.audit import AuditEventCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class RollbackError(Exception):
    """Business logic errors for rollback operations."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def execute_rollback(
    session: AsyncSession,
    rollback_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    reason: str,
) -> RollbackArtifact:
    """Revert a previous mutating tool action using its stored RollbackArtifact."""
    if actor_role not in ["OWNER", "CEO", "DEPARTMENT_MANAGER"]:
        raise RollbackError("Only Owner, CEO, or Managers can trigger rollbacks", status_code=403)

    res = await session.execute(select(RollbackArtifact).where(RollbackArtifact.id == rollback_id))
    artifact = res.scalar_one_or_none()
    if not artifact:
        raise RollbackError("Rollback artifact not found", status_code=404)

    if artifact.status != RollbackStatus.AVAILABLE:
        raise RollbackError(f"Cannot rollback artifact in status '{artifact.status}'")

    now = datetime.now(UTC)
    artifact.status = RollbackStatus.EXECUTED
    artifact.reverted_at = now
    artifact.reverted_by = actor_id

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            action="rollback_executed",
            decision="ALLOW",
            reason=reason,
            target_id=artifact.id,
            target_type="ROLLBACK_ARTIFACT",
            payload={
                "tool_name": artifact.tool_name,
                "target_resource": artifact.target_resource,
                "restored_state": artifact.previous_state,
            },
        ),
    )
    return artifact


async def list_rollbacks(
    session: AsyncSession,
    task_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    status: RollbackStatus | None = None,
    limit: int = 100,
) -> list[RollbackArtifact]:
    """List rollback artifacts with optional filtering."""
    query = select(RollbackArtifact).order_by(RollbackArtifact.created_at.desc()).limit(limit)
    if task_id:
        query = query.where(RollbackArtifact.task_id == task_id)
    if agent_id:
        query = query.where(RollbackArtifact.agent_id == agent_id)
    if status:
        query = query.where(RollbackArtifact.status == status)

    res = await session.execute(query)
    return list(res.scalars().all())
