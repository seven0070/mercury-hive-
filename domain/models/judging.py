"""SQLAlchemy models for Phase 6: Judging Council, Rubrics, and Evaluations."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class Rubric(Base):
    """Standardized grading rubric with criteria and passing thresholds."""

    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'1.0.0'"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    criteria: Mapped[dict | list] = mapped_column(
        JSONB,
        nullable=False,
    )
    minimum_passing_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        server_default=text("80.0"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("name", "version", name="uq_rubrics_name_version"),)


class EvaluationSubmission(Base):
    """Submission of task deliverables for formal council evaluation."""

    __tablename__ = "evaluation_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    deliverable_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )


class JudgingSession(Base):
    """Multi-judge council evaluation session."""

    __tablename__ = "judging_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rubrics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'PENDING_REVIEW'"),
        nullable=False,
    )
    required_judges: Mapped[int] = mapped_column(
        Integer,
        server_default=text("3"),
        nullable=False,
    )
    final_verdict: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    aggregate_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    consensus_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_REVIEW', 'IN_DELIBERATION', "
            "'CONSENSUS_REACHED', 'ESCALATED_TO_OWNER', 'CLOSED')",
            name="ck_judging_sessions_valid_status",
        ),
        CheckConstraint(
            "final_verdict IS NULL OR final_verdict IN "
            "('PASSED', 'FAILED', 'NEEDS_REVISION', 'DISQUALIFIED')",
            name="ck_judging_sessions_valid_verdict",
        ),
    )


class JudgeScorecard(Base):
    """Independent grading assessment by a single council judge."""

    __tablename__ = "judge_scorecards"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judging_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    judge_agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scores: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    total_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    verdict: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    feedback: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    conflict_declared: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )
    conflict_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('PASSED', 'FAILED', 'NEEDS_REVISION', 'DISQUALIFIED')",
            name="ck_judge_scorecards_valid_verdict",
        ),
        UniqueConstraint("session_id", "judge_agent_id", name="uq_scorecard_session_judge"),
    )
