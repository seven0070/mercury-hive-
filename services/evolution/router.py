"""FastAPI router for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import (
    AuthenticatedOwner,
    get_current_owner,
    get_db,
    verify_shutdown_state,
)
from domain.schemas.evolution import (
    EvolutionCandidateCreate,
    EvolutionCandidateResponse,
    PromotionRequest,
    RollbackRequest,
    SandboxRunCreate,
    SandboxRunResponse,
    ShadowDeployRequest,
)
from services.evolution.service import (
    EvolutionError,
    deploy_shadow,
    get_candidate,
    list_candidates,
    list_sandbox_runs,
    promote_to_production,
    propose_candidate,
    rollback_candidate,
    run_sandbox_benchmark,
)

router = APIRouter(prefix="/evolution", tags=["evolution"])


@router.post(
    "/candidates",
    response_model=EvolutionCandidateResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_propose_candidate(
    request: EvolutionCandidateCreate,
    proposer_agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EvolutionCandidateResponse:
    """Propose an evolution candidate (prompt, tool, workflow, or policy)."""
    try:
        candidate = await propose_candidate(
            session=session,
            proposer_agent_id=proposer_agent_id,
            data=request,
        )
        return EvolutionCandidateResponse.model_validate(candidate)
    except EvolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/candidates",
    response_model=list[EvolutionCandidateResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_candidates(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    status: Annotated[str | None, Query()] = None,
) -> list[EvolutionCandidateResponse]:
    """List evolution candidates with optional status filter."""
    candidates = await list_candidates(session=session, status=status)
    return [EvolutionCandidateResponse.model_validate(c) for c in candidates]


@router.get(
    "/candidates/{candidate_id}",
    response_model=EvolutionCandidateResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_get_candidate(
    candidate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EvolutionCandidateResponse:
    """Get evolution candidate by ID."""
    candidate = await get_candidate(session=session, candidate_id=candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Evolution candidate not found")
    return EvolutionCandidateResponse.model_validate(candidate)


@router.post(
    "/candidates/{candidate_id}/sandbox",
    response_model=SandboxRunResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_run_sandbox(
    candidate_id: uuid.UUID,
    request: SandboxRunCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> SandboxRunResponse:
    """Run an isolated sandbox benchmark test on a candidate."""
    try:
        sandbox_run = await run_sandbox_benchmark(
            session=session,
            candidate_id=candidate_id,
            test_suite_name=request.test_suite_name,
            baseline_score=request.baseline_score,
            candidate_score=request.candidate_score,
            metrics=request.metrics,
            runner_id=owner.owner_id,
        )
        return SandboxRunResponse.model_validate(sandbox_run)
    except EvolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/candidates/{candidate_id}/sandbox",
    response_model=list[SandboxRunResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_sandbox_runs(
    candidate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[SandboxRunResponse]:
    """List all sandbox benchmark runs for a candidate."""
    runs = await list_sandbox_runs(session=session, candidate_id=candidate_id)
    return [SandboxRunResponse.model_validate(r) for r in runs]


@router.post(
    "/candidates/{candidate_id}/shadow",
    response_model=EvolutionCandidateResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_deploy_shadow(
    candidate_id: uuid.UUID,
    request: ShadowDeployRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EvolutionCandidateResponse:
    """Deploy candidate to shadow traffic percentage."""
    try:
        candidate = await deploy_shadow(
            session=session,
            candidate_id=candidate_id,
            percentage=request.percentage,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return EvolutionCandidateResponse.model_validate(candidate)
    except EvolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/candidates/{candidate_id}/promote",
    response_model=EvolutionCandidateResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_promote_candidate(
    candidate_id: uuid.UUID,
    request: PromotionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EvolutionCandidateResponse:
    """Promote an evolution candidate to 100% production (Owner only)."""
    try:
        candidate = await promote_to_production(
            session=session,
            candidate_id=candidate_id,
            owner_id=owner.owner_id,
            notes=request.notes,
        )
        return EvolutionCandidateResponse.model_validate(candidate)
    except EvolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/candidates/{candidate_id}/rollback",
    response_model=EvolutionCandidateResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_rollback_candidate(
    candidate_id: uuid.UUID,
    request: RollbackRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> EvolutionCandidateResponse:
    """Roll back a promoted or shadow-deployed candidate immediately."""
    try:
        candidate = await rollback_candidate(
            session=session,
            candidate_id=candidate_id,
            actor_id=owner.owner_id,
            actor_role="OWNER",
            reason=request.reason,
        )
        return EvolutionCandidateResponse.model_validate(candidate)
    except EvolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
