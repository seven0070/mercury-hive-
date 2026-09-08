"""Phase 2 governance: system states, constitution records, approvals, budgets,
and tamper-proof audit function.

Revision ID: 002_phase2
Revises: 001_initial
Create Date: 2026-09-08

Forward-only migration. Creates:
- system_states table (singleton emergency shutdown controls)
- constitution_records table
- approvals table
- budgets table
- fn_record_audit_event SECURITY DEFINER function
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_phase2"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === system_states ===
    op.create_table(
        "system_states",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("singleton", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("run_state", sa.String(32), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column("shutdown_reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_states")),
        sa.UniqueConstraint("singleton", name=op.f("uq_system_states_singleton")),
        sa.CheckConstraint("singleton IS TRUE", name=op.f("ck_system_states_singleton_true")),
        sa.CheckConstraint(
            "run_state IN ('NORMAL', 'DEGRADED', 'EMERGENCY_SHUTDOWN')",
            name=op.f("ck_system_states_valid_run_state"),
        ),
    )

    # Seed initial system state
    op.execute(
        "INSERT INTO system_states (id, singleton, run_state, updated_at) "
        "VALUES (gen_random_uuid(), true, 'NORMAL', now())"
    )

    # === constitution_records ===
    op.create_table(
        "constitution_records",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_constitution_records")),
    )
    op.create_index(
        op.f("ix_constitution_records_sha256_hash"), "constitution_records", ["sha256_hash"]
    )

    # Seed active constitution record
    op.execute(
        "INSERT INTO constitution_records "
        "(id, schema_version, policy_version, sha256_hash, is_active, activated_at) "
        "VALUES (gen_random_uuid(), 1, 1, "
        "'080dc01a2b8dab79c8f0fa005013581650ba124c9f44e2c1893aa5ff6239cbaa', true, now())"
    )

    # === approvals ===
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("risk_level", sa.String(32), server_default=sa.text("'MEDIUM'"), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_approvals_valid_risk_level"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name=op.f("ck_approvals_valid_status"),
        ),
    )
    op.create_index(op.f("ix_approvals_action_type"), "approvals", ["action_type"])
    op.create_index(op.f("ix_approvals_status"), "approvals", ["status"])

    # === budgets ===
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("spent_amount", sa.Numeric(14, 2), server_default=sa.text("0.0"), nullable=False),
        sa.Column("currency", sa.String(8), server_default=sa.text("'USD'"), nullable=False),
        sa.Column(
            "reset_period", sa.String(32), server_default=sa.text("'MONTHLY'"), nullable=False
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_index(op.f("ix_budgets_department_id"), "budgets", ["department_id"])

    # === fn_record_audit_event (SECURITY DEFINER) ===
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_record_audit_event(
            p_event_type VARCHAR(100),
            p_actor_id UUID,
            p_actor_role VARCHAR(50),
            p_target_type VARCHAR(100),
            p_target_id UUID,
            p_action VARCHAR(100),
            p_decision VARCHAR(50),
            p_reason TEXT,
            p_payload JSONB,
            p_correlation_id UUID
        ) RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            v_audit_id UUID;
        BEGIN
            INSERT INTO audit_events (
                id, event_type, actor_id, actor_role, target_type, target_id,
                action, decision, reason, payload, timestamp, correlation_id
            ) VALUES (
                gen_random_uuid(), p_event_type, p_actor_id,
                p_actor_role, p_target_type, p_target_id,
                p_action, p_decision, p_reason, p_payload, now(), p_correlation_id
            ) RETURNING id INTO v_audit_id;

            RETURN v_audit_id;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fn_record_audit_event")
    op.drop_table("budgets")
    op.drop_table("approvals")
    op.drop_table("constitution_records")
    op.drop_table("system_states")
