"""Initial schema: owners, sessions, refresh tokens, audit events.

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-01

Forward-only migration. Creates:
- pgcrypto extension
- owners table with singleton constraint
- owner_sessions table
- refresh_tokens table
- audit_events table with constrained decision values
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgcrypto for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # === owners ===
    op.create_table(
        "owners",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("singleton", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owners")),
        sa.UniqueConstraint("singleton", name=op.f("uq_owners_singleton")),
        sa.UniqueConstraint("email", name=op.f("uq_owners_email")),
        sa.CheckConstraint("singleton IS TRUE", name=op.f("ck_owners_singleton_true")),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'LOCKED')", name=op.f("ck_owners_valid_owner_status")
        ),
    )

    # === owner_sessions ===
    op.create_table(
        "owner_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(256), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owner_sessions")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["owners.id"],
            name=op.f("fk_owner_sessions_owner_id_owners"),
            ondelete="RESTRICT",
        ),
    )

    # === refresh_tokens ===
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["owner_sessions.id"],
            name=op.f("fk_refresh_tokens_session_id_owner_sessions"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"])

    # === audit_events ===
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("target_type", sa.String(100), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('ALLOW', 'DENY', 'ERROR')",
            name=op.f("ck_audit_events_valid_audit_decision"),
        ),
    )
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])


def downgrade() -> None:
    # Forward-only by policy — downgrade preserved for emergency use only
    op.drop_table("audit_events")
    op.drop_table("refresh_tokens")
    op.drop_table("owner_sessions")
    op.drop_table("owners")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
