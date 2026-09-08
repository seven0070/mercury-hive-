"""Phase 7: controlled evolution engine, sandboxes, and shadow deployments.

Revision ID: 007_phase7
Revises: 006_phase6
Create Date: 2026-09-08

Forward-only migration. Creates:
- evolution_candidates table (governed mutation proposals)
- sandbox_runs table (isolated benchmarking against production baselines)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007_phase7"
down_revision: str | None = "006_phase6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === evolution_candidates ===
    op.create_table(
        "evolution_candidates",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("evolution_type", sa.String(32), nullable=False),
        sa.Column("target_identifier", sa.String(128), nullable=False),
        sa.Column("proposed_change", JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default=sa.text("'PROPOSED'"),
            nullable=False,
        ),
        sa.Column("proposer_agent_id", sa.Uuid(), nullable=False),
        sa.Column("benchmark_results", JSONB(), nullable=True),
        sa.Column(
            "shadow_traffic_percentage",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversion_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evolution_candidates")),
        sa.ForeignKeyConstraint(
            ["proposer_agent_id"],
            ["agents.id"],
            name=op.f("fk_evolution_candidates_proposer_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["owners.id"],
            name=op.f("fk_evolution_candidates_approved_by_owners"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "evolution_type IN ('SYSTEM_PROMPT', 'TOOL_DEFINITION', "
            "'WORKFLOW_PIPELINE', 'POLICY_RULE')",
            name=op.f("ck_evolution_valid_type"),
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'SANDBOX_TESTING', 'SHADOW_DEPLOYED', "
            "'APPROVED_FOR_PROMOTION', 'PROMOTED', 'REJECTED', 'ROLLED_BACK')",
            name=op.f("ck_evolution_valid_status"),
        ),
        sa.CheckConstraint(
            "shadow_traffic_percentage >= 0 AND shadow_traffic_percentage <= 100",
            name=op.f("ck_evolution_valid_shadow_pct"),
        ),
    )
    op.create_index(
        "ix_evolution_candidates_status",
        "evolution_candidates",
        ["status"],
    )
    op.create_index(
        "ix_evolution_candidates_target",
        "evolution_candidates",
        ["target_identifier"],
    )

    # === sandbox_runs ===
    op.create_table(
        "sandbox_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("test_suite_name", sa.String(128), nullable=False),
        sa.Column("baseline_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("candidate_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sandbox_runs")),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["evolution_candidates.id"],
            name=op.f("fk_sandbox_runs_candidate_id_evolution_candidates"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "verdict IN ('PASSED', 'REGRESSED', 'FAILED')",
            name=op.f("ck_sandbox_runs_valid_verdict"),
        ),
    )
    op.create_index(
        "ix_sandbox_runs_candidate_id",
        "sandbox_runs",
        ["candidate_id"],
    )


def downgrade() -> None:
    # Forward-only migration; downgrade provided for testing rollback
    op.drop_table("sandbox_runs")
    op.drop_table("evolution_candidates")
