"""Unit tests for Phase 6: Judging Council, Rubrics, and Conflict Checks."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.enums.agent_status import AgentStatus
from domain.enums.judging import CouncilStatus, EvaluationVerdict
from domain.enums.roles import SystemRole
from domain.models.agents import Agent
from domain.models.judging import (
    EvaluationSubmission,
    JudgeScorecard,
    JudgingSession,
)
from domain.schemas.judging import (
    ScorecardSubmit,
)
from services.judging.service import (
    JudgingError,
    submit_scorecard,
)


@pytest.mark.asyncio
async def test_conflict_author_cannot_judge_own_work():
    """Author of a deliverable cannot submit a scorecard for their own deliverable."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    author_id = uuid.uuid4()
    session_id = uuid.uuid4()

    submission = EvaluationSubmission(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        author_agent_id=author_id,
        title="Deliverable Alpha",
        deliverable_payload={"code": "print('hello')"},
        submitted_at=datetime.now(UTC),
    )

    judging_session = JudgingSession(
        id=session_id,
        submission_id=submission.id,
        rubric_id=uuid.uuid4(),
        status=CouncilStatus.PENDING_REVIEW,
        required_judges=3,
        created_at=datetime.now(UTC),
    )

    r_session = MagicMock()
    r_session.scalar_one_or_none.return_value = judging_session
    r_sub = MagicMock()
    r_sub.scalar_one.return_value = submission

    mock_session.execute.side_effect = [r_session, r_sub]

    scorecard_data = ScorecardSubmit(
        scores={"CORRECTNESS": 90.0},
        total_score=90.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Looks good to me!",
    )

    with pytest.raises(JudgingError, match="Author cannot serve as judge on their own deliverable"):
        await submit_scorecard(
            session=mock_session,
            session_id=session_id,
            judge_agent_id=author_id,  # SAME as author!
            data=scorecard_data,
        )


@pytest.mark.asyncio
async def test_conflict_same_department_judge_blocked():
    """Judge belonging to the same department as the author is blocked."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    dept_id = uuid.uuid4()
    author_id = uuid.uuid4()
    judge_id = uuid.uuid4()
    session_id = uuid.uuid4()

    submission = EvaluationSubmission(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        author_agent_id=author_id,
        title="Deliverable Beta",
        deliverable_payload={"code": "sample"},
        submitted_at=datetime.now(UTC),
    )

    judging_session = JudgingSession(
        id=session_id,
        submission_id=submission.id,
        rubric_id=uuid.uuid4(),
        status=CouncilStatus.PENDING_REVIEW,
        required_judges=3,
        created_at=datetime.now(UTC),
    )

    judge = Agent(
        id=judge_id,
        display_name="Biased Judge",
        role=SystemRole.JUDGE,
        department_id=dept_id,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    author = Agent(
        id=author_id,
        display_name="Teammate Author",
        role=SystemRole.WORKER,
        department_id=dept_id,  # Same department!
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    r_session = MagicMock()
    r_session.scalar_one_or_none.return_value = judging_session
    r_sub = MagicMock()
    r_sub.scalar_one.return_value = submission
    r_judge = MagicMock()
    r_judge.scalar_one_or_none.return_value = judge
    r_author = MagicMock()
    r_author.scalar_one_or_none.return_value = author

    mock_session.execute.side_effect = [r_session, r_sub, r_judge, r_author]

    scorecard_data = ScorecardSubmit(
        scores={"CORRECTNESS": 95.0},
        total_score=95.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Colleague did great work",
    )

    with pytest.raises(JudgingError, match="Judge belongs to the same department as the author"):
        await submit_scorecard(
            session=mock_session,
            session_id=session_id,
            judge_agent_id=judge_id,
            data=scorecard_data,
        )


@pytest.mark.asyncio
async def test_council_consensus_evaluation():
    """Council reaches consensus when required judges submit scores."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    author_dept = uuid.uuid4()
    judging_dept = uuid.uuid4()

    author_id = uuid.uuid4()
    judge1_id = uuid.uuid4()
    session_id = uuid.uuid4()

    submission = EvaluationSubmission(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        author_agent_id=author_id,
        title="Production Deployment Release",
        deliverable_payload={"artifacts": ["v1.0.tar.gz"]},
        submitted_at=datetime.now(UTC),
    )

    judging_session = JudgingSession(
        id=session_id,
        submission_id=submission.id,
        rubric_id=uuid.uuid4(),
        status=CouncilStatus.PENDING_REVIEW,
        required_judges=2,  # Require 2 judges for consensus
        created_at=datetime.now(UTC),
    )

    judge1 = Agent(
        id=judge1_id,
        display_name="Council Judge 01",
        role=SystemRole.JUDGE,
        department_id=judging_dept,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    author = Agent(
        id=author_id,
        display_name="Worker Lead",
        role=SystemRole.WORKER,
        department_id=author_dept,
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    card1 = JudgeScorecard(
        id=uuid.uuid4(),
        session_id=session_id,
        judge_agent_id=uuid.uuid4(),
        scores={"QUALITY": 85.0},
        total_score=85.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Solid delivery",
        conflict_declared=False,
        submitted_at=datetime.now(UTC),
    )
    card2 = JudgeScorecard(
        id=uuid.uuid4(),
        session_id=session_id,
        judge_agent_id=judge1_id,
        scores={"QUALITY": 90.0},
        total_score=90.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Excellent tests",
        conflict_declared=False,
        submitted_at=datetime.now(UTC),
    )

    r_session = MagicMock()
    r_session.scalar_one_or_none.return_value = judging_session
    r_sub = MagicMock()
    r_sub.scalar_one.return_value = submission
    r_judge = MagicMock()
    r_judge.scalar_one_or_none.return_value = judge1
    r_author = MagicMock()
    r_author.scalar_one_or_none.return_value = author
    r_dup = MagicMock()
    r_dup.scalar_one_or_none.return_value = None  # Not duplicate
    r_cards = MagicMock()
    r_cards.scalars.return_value.all.return_value = [card1, card2]  # Now 2 cards!

    mock_session.execute.side_effect = [
        r_session,
        r_sub,
        r_judge,
        r_author,
        r_dup,
        r_cards,
        MagicMock(),
    ]

    scorecard_data = ScorecardSubmit(
        scores={"QUALITY": 90.0},
        total_score=90.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Excellent tests",
    )

    _, updated_session = await submit_scorecard(
        session=mock_session,
        session_id=session_id,
        judge_agent_id=judge1_id,
        data=scorecard_data,
    )

    assert updated_session.status == CouncilStatus.CONSENSUS_REACHED
    assert updated_session.final_verdict == EvaluationVerdict.PASSED
    assert updated_session.aggregate_score == 87.5  # Mean of 85.0 and 90.0
    assert updated_session.closed_at is not None


@pytest.mark.asyncio
async def test_high_variance_triggers_owner_escalation():
    """Score variance > 25 points escalates session to owner review."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    author_id = uuid.uuid4()
    judge2_id = uuid.uuid4()
    session_id = uuid.uuid4()

    submission = EvaluationSubmission(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        author_agent_id=author_id,
        title="Disputed Architecture Proposal",
        deliverable_payload={},
        submitted_at=datetime.now(UTC),
    )

    judging_session = JudgingSession(
        id=session_id,
        submission_id=submission.id,
        rubric_id=uuid.uuid4(),
        status=CouncilStatus.PENDING_REVIEW,
        required_judges=2,
        created_at=datetime.now(UTC),
    )

    judge2 = Agent(
        id=judge2_id,
        display_name="Critical Judge",
        role=SystemRole.JUDGE,
        department_id=uuid.uuid4(),
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    author = Agent(
        id=author_id,
        display_name="Worker",
        role=SystemRole.WORKER,
        department_id=uuid.uuid4(),
        status=AgentStatus.ACTIVE,
        system_prompt_version="1.0.0",
        created_at=datetime.now(UTC),
    )

    card1 = JudgeScorecard(
        id=uuid.uuid4(),
        session_id=session_id,
        judge_agent_id=uuid.uuid4(),
        scores={"QUALITY": 95.0},
        total_score=95.0,
        verdict=EvaluationVerdict.PASSED,
        feedback="Flawless",
        conflict_declared=False,
        submitted_at=datetime.now(UTC),
    )
    card2 = JudgeScorecard(
        id=uuid.uuid4(),
        session_id=session_id,
        judge_agent_id=judge2_id,
        scores={"QUALITY": 50.0},
        total_score=50.0,
        verdict=EvaluationVerdict.FAILED,
        feedback="Severe vulnerabilities",
        conflict_declared=False,
        submitted_at=datetime.now(UTC),
    )

    r_session = MagicMock()
    r_session.scalar_one_or_none.return_value = judging_session
    r_sub = MagicMock()
    r_sub.scalar_one.return_value = submission
    r_judge = MagicMock()
    r_judge.scalar_one_or_none.return_value = judge2
    r_author = MagicMock()
    r_author.scalar_one_or_none.return_value = author
    r_dup = MagicMock()
    r_dup.scalar_one_or_none.return_value = None
    r_cards = MagicMock()
    r_cards.scalars.return_value.all.return_value = [card1, card2]  # Difference: 45 pts!

    mock_session.execute.side_effect = [
        r_session,
        r_sub,
        r_judge,
        r_author,
        r_dup,
        r_cards,
        MagicMock(),
    ]

    scorecard_data = ScorecardSubmit(
        scores={"QUALITY": 50.0},
        total_score=50.0,
        verdict=EvaluationVerdict.FAILED,
        feedback="Severe vulnerabilities",
    )

    _, updated_session = await submit_scorecard(
        session=mock_session,
        session_id=session_id,
        judge_agent_id=judge2_id,
        data=scorecard_data,
    )

    assert updated_session.status == CouncilStatus.ESCALATED_TO_OWNER
    assert "Escalated due to high score variance" in updated_session.consensus_notes
