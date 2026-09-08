"""Controlled evolution engine: proposals, sandboxes, shadow deployment, and promotion."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.evolution import EvolutionStatus, SandboxVerdict
from domain.models.agents import Agent
from domain.models.evolution import EvolutionCandidate, SandboxRun
from domain.schemas.audit import AuditEventCreate
from domain.schemas.evolution import EvolutionCandidateCreate
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class EvolutionError(Exception):
    """Controlled evolution governance violations or invalid transitions."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def propose_candidate(
    session: AsyncSession,
    proposer_agent_id: uuid.UUID,
    data: EvolutionCandidateCreate,
) -> EvolutionCandidate:
    """Propose a system mutation candidate (prompt, tool, workflow, policy)."""
    # Verify proposer agent exists and is active
    agent_res = await session.execute(select(Agent).where(Agent.id == proposer_agent_id))
    agent = agent_res.scalar_one_or_none()
    if not agent or agent.status != "ACTIVE":
        raise EvolutionError("Proposer must be an active registered agent", status_code=403)

    candidate = EvolutionCandidate(
        id=uuid.uuid4(),
        title=data.title,
        evolution_type=data.evolution_type.value,
        target_identifier=data.target_identifier,
        proposed_change=data.proposed_change,
        status=EvolutionStatus.PROPOSED.value,
        proposer_agent_id=proposer_agent_id,
        shadow_traffic_percentage=0,
        created_at=datetime.now(UTC),
    )
    session.add(candidate)

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=proposer_agent_id,
            actor_role=agent.role,
            target_type="EVOLUTION_CANDIDATE",
            target_id=candidate.id,
            action="propose_candidate",
            decision="ALLOW",
            reason=f"Candidate proposed: {data.title} ({data.evolution_type.value})",
            payload={
                "target_identifier": data.target_identifier,
                "evolution_type": data.evolution_type.value,
            },
        ),
    )

    return candidate


async def run_sandbox_benchmark(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    test_suite_name: str,
    baseline_score: float,
    candidate_score: float,
    metrics: dict[str, Any] | None = None,
    runner_id: uuid.UUID | None = None,
) -> SandboxRun:
    """Execute an isolated sandbox test run comparing candidate against baseline."""
    cand_res = await session.execute(
        select(EvolutionCandidate).where(EvolutionCandidate.id == candidate_id)
    )
    candidate = cand_res.scalar_one_or_none()
    if not candidate:
        raise EvolutionError("Evolution candidate not found", status_code=404)

    if candidate.status not in [
        EvolutionStatus.PROPOSED.value,
        EvolutionStatus.SANDBOX_TESTING.value,
    ]:
        raise EvolutionError(
            f"Cannot run sandbox test on candidate in status {candidate.status}",
            status_code=400,
        )

    # Determine verdict
    if candidate_score < baseline_score:
        verdict = SandboxVerdict.REGRESSED
    elif candidate_score >= baseline_score and candidate_score >= 70.0:
        verdict = SandboxVerdict.PASSED
    else:
        verdict = SandboxVerdict.FAILED

    sandbox_run = SandboxRun(
        id=uuid.uuid4(),
        candidate_id=candidate.id,
        test_suite_name=test_suite_name,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        metrics=metrics,
        verdict=verdict.value,
        executed_at=datetime.now(UTC),
    )
    session.add(sandbox_run)

    candidate.status = EvolutionStatus.SANDBOX_TESTING.value
    candidate.benchmark_results = {
        "last_test_suite": test_suite_name,
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "verdict": verdict.value,
        "metrics": metrics or {},
    }

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=runner_id,
            actor_role="SYSTEM",
            target_type="SANDBOX_RUN",
            target_id=sandbox_run.id,
            action="run_sandbox_benchmark",
            decision="ALLOW",
            reason=f"Sandbox test {test_suite_name}: {verdict.value}",
            payload={
                "candidate_id": str(candidate.id),
                "baseline_score": baseline_score,
                "candidate_score": candidate_score,
                "verdict": verdict.value,
            },
        ),
    )

    return sandbox_run


async def deploy_shadow(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    percentage: int,
    actor_id: uuid.UUID | None = None,
    actor_role: str = "OWNER",
) -> EvolutionCandidate:
    """Route a bounded percentage of real traffic to candidate in shadow evaluation."""
    cand_res = await session.execute(
        select(EvolutionCandidate).where(EvolutionCandidate.id == candidate_id)
    )
    candidate = cand_res.scalar_one_or_none()
    if not candidate:
        raise EvolutionError("Evolution candidate not found", status_code=404)

    if candidate.status not in [
        EvolutionStatus.SANDBOX_TESTING.value,
        EvolutionStatus.SHADOW_DEPLOYED.value,
    ]:
        raise EvolutionError(
            "Candidate must be in SANDBOX_TESTING before shadow deploy, "
            f"current: {candidate.status}",
            status_code=400,
        )

    # Candidate must have at least one PASSED sandbox run
    runs_res = await session.execute(
        select(SandboxRun).where(
            SandboxRun.candidate_id == candidate.id,
            SandboxRun.verdict == SandboxVerdict.PASSED.value,
        )
    )
    passed_runs = runs_res.scalars().all()
    if not passed_runs:
        raise EvolutionError(
            "Candidate has not achieved any PASSED sandbox benchmarks",
            status_code=400,
        )

    candidate.status = EvolutionStatus.SHADOW_DEPLOYED.value
    candidate.shadow_traffic_percentage = percentage

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="EVOLUTION_CANDIDATE",
            target_id=candidate.id,
            action="deploy_shadow",
            decision="ALLOW",
            reason=f"Shadow traffic routed to {percentage}%",
            payload={"percentage": percentage},
        ),
    )

    return candidate


async def promote_to_production(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    owner_id: uuid.UUID,
    notes: str | None = None,
) -> EvolutionCandidate:
    """Promote an evolution candidate to production. Restricted exclusively to Owner."""
    cand_res = await session.execute(
        select(EvolutionCandidate).where(EvolutionCandidate.id == candidate_id)
    )
    candidate = cand_res.scalar_one_or_none()
    if not candidate:
        raise EvolutionError("Evolution candidate not found", status_code=404)

    if candidate.status not in [
        EvolutionStatus.SANDBOX_TESTING.value,
        EvolutionStatus.SHADOW_DEPLOYED.value,
        EvolutionStatus.APPROVED_FOR_PROMOTION.value,
    ]:
        raise EvolutionError(
            f"Cannot promote candidate from status {candidate.status}",
            status_code=400,
        )

    # Verification: must have passed at least one sandbox benchmark
    runs_res = await session.execute(
        select(SandboxRun).where(
            SandboxRun.candidate_id == candidate.id,
            SandboxRun.verdict == SandboxVerdict.PASSED.value,
        )
    )
    if not runs_res.scalars().all():
        raise EvolutionError(
            "Cannot promote candidate without a verified PASSED sandbox run",
            status_code=400,
        )

    now = datetime.now(UTC)
    candidate.status = EvolutionStatus.PROMOTED.value
    candidate.approved_by = owner_id
    candidate.promoted_at = now
    candidate.shadow_traffic_percentage = 100

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=owner_id,
            actor_role="OWNER",
            target_type="EVOLUTION_CANDIDATE",
            target_id=candidate.id,
            action="promote_to_production",
            decision="ALLOW",
            reason=f"Promoted to 100% production by Owner. Notes: {notes or 'N/A'}",
            payload={"target_identifier": candidate.target_identifier, "notes": notes},
        ),
    )

    return candidate


async def rollback_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    reason: str,
) -> EvolutionCandidate:
    """Instantly roll back a promoted or shadow-deployed candidate."""
    cand_res = await session.execute(
        select(EvolutionCandidate).where(EvolutionCandidate.id == candidate_id)
    )
    candidate = cand_res.scalar_one_or_none()
    if not candidate:
        raise EvolutionError("Evolution candidate not found", status_code=404)

    if candidate.status not in [
        EvolutionStatus.SHADOW_DEPLOYED.value,
        EvolutionStatus.PROMOTED.value,
        EvolutionStatus.SANDBOX_TESTING.value,
    ]:
        raise EvolutionError(
            f"Cannot rollback candidate in status {candidate.status}",
            status_code=400,
        )

    now = datetime.now(UTC)
    candidate.status = EvolutionStatus.ROLLED_BACK.value
    candidate.reverted_at = now
    candidate.reversion_reason = reason
    candidate.shadow_traffic_percentage = 0

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="SYSTEM",
            actor_id=actor_id,
            actor_role=actor_role,
            target_type="EVOLUTION_CANDIDATE",
            target_id=candidate.id,
            action="rollback_candidate",
            decision="ALLOW",
            reason=f"Evolution rolled back: {reason}",
            payload={"target_identifier": candidate.target_identifier, "reason": reason},
        ),
    )

    return candidate


async def get_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> EvolutionCandidate | None:
    """Retrieve an evolution candidate by ID."""
    res = await session.execute(
        select(EvolutionCandidate).where(EvolutionCandidate.id == candidate_id)
    )
    return res.scalar_one_or_none()


async def list_candidates(
    session: AsyncSession,
    status: str | None = None,
) -> list[EvolutionCandidate]:
    """List evolution candidates with optional status filter."""
    stmt = select(EvolutionCandidate).order_by(EvolutionCandidate.created_at.desc())
    if status:
        stmt = stmt.where(EvolutionCandidate.status == status)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_sandbox_runs(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> list[SandboxRun]:
    """List all sandbox benchmark runs for a candidate."""
    stmt = (
        select(SandboxRun)
        .where(SandboxRun.candidate_id == candidate_id)
        .order_by(SandboxRun.executed_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
