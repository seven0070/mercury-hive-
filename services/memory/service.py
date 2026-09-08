"""Scoped Agent Memory service with optimistic locking and boundary isolation."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tools import MemoryScope
from domain.models.agents import Agent, PermissionGrant
from domain.models.tools import AgentMemory
from domain.schemas.audit import AuditEventCreate
from domain.schemas.tools import AgentMemoryStore
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class MemoryError(Exception):
    """Memory domain errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def store_memory(
    session: AsyncSession,
    agent_id: uuid.UUID,
    data: AgentMemoryStore,
    actor_id: uuid.UUID,
    actor_role: str,
) -> AgentMemory:
    """Store or update a scoped key-value memory item."""
    now = datetime.now(UTC)

    # Check agent exists
    agent_res = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_res.scalar_one_or_none()
    if not agent or agent.status != "ACTIVE":
        raise MemoryError("Agent not found or not active")

    # If actor is not owner, check agent permission grant has this memory scope
    if actor_role != "OWNER":
        grant_res = await session.execute(
            select(PermissionGrant).where(
                PermissionGrant.agent_id == agent_id,
                PermissionGrant.revoked_at.is_(None),
                (PermissionGrant.expires_at.is_(None)) | (PermissionGrant.expires_at > now),
            )
        )
        grants = grant_res.scalars().all()
        allowed_scopes = {s for g in grants for s in g.memory_scopes}
        if data.scope not in allowed_scopes:
            raise MemoryError(
                f"Agent lacks permission grant for memory scope '{data.scope}'",
                status_code=403,
            )

    # Find existing item
    query = select(AgentMemory).where(
        AgentMemory.agent_id == agent_id,
        AgentMemory.scope == data.scope,
        AgentMemory.key == data.key,
    )
    if data.scope_id:
        query = query.where(AgentMemory.scope_id == data.scope_id)
    else:
        query = query.where(AgentMemory.scope_id.is_(None))

    existing_res = await session.execute(query)
    existing = existing_res.scalar_one_or_none()

    if existing:
        existing.value = data.value
        existing.data_classification = data.data_classification
        existing.version += 1
        existing.updated_at = now
        memory = existing
    else:
        memory = AgentMemory(
            id=uuid.uuid4(),
            agent_id=agent_id,
            scope=data.scope,
            scope_id=data.scope_id,
            key=data.key,
            value=data.value,
            data_classification=data.data_classification,
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(memory)

    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="ACCESS",
            actor_id=actor_id,
            actor_role=actor_role,
            action="memory_stored",
            decision="ALLOW",
            reason=f"Memory key '{data.key}' in scope '{data.scope}' stored",
            target_id=memory.id,
            target_type="AGENT_MEMORY",
        ),
    )
    return memory


async def get_memory(
    session: AsyncSession,
    agent_id: uuid.UUID,
    scope: MemoryScope,
    key: str,
    scope_id: uuid.UUID | None = None,
) -> AgentMemory | None:
    """Fetch a scoped memory item."""
    query = select(AgentMemory).where(
        AgentMemory.agent_id == agent_id,
        AgentMemory.scope == scope,
        AgentMemory.key == key,
    )
    if scope_id:
        query = query.where(AgentMemory.scope_id == scope_id)
    else:
        query = query.where(AgentMemory.scope_id.is_(None))

    res = await session.execute(query)
    return res.scalar_one_or_none()


async def list_memories(
    session: AsyncSession,
    agent_id: uuid.UUID,
    scope: MemoryScope | None = None,
) -> list[AgentMemory]:
    """List memory items for an agent."""
    query = select(AgentMemory).where(AgentMemory.agent_id == agent_id)
    if scope:
        query = query.where(AgentMemory.scope == scope)
    res = await session.execute(query.order_by(AgentMemory.updated_at.desc()))
    return list(res.scalars().all())
