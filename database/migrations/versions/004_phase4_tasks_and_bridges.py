"""Phase 4: tasks, cross-department bridges, and delegations.

Revision ID: 004_phase4
Revises: 003_phase3
Create Date: 2026-09-08

Forward-only migration. Creates:
- tasks table (missions, sub-tasks, capability tracking)
- cross_department_bridges table (permissioned inter-department bridges)
- task_delegations table (audited task delegations across bridges)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004_phase4"
down_revision: str | None = "003_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === tasks ===
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(32), server_default=sa.text("'MEDIUM'"), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'CREATED'"), nullable=False),
        sa.Column("origin_department_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_department_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_agent_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=True),
        sa.Column("required_capabilities", JSONB(), nullable=True),
        sa.Column("input_artifacts", JSONB(), nullable=True),
        sa.Column("output_artifacts", JSONB(), nullable=True),
        sa.Column(
            "budget_allocated",
            sa.Numeric(14, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "budget_spent",
            sa.Numeric(14, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.ForeignKeyConstraint(
            ["origin_department_id"],
            ["departments.id"],
            name=op.f("fk_tasks_origin_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_department_id"],
            ["departments.id"],
            name=op.f("fk_tasks_assigned_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_agent_id"],
            ["agents.id"],
            name=op.f("fk_tasks_assigned_agent_id_agents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["tasks.id"],
            name=op.f("fk_tasks_parent_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_tasks_valid_priority"),
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'ASSIGNED', 'IN_PROGRESS', 'BLOCKED', "
            "'AWAITING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name=op.f("ck_tasks_valid_status"),
        ),
    )
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"])
    op.create_index(op.f("ix_tasks_assigned_agent_id"), "tasks", ["assigned_agent_id"])
    op.create_index(op.f("ix_tasks_assigned_department_id"), "tasks", ["assigned_department_id"])

    # === cross_department_bridges ===
    op.create_table(
        "cross_department_bridges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_department_id", sa.Uuid(), nullable=False),
        sa.Column("target_department_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column(
            "allowed_data_classification",
            sa.String(32),
            server_default=sa.text("'INTERNAL'"),
            nullable=False,
        ),
        sa.Column("data_sharing_scopes", JSONB(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cross_department_bridges")),
        sa.ForeignKeyConstraint(
            ["source_department_id"],
            ["departments.id"],
            name=op.f("fk_cross_department_bridges_source_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_department_id"],
            ["departments.id"],
            name=op.f("fk_cross_department_bridges_target_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'ACTIVE', 'REVOKED', 'EXPIRED')",
            name=op.f("ck_bridges_valid_status"),
        ),
        sa.CheckConstraint(
            "allowed_data_classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')",
            name=op.f("ck_bridges_valid_classification"),
        ),
        sa.CheckConstraint(
            "source_department_id != target_department_id",
            name=op.f("ck_bridges_distinct_departments"),
        ),
    )
    op.create_index(
        op.f("ix_bridges_source"),
        "cross_department_bridges",
        ["source_department_id"],
    )
    op.create_index(
        op.f("ix_bridges_target"),
        "cross_department_bridges",
        ["target_department_id"],
    )

    # === task_delegations ===
    op.create_table(
        "task_delegations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("bridge_id", sa.Uuid(), nullable=False),
        sa.Column("delegated_from_agent_id", sa.Uuid(), nullable=False),
        sa.Column("delegated_to_agent_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_delegations")),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_delegations_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bridge_id"],
            ["cross_department_bridges.id"],
            name=op.f("fk_task_delegations_bridge_id_cross_department_bridges"),
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    op.drop_table("task_delegations")
    op.drop_table("cross_department_bridges")
    op.drop_table("tasks")
