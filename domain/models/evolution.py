"""SQLAlchemy models for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class EvolutionCandidate(Base):
    """Governed proposal for system evolution (prompts, tools, or policies)."""

    __tablename__ = "evolution_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    evolution_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    target_identifier: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    proposed_change: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'PROPOSED'"),
        nullable=False,
    )
    proposer_agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    benchmark_results: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    shadow_traffic_percentage: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reversion_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "evolution_type IN ('SYSTEM_PROMPT', 'TOOL_DEFINITION', "
            "'WORKFLOW_PIPELINE', 'POLICY_RULE')",
            name="ck_evolution_valid_type",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'SANDBOX_TESTING', 'SHADOW_DEPLOYED', "
            "'APPROVED_FOR_PROMOTION', 'PROMOTED', 'REJECTED', 'ROLLED_BACK')",
            name="ck_evolution_valid_status",
        ),
        CheckConstraint(
            "shadow_traffic_percentage >= 0 AND shadow_traffic_percentage <= 100",
            name="ck_evolution_valid_shadow_pct",
        ),
    )


class SandboxRun(Base):
    """Isolated benchmarking run comparing candidate against production baseline."""

    __tablename__ = "sandbox_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evolution_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    test_suite_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    baseline_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    candidate_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    metrics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    verdict: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('PASSED', 'REGRESSED', 'FAILED')",
            name="ck_sandbox_runs_valid_verdict",
        ),
    )
