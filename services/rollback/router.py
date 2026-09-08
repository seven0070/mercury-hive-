"""FastAPI router for rollback artifacts and repair actions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.tools import RollbackStatus
from domain.schemas.governance import ApprovalDecisionRequest
from domain.schemas.tools import RollbackResponse
from services.rollback.service import (
    RollbackError,
    execute_rollback,
    list_rollbacks,
)

router = APIRouter(prefix="/rollbacks", tags=["rollbacks"])


@router.get("", response_model=list[RollbackResponse])
async def api_list_rollbacks(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    task_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    status: RollbackStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[RollbackResponse]:
    """List rollback artifacts."""
    artifacts = await list_rollbacks(
        session=session,
        task_id=task_id,
        agent_id=agent_id,
        status=status,
        limit=limit,
    )
    return [RollbackResponse.model_validate(a) for a in artifacts]


@router.post("/{rollback_id}/execute", response_model=RollbackResponse)
async def api_execute_rollback(
    rollback_id: uuid.UUID,
    request: ApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> RollbackResponse:
    """Execute automated repair / state rollback."""
    try:
        artifact = await execute_rollback(
            session=session,
            rollback_id=rollback_id,
            actor_id=owner.owner_id,
            actor_role="OWNER",
            reason=request.reason,
        )
        return RollbackResponse.model_validate(artifact)
    except RollbackError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
