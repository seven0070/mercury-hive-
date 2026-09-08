"""Phase 6: judging council, rubrics, and independent evaluation.

Revision ID: 006_phase6
Revises: 005_phase5
Create Date: 2026-09-08

Forward-only migration. Creates:
- rubrics table + seeds default engineering & governance rubrics
- evaluation_submissions table (deliverable handoffs)
- judging_sessions table (multi-judge council deliberation)
- judge_scorecards table (individual scoring assessments)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "006_phase6"
down_revision: str | None = "005_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_RUBRICS = [
    (
        "Standard Engineering Deliverable Rubric",
        "1.0.0",
        "Evaluates code correctness, unit test coverage, and documentation integrity.",
        [
            {"category": "CORRECTNESS", "weight": 0.4, "min_score": 80.0},
            {"category": "TEST_COVERAGE", "weight": 0.3, "min_score": 80.0},
            {"category": "CODE_QUALITY", "weight": 0.3, "min_score": 75.0},
        ],
        80.0,
    ),
    (
        "Security & Governance Audit Rubric",
        "1.0.0",
        "Evaluates tamper-proof audit trails, least-privilege scoping, and data protection.",
        [
            {"category": "SECURITY_POSTURE", "weight": 0.5, "min_score": 90.0},
            {"category": "GOVERNANCE_COMPLIANCE", "weight": 0.3, "min_score": 85.0},
            {"category": "REVERSIBILITY", "weight": 0.2, "min_score": 80.0},
        ],
        85.0,
    ),
]


def upgrade() -> None:
    # === rubrics ===
    op.create_table(
        "rubrics",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(32), server_default=sa.text("'1.0.0'"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("criteria", JSONB(), nullable=False),
        sa.Column(
            "minimum_passing_score",
            sa.Numeric(5, 2),
            server_default=sa.text("80.0"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_rubrics_name_version")),
    )

    # Seed initial rubrics
    rubrics_table = sa.table(
        "rubrics",
        sa.column("name", sa.String),
        sa.column("version", sa.String),
        sa.column("description", sa.Text),
        sa.column("criteria", JSONB),
        sa.column("minimum_passing_score", sa.Numeric),
    )
    op.bulk_insert(
        rubrics_table,
        [
            {
                "name": name,
                "version": ver,
                "description": desc,
                "criteria": crit,
                "minimum_passing_score": min_s,
            }
            for name, ver, desc, crit, min_s in INITIAL_RUBRICS
        ],
    )

    # === evaluation_submissions ===
    op.create_table(
        "evaluation_submissions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("author_agent_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("deliverable_payload", JSONB(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_submissions")),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_evaluation_submissions_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_agent_id"],
            ["agents.id"],
            name=op.f("fk_evaluation_submissions_author_agent_id_agents"),
            ondelete="RESTRICT",
        ),
    )

    # === judging_sessions ===
    op.create_table(
        "judging_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default=sa.text("'PENDING_REVIEW'"),
            nullable=False,
        ),
        sa.Column(
            "required_judges",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("final_verdict", sa.String(32), nullable=True),
        sa.Column("aggregate_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("consensus_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judging_sessions")),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["evaluation_submissions.id"],
            name=op.f("fk_judging_sessions_submission_id_evaluation_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_judging_sessions_rubric_id_rubrics"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW', 'IN_DELIBERATION', "
            "'CONSENSUS_REACHED', 'ESCALATED_TO_OWNER', 'CLOSED')",
            name=op.f("ck_judging_sessions_valid_status"),
        ),
        sa.CheckConstraint(
            "final_verdict IS NULL OR final_verdict IN "
            "('PASSED', 'FAILED', 'NEEDS_REVISION', 'DISQUALIFIED')",
            name=op.f("ck_judging_sessions_valid_verdict"),
        ),
    )

    # === judge_scorecards ===
    op.create_table(
        "judge_scorecards",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("judge_agent_id", sa.Uuid(), nullable=False),
        sa.Column("scores", JSONB(), nullable=False),
        sa.Column("total_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column(
            "conflict_declared",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judge_scorecards")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["judging_sessions.id"],
            name=op.f("fk_judge_scorecards_session_id_judging_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["judge_agent_id"],
            ["agents.id"],
            name=op.f("fk_judge_scorecards_judge_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "verdict IN ('PASSED', 'FAILED', 'NEEDS_REVISION', 'DISQUALIFIED')",
            name=op.f("ck_judge_scorecards_valid_verdict"),
        ),
        sa.UniqueConstraint(
            "session_id",
            "judge_agent_id",
            name=op.f("uq_scorecard_session_judge"),
        ),
    )


def downgrade() -> None:
    op.drop_table("judge_scorecards")
    op.drop_table("judging_sessions")
    op.drop_table("evaluation_submissions")
    op.drop_table("rubrics")
