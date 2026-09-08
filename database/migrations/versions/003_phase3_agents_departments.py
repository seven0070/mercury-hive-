"""Phase 3: departments, agents, and permission grants.

Revision ID: 003_phase3
Revises: 002_phase2
Create Date: 2026-09-08

Forward-only migration. Creates:
- departments table + seeds initial 10 core departments
- agents table (AI workforce registry)
- permission_grants table (scoped, revocable authority)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "003_phase3"
down_revision: str | None = "002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_DEPARTMENTS = [
    ("Research", "Conducts fundamental exploration and hypothesis generation."),
    ("Engineering", "Builds, maintains, and hardens technical systems and architecture."),
    ("Product", "Defines product requirements, roadmaps, and feature specifications."),
    ("Marketing", "Handles public positioning, growth, and brand communications."),
    ("Finance", "Monitors budgets, resource usage, and financial allocations."),
    ("Legal and Compliance", "Enforces regulatory, policy, and contractual governance."),
    ("Security", "Continuous threat modeling, security review, and defense."),
    ("Operations", "Coordinates infrastructure, runtime health, and execution workflows."),
    ("Customer Support", "Maintains user satisfaction and triage assistance."),
    ("Judging", "Evaluates submissions and deliverables against standardized rubrics."),
]


def upgrade() -> None:
    # === departments ===
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("hr_owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "data_classification",
            sa.String(32),
            server_default=sa.text("'INTERNAL'"),
            nullable=False,
        ),
        sa.Column("budget", sa.Numeric(14, 2), server_default=sa.text("0.0"), nullable=False),
        sa.Column("workspace_metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("name", name=op.f("uq_departments_name")),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'PILOT', 'ACTIVE', 'SUSPENDED', 'ARCHIVED')",
            name=op.f("ck_departments_valid_status"),
        ),
        sa.CheckConstraint(
            "data_classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')",
            name=op.f("ck_departments_valid_data_classification"),
        ),
    )
    op.create_index(op.f("ix_departments_name"), "departments", ["name"])

    # Seed the 10 initial departments
    dept_table = sa.table(
        "departments",
        sa.column("name", sa.String),
        sa.column("purpose", sa.Text),
        sa.column("status", sa.String),
        sa.column("data_classification", sa.String),
        sa.column("budget", sa.Numeric),
    )
    op.bulk_insert(
        dept_table,
        [
            {
                "name": name,
                "purpose": purpose,
                "status": "ACTIVE",
                "data_classification": "INTERNAL",
                "budget": 10000.0,
            }
            for name, purpose in INITIAL_DEPARTMENTS
        ],
    )

    # === agents ===
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("persona_source", sa.String(256), nullable=True),
        sa.Column("persona_disclosure", sa.Text(), nullable=True),
        sa.Column(
            "system_prompt_version",
            sa.String(32),
            server_default=sa.text("'1.0.0'"),
            nullable=False,
        ),
        sa.Column("avatar_profile_id", sa.Uuid(), nullable=True),
        sa.Column("parent_agent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_agents_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["agents.id"],
            name=op.f("fk_agents_manager_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_agent_id"],
            ["agents.id"],
            name=op.f("fk_agents_parent_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "role IN ('OWNER', 'CEO', 'HR', 'DEPARTMENT_MANAGER', "
            "'WORKER', 'VERIFIER', 'JUDGE', 'TEMPORARY_SUB_AGENT')",
            name=op.f("ck_agents_valid_role"),
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'SANDBOX', 'PROBATION', 'ACTIVE', "
            "'RESTRICTED', 'SUSPENDED', 'QUARANTINED', 'ARCHIVED', 'TERMINATED')",
            name=op.f("ck_agents_valid_status"),
        ),
    )
    op.create_index(op.f("ix_agents_role"), "agents", ["role"])
    op.create_index(op.f("ix_agents_status"), "agents", ["status"])
    op.create_index(op.f("ix_agents_department_id"), "agents", ["department_id"])

    # === permission_grants ===
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column(
            "allowed_actions", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("allowed_tools", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("memory_scopes", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("budget_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_requirements", JSONB(), nullable=True),
        sa.Column("issued_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_grants")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_permission_grants_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_permission_grants_department_id_departments"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_permission_grants_agent_id"), "permission_grants", ["agent_id"])


def downgrade() -> None:
    op.drop_table("permission_grants")
    op.drop_table("agents")
    op.drop_table("departments")
