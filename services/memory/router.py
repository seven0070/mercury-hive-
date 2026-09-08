"""FastAPI router for scoped agent memory storage and retrieval."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.tools import MemoryScope
from domain.schemas.tools import AgentMemoryResponse, AgentMemoryStore
from services.memory.service import (
    MemoryError,
    get_memory,
    list_memories,
    store_memory,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/{agent_id}", response_model=AgentMemoryResponse)
async def api_store_memory(
    agent_id: uuid.UUID,
    request: AgentMemoryStore,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentMemoryResponse:
    """Store or update scoped memory for an agent."""
    try:
        mem = await store_memory(
            session=session,
            agent_id=agent_id,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentMemoryResponse.model_validate(mem)
    except MemoryError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/{agent_id}", response_model=list[AgentMemoryResponse])
async def api_list_memories(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    scope: MemoryScope | None = None,
) -> list[AgentMemoryResponse]:
    """List memory items for an agent."""
    items = await list_memories(session=session, agent_id=agent_id, scope=scope)
    return [AgentMemoryResponse.model_validate(m) for m in items]


@router.get("/{agent_id}/{scope}/{key}", response_model=AgentMemoryResponse)
async def api_get_memory(
    agent_id: uuid.UUID,
    scope: MemoryScope,
    key: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    scope_id: uuid.UUID | None = None,
) -> AgentMemoryResponse:
    """Retrieve an individual scoped memory item."""
    mem = await get_memory(
        session=session,
        agent_id=agent_id,
        scope=scope,
        key=key,
        scope_id=scope_id,
    )
    if not mem:
        raise HTTPException(status_code=404, detail="Memory key not found")
    return AgentMemoryResponse.model_validate(mem)
