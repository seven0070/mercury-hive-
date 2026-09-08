"""API router for Phase 3: Agents, Departments, and Scoped Permissions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.agent_status import AgentStatus, DepartmentStatus
from domain.enums.roles import SystemRole
from domain.schemas.agents import (
    AgentCreate,
    AgentResponse,
    AgentStatusChange,
    AgentUpdate,
    DepartmentCreate,
    DepartmentResponse,
    PermissionGrantCreate,
    PermissionGrantResponse,
)
from services.agent_registry.service import (
    AgentRegistryError,
    create_agent,
    get_agent,
    issue_permission_grant,
    list_agent_grants,
    list_agents,
    restore_agent,
    revoke_permission_grant,
    suspend_agent,
    terminate_agent,
    update_agent,
)
from services.departments.service import (
    DepartmentError,
    approve_department,
    get_department,
    list_departments,
    propose_department,
    suspend_department,
)

router = APIRouter(tags=["agents"])


# ============================================================
# Agent Endpoints
# ============================================================


@router.post("/agents", response_model=AgentResponse)
async def api_create_agent(
    request: AgentCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Register a new AI agent."""
    try:
        agent = await create_agent(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return AgentResponse.model_validate(agent)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("/agents", response_model=list[AgentResponse])
async def api_list_agents(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    department_id: uuid.UUID | None = None,
    role: SystemRole | None = None,
    status: AgentStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AgentResponse]:
    """List agents with optional filtering."""
    agents = await list_agents(
        session=session,
        department_id=department_id,
        role=role,
        status=status,
        limit=limit,
    )
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def api_get_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Fetch an agent by ID."""
    agent = await get_agent(session, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def api_update_agent(
    agent_id: uuid.UUID,
    request: AgentUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Update agent metadata."""
    try:
        agent = await update_agent(
            session=session,
            agent_id=agent_id,
            data=request,
            updater_id=owner.owner_id,
            updater_role="OWNER",
        )
        return AgentResponse.model_validate(agent)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/agents/{agent_id}/suspend", response_model=AgentResponse)
async def api_suspend_agent(
    agent_id: uuid.UUID,
    request: AgentStatusChange,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Suspend an agent and revoke all its active grants."""
    try:
        agent = await suspend_agent(
            session=session,
            agent_id=agent_id,
            reason=request.reason,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentResponse.model_validate(agent)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/agents/{agent_id}/terminate", response_model=AgentResponse)
async def api_terminate_agent(
    agent_id: uuid.UUID,
    request: AgentStatusChange,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Permanently terminate an agent."""
    try:
        agent = await terminate_agent(
            session=session,
            agent_id=agent_id,
            reason=request.reason,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentResponse.model_validate(agent)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/agents/{agent_id}/restore", response_model=AgentResponse)
async def api_restore_agent(
    agent_id: uuid.UUID,
    request: AgentStatusChange,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentResponse:
    """Restore a suspended agent back to active status."""
    try:
        agent = await restore_agent(
            session=session,
            agent_id=agent_id,
            reason=request.reason,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentResponse.model_validate(agent)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


# ============================================================
# Department Endpoints
# ============================================================


@router.get("/departments", response_model=list[DepartmentResponse])
async def api_list_departments(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    status: DepartmentStatus | None = None,
) -> list[DepartmentResponse]:
    """List departments."""
    departments = await list_departments(session, status=status)
    return [DepartmentResponse.model_validate(d) for d in departments]


@router.get("/departments/{department_id}", response_model=DepartmentResponse)
async def api_get_department(
    department_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> DepartmentResponse:
    """Fetch department by ID."""
    dept = await get_department(session, department_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return DepartmentResponse.model_validate(dept)


@router.post("/departments/proposals", response_model=DepartmentResponse)
async def api_propose_department(
    request: DepartmentCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> DepartmentResponse:
    """Propose a new department."""
    try:
        dept = await propose_department(
            session=session,
            data=request,
            proposer_id=owner.owner_id,
            proposer_role="OWNER",
        )
        return DepartmentResponse.model_validate(dept)
    except DepartmentError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/departments/{department_id}/approve", response_model=DepartmentResponse)
async def api_approve_department(
    department_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> DepartmentResponse:
    """Approve a proposed department (System Owner only)."""
    try:
        dept = await approve_department(
            session=session,
            department_id=department_id,
            approver_id=owner.owner_id,
            approver_role="OWNER",
        )
        return DepartmentResponse.model_validate(dept)
    except DepartmentError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/departments/{department_id}/suspend", response_model=DepartmentResponse)
async def api_suspend_department(
    department_id: uuid.UUID,
    request: AgentStatusChange,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> DepartmentResponse:
    """Suspend an active department (System Owner only)."""
    try:
        dept = await suspend_department(
            session=session,
            department_id=department_id,
            actor_id=owner.owner_id,
            actor_role="OWNER",
            reason=request.reason,
        )
        return DepartmentResponse.model_validate(dept)
    except DepartmentError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


# ============================================================
# Scoped Permission Grants
# ============================================================


@router.post("/permissions/grant", response_model=PermissionGrantResponse)
async def api_issue_permission_grant(
    request: PermissionGrantCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> PermissionGrantResponse:
    """Issue a scoped permission grant to an agent."""
    try:
        grant = await issue_permission_grant(
            session=session,
            data=request,
            issuer_id=owner.owner_id,
            issuer_role="OWNER",
        )
        return PermissionGrantResponse.model_validate(grant)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/permissions/{grant_id}/revoke", response_model=PermissionGrantResponse)
async def api_revoke_permission_grant(
    grant_id: uuid.UUID,
    request: AgentStatusChange,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> PermissionGrantResponse:
    """Revoke an active permission grant."""
    try:
        grant = await revoke_permission_grant(
            session=session,
            grant_id=grant_id,
            reason=request.reason,
            revoker_id=owner.owner_id,
            revoker_role="OWNER",
        )
        return PermissionGrantResponse.model_validate(grant)
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("/agents/{agent_id}/grants", response_model=list[PermissionGrantResponse])
async def api_list_agent_grants(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[PermissionGrantResponse]:
    """List all permission grants for an agent."""
    grants = await list_agent_grants(session, agent_id)
    return [PermissionGrantResponse.model_validate(g) for g in grants]

