"""FastAPI router for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.schemas.tribe import (
    AgentSkillCreate,
    AgentSkillResponse,
    AgentSkillVerify,
    ExternalTaskIngestRequest,
    TaskSyncCreate,
    TaskSyncResponse,
    TribeMappingCreate,
    TribeMappingResponse,
)
from services.tribe.service import (
    TribeError,
    create_tribe_mapping,
    ingest_external_task,
    list_agent_skills,
    list_task_sync_mappings,
    list_tribe_mappings,
    register_agent_skill,
    sync_task_mapping,
    verify_agent_skill,
)

router = APIRouter(prefix="/tribe", tags=["tribe"])


@router.post("/mappings", response_model=TribeMappingResponse)
async def api_create_tribe_mapping(
    request: TribeMappingCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TribeMappingResponse:
    """Map a department to an external Tribe/Squad topology."""
    try:
        mapping = await create_tribe_mapping(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TribeMappingResponse.model_validate(mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/mappings", response_model=list[TribeMappingResponse])
async def api_list_tribe_mappings(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    department_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[TribeMappingResponse]:
    """List department-to-tribe mappings."""
    mappings = await list_tribe_mappings(session=session, department_id=department_id)
    return [TribeMappingResponse.model_validate(m) for m in mappings]


@router.post("/skills/{agent_id}", response_model=AgentSkillResponse)
async def api_register_agent_skill(
    agent_id: uuid.UUID,
    request: AgentSkillCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentSkillResponse:
    """Register or update an agent capability in the skill matrix."""
    try:
        skill = await register_agent_skill(
            session=session,
            agent_id=agent_id,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentSkillResponse.model_validate(skill)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/skills/{skill_id}/verify", response_model=AgentSkillResponse)
async def api_verify_agent_skill(
    skill_id: uuid.UUID,
    request: AgentSkillVerify,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentSkillResponse:
    """Certify and verify an agent skill."""
    try:
        skill = await verify_agent_skill(
            session=session,
            skill_id=skill_id,
            is_verified=request.is_verified,
            verifier_id=owner.owner_id,
            verifier_role="OWNER",
        )
        return AgentSkillResponse.model_validate(skill)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/skills/{agent_id}", response_model=list[AgentSkillResponse])
async def api_list_agent_skills(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[AgentSkillResponse]:
    """List all registered skills for an agent."""
    skills = await list_agent_skills(session=session, agent_id=agent_id)
    return [AgentSkillResponse.model_validate(s) for s in skills]


@router.post("/tasks/sync", response_model=TaskSyncResponse)
async def api_sync_task_mapping(
    request: TaskSyncCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskSyncResponse:
    """Link an internal task to an external tracker issue/ticket."""
    try:
        mapping = await sync_task_mapping(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TaskSyncResponse.model_validate(mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/tasks/ingest", response_model=TaskSyncResponse)
async def api_ingest_external_task(
    request: ExternalTaskIngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskSyncResponse:
    """Ingest an external issue as a governed task in Mercury Hive."""
    try:
        _task, sync_mapping = await ingest_external_task(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TaskSyncResponse.model_validate(sync_mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/tasks/sync", response_model=list[TaskSyncResponse])
async def api_list_task_sync(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    task_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[TaskSyncResponse]:
    """List task synchronization mappings."""
    mappings = await list_task_sync_mappings(session=session, task_id=task_id)
    return [TaskSyncResponse.model_validate(m) for m in mappings]
