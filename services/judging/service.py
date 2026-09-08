"""Judging council service: rubrics, conflict of interest checks, and consensus deliberation."""

import statistics
import uuid
from collections import Counter
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.judging import CouncilStatus
from domain.models.agents import Agent
from domain.models.judging import (
    EvaluationSubmission,
    JudgeScorecard,
    JudgingSession,
    Rubric,
)
from domain.models.tasks import Task
from domain.schemas.audit import AuditEventCreate
from domain.schemas.judging import (
    JudgingSessionCreate,
    RubricCreate,
    ScorecardSubmit,
    SubmissionCreate,
)
from services.audit.service import log_audit_event

logger = structlog.get_logger()


class JudgingError(Exception):
    """Business logic or ethics violations in judging."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def create_rubric(
    session: AsyncSession,
    data: RubricCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> Rubric:
    """Create a new standardized grading rubric."""
    if creator_role not in ["OWNER", "CEO", "DEPARTMENT_MANAGER"]:
        raise JudgingError("Only Owner, CEO, or Managers can create rubrics", status_code=403)

    rubric = Rubric(
        id=uuid.uuid4(),
        name=data.name,
        version=data.version,
        description=data.description,
        criteria=data.criteria,
        minimum_passing_score=data.minimum_passing_score,
        is_active=data.is_active,
        created_at=datetime.now(UTC),
    )
    session.add(rubric)
    await session.flush()
    return rubric


async def list_rubrics(session: AsyncSession) -> list[Rubric]:
    """List active rubrics."""
    res = await session.execute(select(Rubric).order_by(Rubric.name.asc()))
    return list(res.scalars().all())


async def submit_deliverable(
    session: AsyncSession,
    data: SubmissionCreate,
    author_agent_id: uuid.UUID,
) -> EvaluationSubmission:
    """Submit a task deliverable for council evaluation."""
    task_res = await session.execute(select(Task).where(Task.id == data.task_id))
    task = task_res.scalar_one_or_none()
    if not task:
        raise JudgingError("Task not found")

    sub = EvaluationSubmission(
        id=uuid.uuid4(),
        task_id=data.task_id,
        author_agent_id=author_agent_id,
        title=data.title,
        deliverable_payload=data.deliverable_payload,
        submitted_at=datetime.now(UTC),
    )
    session.add(sub)
    await session.flush()
    return sub


async def create_judging_session(
    session: AsyncSession,
    data: JudgingSessionCreate,
    creator_id: uuid.UUID,
    creator_role: str,
) -> JudgingSession:
    """Instantiate a multi-judge council session."""
    sub_res = await session.execute(
        select(EvaluationSubmission).where(EvaluationSubmission.id == data.submission_id)
    )
    if not sub_res.scalar_one_or_none():
        raise JudgingError("Submission not found")

    rubric_res = await session.execute(select(Rubric).where(Rubric.id == data.rubric_id))
    if not rubric_res.scalar_one_or_none():
        raise JudgingError("Rubric not found")

    judging_session = JudgingSession(
        id=uuid.uuid4(),
        submission_id=data.submission_id,
        rubric_id=data.rubric_id,
        status=CouncilStatus.PENDING_REVIEW,
        required_judges=data.required_judges,
        created_at=datetime.now(UTC),
    )
    session.add(judging_session)
    await session.flush()

    await log_audit_event(
        session,
        AuditEventCreate(
            event_type="GOVERNANCE",
            actor_id=creator_id,
            actor_role=creator_role,
            action="judging_session_created",
            decision="ALLOW",
            reason=f"Council judging session created with {data.required_judges} required judges",
            target_id=judging_session.id,
            target_type="JUDGING_SESSION",
        ),
    )
    return judging_session


async def submit_scorecard(
    session: AsyncSession,
    session_id: uuid.UUID,
    judge_agent_id: uuid.UUID,
    data: ScorecardSubmit,
) -> tuple[JudgeScorecard, JudgingSession]:
    """Submit a scorecard with conflict-of-interest checks and council consensus."""
    # 1. Fetch judging session and submission
    s_res = await session.execute(
        select(JudgingSession).where(JudgingSession.id == session_id).with_for_update()
    )
    judging_session = s_res.scalar_one_or_none()
    if not judging_session:
        raise JudgingError("Judging session not found", status_code=404)

    if judging_session.status in [CouncilStatus.CONSENSUS_REACHED, CouncilStatus.CLOSED]:
        raise JudgingError("Judging session is already closed")

    sub_res = await session.execute(
        select(EvaluationSubmission).where(EvaluationSubmission.id == judging_session.submission_id)
    )
    submission = sub_res.scalar_one()

    # 2. Conflict of Interest Checks
    # Check 2a: Author cannot judge own submission
    if judge_agent_id == submission.author_agent_id:
        raise JudgingError(
            "Conflict of Interest: Author cannot serve as judge on their own deliverable",
            status_code=403,
        )

    # Check 2b: Judge must exist and be active
    j_res = await session.execute(select(Agent).where(Agent.id == judge_agent_id))
    judge = j_res.scalar_one_or_none()
    if not judge or judge.status != "ACTIVE":
        raise JudgingError("Judge agent not found or not active")

    # Check 2c: Author agent department vs judge department
    author_res = await session.execute(select(Agent).where(Agent.id == submission.author_agent_id))
    author = author_res.scalar_one_or_none()
    if author and author.department_id and judge.department_id == author.department_id:
        raise JudgingError(
            "Conflict of Interest: Judge belongs to the same department as the author",
            status_code=403,
        )

    # 3. Check for duplicate scorecard
    dup_res = await session.execute(
        select(JudgeScorecard).where(
            JudgeScorecard.session_id == session_id,
            JudgeScorecard.judge_agent_id == judge_agent_id,
        )
    )
    if dup_res.scalar_one_or_none():
        raise JudgingError("Judge has already submitted a scorecard for this session")

    # 4. Insert scorecard
    scorecard = JudgeScorecard(
        id=uuid.uuid4(),
        session_id=session_id,
        judge_agent_id=judge_agent_id,
        scores=data.scores,
        total_score=data.total_score,
        verdict=data.verdict,
        feedback=data.feedback,
        conflict_declared=data.conflict_declared,
        conflict_reason=data.conflict_reason,
        submitted_at=datetime.now(UTC),
    )
    session.add(scorecard)
    await session.flush()

    # 5. Check Council Consensus
    cards_res = await session.execute(
        select(JudgeScorecard).where(
            JudgeScorecard.session_id == session_id,
            JudgeScorecard.conflict_declared.is_(False),
        )
    )
    valid_cards = cards_res.scalars().all()

    if len(valid_cards) >= judging_session.required_judges:
        # Deliberation complete -> calculate consensus
        scores = [float(c.total_score) for c in valid_cards]
        avg_score = round(statistics.mean(scores), 2)
        variance = max(scores) - min(scores)

        verdict_counts = Counter(c.verdict for c in valid_cards)
        majority_verdict, count = verdict_counts.most_common(1)[0]

        judging_session.aggregate_score = avg_score

        # Check for high variance (>25 points difference triggers escalation)
        if variance > 25.0:
            judging_session.status = CouncilStatus.ESCALATED_TO_OWNER
            judging_session.consensus_notes = (
                f"Escalated due to high score variance ({variance:.1f} pts) across judges. "
                f"Scores: {scores}. Breakdown: {dict(verdict_counts)}"
            )
        else:
            judging_session.status = CouncilStatus.CONSENSUS_REACHED
            judging_session.final_verdict = majority_verdict
            judging_session.closed_at = datetime.now(UTC)
            judging_session.consensus_notes = (
                f"Consensus reached by majority ({count}/{len(valid_cards)}). "
                f"Mean score: {avg_score:.1f} pts."
            )

        await log_audit_event(
            session,
            AuditEventCreate(
                event_type="GOVERNANCE",
                actor_id=judge_agent_id,
                actor_role="JUDGE",
                action="judging_consensus_evaluated",
                decision="ALLOW",
                reason=judging_session.consensus_notes,
                target_id=judging_session.id,
                target_type="JUDGING_SESSION",
                payload={
                    "status": judging_session.status,
                    "final_verdict": judging_session.final_verdict,
                    "aggregate_score": float(avg_score),
                },
            ),
        )
    else:
        judging_session.status = CouncilStatus.IN_DELIBERATION

    return scorecard, judging_session


async def get_judging_session(
    session: AsyncSession,
    session_id: uuid.UUID,
) -> JudgingSession | None:
    """Fetch a judging session by ID."""
    res = await session.execute(select(JudgingSession).where(JudgingSession.id == session_id))
    return res.scalar_one_or_none()
