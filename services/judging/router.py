"""FastAPI router for Phase 6: Judging Council, Rubrics, and Evaluation Sessions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.schemas.judging import (
    JudgingSessionCreate,
    JudgingSessionResponse,
    RubricCreate,
    RubricResponse,
    ScorecardResponse,
    ScorecardSubmit,
    SubmissionCreate,
    SubmissionResponse,
)
from services.judging.service import (
    JudgingError,
    create_judging_session,
    create_rubric,
    get_judging_session,
    list_rubrics,
    submit_deliverable,
    submit_scorecard,
)

router = APIRouter(prefix="/judging", tags=["judging"])


@router.post("/rubrics", response_model=RubricResponse)
async def api_create_rubric(
    request: RubricCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> RubricResponse:
    """Create a standardized grading rubric."""
    try:
        rubric = await create_rubric(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return RubricResponse.model_validate(rubric)
    except JudgingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/rubrics", response_model=list[RubricResponse])
async def api_list_rubrics(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[RubricResponse]:
    """List all available grading rubrics."""
    rubrics = await list_rubrics(session)
    return [RubricResponse.model_validate(r) for r in rubrics]


@router.post("/submissions", response_model=SubmissionResponse)
async def api_submit_deliverable(
    request: SubmissionCreate,
    author_agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> SubmissionResponse:
    """Submit a task deliverable to the council for formal evaluation."""
    try:
        submission = await submit_deliverable(
            session=session,
            data=request,
            author_agent_id=author_agent_id,
        )
        return SubmissionResponse.model_validate(submission)
    except JudgingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/sessions", response_model=JudgingSessionResponse)
async def api_create_judging_session(
    request: JudgingSessionCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> JudgingSessionResponse:
    """Instantiate a multi-judge council session."""
    try:
        j_session = await create_judging_session(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return JudgingSessionResponse.model_validate(j_session)
    except JudgingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/sessions/{session_id}", response_model=JudgingSessionResponse)
async def api_get_judging_session(
    session_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> JudgingSessionResponse:
    """Fetch judging session status, aggregate score, and verdict."""
    j_session = await get_judging_session(session, session_id)
    if not j_session:
        raise HTTPException(status_code=404, detail="Judging session not found")
    return JudgingSessionResponse.model_validate(j_session)


@router.post("/sessions/{session_id}/score", response_model=ScorecardResponse)
async def api_submit_scorecard(
    session_id: uuid.UUID,
    judge_agent_id: uuid.UUID,
    request: ScorecardSubmit,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> ScorecardResponse:
    """Submit a scorecard for an active council deliberation."""
    try:
        scorecard, _ = await submit_scorecard(
            session=session,
            session_id=session_id,
            judge_agent_id=judge_agent_id,
            data=request,
        )
        return ScorecardResponse.model_validate(scorecard)
    except JudgingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
