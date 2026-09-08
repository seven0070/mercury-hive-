"""Phase 8: Tribe adapter and team/skill/task synchronization.

Revision ID: 008_phase8
Revises: 007_phase7
Create Date: 2026-09-08

Forward-only migration. Creates:
- tribe_mappings table (department to external tribe/squad mapping)
- agent_skills table (certified capability matrix for agents)
- task_sync_mappings table (cross-system task ticket synchronization)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_phase8"
down_revision: str | None = "007_phase7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === tribe_mappings ===
    op.create_table(
        "tribe_mappings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("tribe_name", sa.String(100), nullable=False),
        sa.Column("squad_name", sa.String(100), nullable=False),
        sa.Column("external_team_id", sa.String(128), nullable=False),
        sa.Column(
            "sync_status",
            sa.String(32),
            server_default=sa.text("'SYNCED'"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tribe_mappings")),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_tribe_mappings_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "sync_status IN ('SYNCED', 'PENDING', 'FAILED')",
            name=op.f("ck_tribe_mappings_sync_status"),
        ),
    )
    op.create_index(
        "ix_tribe_mappings_dept",
        "tribe_mappings",
        ["department_id"],
    )

    # === agent_skills ===
    op.create_table(
        "agent_skills",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("skill_name", sa.String(100), nullable=False),
        sa.Column(
            "proficiency_level",
            sa.String(32),
            server_default=sa.text("'COMPETENT'"),
            nullable=False,
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_skills")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_skills_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["agents.id"],
            name=op.f("fk_agent_skills_verified_by_agents"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "proficiency_level IN ('NOVICE', 'COMPETENT', 'EXPERT', 'MASTER')",
            name=op.f("ck_agent_skills_proficiency"),
        ),
        sa.UniqueConstraint(
            "agent_id",
            "skill_name",
            name=op.f("uq_agent_skills_agent_skill"),
        ),
    )
    op.create_index(
        "ix_agent_skills_agent_id",
        "agent_skills",
        ["agent_id"],
    )

    # === task_sync_mappings ===
    op.create_table(
        "task_sync_mappings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("external_system", sa.String(64), nullable=False),
        sa.Column("external_task_id", sa.String(128), nullable=False),
        sa.Column(
            "sync_direction",
            sa.String(32),
            server_default=sa.text("'BIDIRECTIONAL'"),
            nullable=False,
        ),
        sa.Column(
            "sync_status",
            sa.String(32),
            server_default=sa.text("'SYNCED'"),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_sync_mappings")),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_sync_mappings_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "sync_direction IN ('INBOUND', 'OUTBOUND', 'BIDIRECTIONAL')",
            name=op.f("ck_task_sync_direction"),
        ),
        sa.CheckConstraint(
            "sync_status IN ('SYNCED', 'PENDING', 'FAILED')",
            name=op.f("ck_task_sync_status"),
        ),
        sa.UniqueConstraint(
            "external_system",
            "external_task_id",
            name=op.f("uq_task_sync_system_task"),
        ),
    )
    op.create_index(
        "ix_task_sync_mappings_task_id",
        "task_sync_mappings",
        ["task_id"],
    )


def downgrade() -> None:
    # Forward-only migration; downgrade provided for rollback in test harnesses
    op.drop_table("task_sync_mappings")
    op.drop_table("agent_skills")
    op.drop_table("tribe_mappings")
