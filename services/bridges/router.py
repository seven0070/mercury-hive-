"""FastAPI router for cross-department bridges."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.tasks import BridgeStatus
from domain.schemas.tasks import BridgeCreate, BridgeDecisionRequest, BridgeResponse
from services.bridges.service import (
    BridgeError,
    approve_bridge,
    get_bridge,
    list_bridges,
    request_bridge,
    revoke_bridge,
)

router = APIRouter(prefix="/bridges", tags=["bridges"])


@router.post("", response_model=BridgeResponse)
async def api_request_bridge(
    request: BridgeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> BridgeResponse:
    """Request a cross-department bridge."""
    try:
        bridge = await request_bridge(
            session=session,
            data=request,
            requester_id=owner.owner_id,
            requester_role="OWNER",
        )
        return BridgeResponse.model_validate(bridge)
    except BridgeError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("", response_model=list[BridgeResponse])
async def api_list_bridges(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    department_id: uuid.UUID | None = None,
    status: BridgeStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[BridgeResponse]:
    """List cross-department bridges."""
    bridges = await list_bridges(
        session=session,
        department_id=department_id,
        status=status,
        limit=limit,
    )
    return [BridgeResponse.model_validate(b) for b in bridges]


@router.get("/{bridge_id}", response_model=BridgeResponse)
async def api_get_bridge(
    bridge_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> BridgeResponse:
    """Fetch bridge by ID."""
    bridge = await get_bridge(session, bridge_id)
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    return BridgeResponse.model_validate(bridge)


@router.post("/{bridge_id}/approve", response_model=BridgeResponse)
async def api_approve_bridge(
    bridge_id: uuid.UUID,
    request: BridgeDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> BridgeResponse:
    """Approve a proposed bridge."""
    try:
        bridge = await approve_bridge(
            session=session,
            bridge_id=bridge_id,
            approver_id=owner.owner_id,
            approver_role="OWNER",
            reason=request.reason,
        )
        return BridgeResponse.model_validate(bridge)
    except BridgeError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/{bridge_id}/revoke", response_model=BridgeResponse)
async def api_revoke_bridge(
    bridge_id: uuid.UUID,
    request: BridgeDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> BridgeResponse:
    """Revoke an active bridge."""
    try:
        bridge = await revoke_bridge(
            session=session,
            bridge_id=bridge_id,
            revoker_id=owner.owner_id,
            revoker_role="OWNER",
            reason=request.reason,
        )
        return BridgeResponse.model_validate(bridge)
    except BridgeError as e:
        raise HTTPException(status_code=400, detail=e.message) from e

