"""FastAPI router for tool definitions and secure execution gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import (
    AuthenticatedOwner,
    get_current_owner,
    get_db,
    verify_shutdown_state,
)
from domain.models.tools import ToolDefinition
from domain.schemas.tools import (
    ToolDefinitionCreate,
    ToolDefinitionResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
)
from services.tools.gateway import (
    ToolGatewayError,
    execute_tool,
    register_tool_definition,
)

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post(
    "/catalog",
    response_model=ToolDefinitionResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_register_tool(
    request: ToolDefinitionCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ToolDefinitionResponse:
    """Register a new tool in the catalog (Owner only)."""
    try:
        tool = await register_tool_definition(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return ToolDefinitionResponse.model_validate(tool)
    except ToolGatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/catalog",
    response_model=list[ToolDefinitionResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_tools(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ToolDefinitionResponse]:
    """List registered tools."""
    res = await session.execute(
        select(ToolDefinition).order_by(ToolDefinition.name.asc()).limit(limit)
    )
    return [ToolDefinitionResponse.model_validate(t) for t in res.scalars().all()]


@router.post(
    "/execute",
    response_model=ToolExecutionResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_execute_tool(
    request: ToolExecutionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ToolExecutionResponse:
    """Execute a sandboxed tool with policy checks and auditing."""
    try:
        execution = await execute_tool(
            session=session,
            request=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return ToolExecutionResponse.model_validate(execution)
    except ToolGatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
