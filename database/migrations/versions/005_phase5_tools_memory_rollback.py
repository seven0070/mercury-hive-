"""Phase 5: tool gateway, scoped memory, and rollback artifacts.

Revision ID: 005_phase5
Revises: 004_phase4
Create Date: 2026-09-08

Forward-only migration. Creates:
- tool_definitions table + seeds initial safe tools
- tool_executions table (audited tool invocation logs)
- agent_memories table (scoped key-value memory)
- rollback_artifacts table (reversible action snapshots)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005_phase5"
down_revision: str | None = "004_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_TOOLS = [
    ("file_reader", "Read scoped file artifacts with sandbox constraints.", "LOW", False),
    (
        "file_writer",
        "Write sandboxed file artifacts with automatic rollback backup.",
        "MEDIUM",
        False,
    ),
    ("memory_store", "Store key-value data in scoped persistent memory.", "LOW", False),
    ("memory_fetch", "Fetch scoped key-value data from memory.", "LOW", False),
    ("system_inspector", "Read system health and department status metrics.", "LOW", False),
]


def upgrade() -> None:
    # === tool_definitions ===
    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(32), server_default=sa.text("'MEDIUM'"), nullable=False),
        sa.Column("schema_definition", JSONB(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_definitions")),
        sa.UniqueConstraint("name", name=op.f("uq_tool_definitions_name")),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_tools_valid_risk_level"),
        ),
    )

    # Seed initial tools
    tools_table = sa.table(
        "tool_definitions",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("risk_level", sa.String),
        sa.column("requires_approval", sa.Boolean),
    )
    op.bulk_insert(
        tools_table,
        [
            {
                "name": name,
                "description": desc,
                "risk_level": risk,
                "requires_approval": req_app,
            }
            for name, desc, risk, req_app in INITIAL_TOOLS
        ],
    )

    # === tool_executions ===
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("parameters", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_tool_executions_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_tool_executions_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', "
            "'BLOCKED_BY_POLICY', 'TIMED_OUT')",
            name=op.f("ck_tool_executions_valid_status"),
        ),
    )
    op.create_index(op.f("ix_tool_executions_agent_id"), "tool_executions", ["agent_id"])
    op.create_index(op.f("ix_tool_executions_tool_name"), "tool_executions", ["tool_name"])

    # === agent_memories ===
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column(
            "data_classification",
            sa.String(32),
            server_default=sa.text("'INTERNAL'"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_memories")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_memories_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "scope IN ('TASK', 'DEPARTMENT', 'AGENT_PRIVATE', 'COMPANY_SHARED')",
            name=op.f("ck_memory_valid_scope"),
        ),
        sa.CheckConstraint(
            "data_classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')",
            name=op.f("ck_memory_valid_classification"),
        ),
    )
    op.create_index(
        op.f("ix_agent_memories_lookup"),
        "agent_memories",
        ["agent_id", "scope", "key"],
    )

    # === rollback_artifacts ===
    op.create_table(
        "rollback_artifacts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("target_resource", sa.String(256), nullable=False),
        sa.Column("previous_state", JSONB(), nullable=True),
        sa.Column("new_state", JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            server_default=sa.text("'AVAILABLE'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rollback_artifacts")),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_rollback_artifacts_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_rollback_artifacts_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'EXECUTED', 'FAILED', 'EXPIRED')",
            name=op.f("ck_rollback_valid_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("rollback_artifacts")
    op.drop_table("agent_memories")
    op.drop_table("tool_executions")
    op.drop_table("tool_definitions")
