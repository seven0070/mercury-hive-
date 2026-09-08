"""FastAPI router for tasks and mission execution."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.enums.tasks import TaskPriority, TaskStatus
from domain.schemas.tasks import (
    TaskCreate,
    TaskDelegationCreate,
    TaskDelegationResponse,
    TaskResponse,
    TaskStatusTransition,
)
from services.tasks.service import (
    TaskError,
    assign_task,
    create_task,
    delegate_task,
    get_task,
    list_tasks,
    transition_task_status,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def api_create_task(
    request: TaskCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskResponse:
    """Create a new governed task or mission."""
    try:
        task = await create_task(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return TaskResponse.model_validate(task)
    except TaskError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.get("", response_model=list[TaskResponse])
async def api_list_tasks(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    department_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TaskResponse]:
    """List tasks with filtering."""
    tasks = await list_tasks(
        session=session,
        department_id=department_id,
        agent_id=agent_id,
        status=status,
        priority=priority,
        limit=limit,
    )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def api_get_task(
    task_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskResponse:
    """Fetch task by ID."""
    task = await get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def api_assign_task(
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskResponse:
    """Assign an agent to a task."""
    try:
        task = await assign_task(
            session=session,
            task_id=task_id,
            agent_id=agent_id,
            assigner_id=owner.owner_id,
            assigner_role="OWNER",
        )
        return TaskResponse.model_validate(task)
    except TaskError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/{task_id}/transition", response_model=TaskResponse)
async def api_transition_task(
    task_id: uuid.UUID,
    request: TaskStatusTransition,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskResponse:
    """Perform a validated status transition on a task."""
    try:
        task = await transition_task_status(
            session=session,
            task_id=task_id,
            transition=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TaskResponse.model_validate(task)
    except TaskError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/delegate", response_model=TaskDelegationResponse)
async def api_delegate_task(
    request: TaskDelegationCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskDelegationResponse:
    """Delegate a task across an active department bridge."""
    try:
        delegation = await delegate_task(
            session=session,
            data=request,
            delegator_id=owner.owner_id,
            delegator_role="OWNER",
        )
        return TaskDelegationResponse.model_validate(delegation)
    except TaskError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
