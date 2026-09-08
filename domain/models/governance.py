"""Governance domain models for Phase 2: SystemState, ConstitutionRecord, Approval, Budget."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class SystemState(Base):
    """System run state and emergency shutdown singleton."""

    __tablename__ = "system_states"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    singleton: Mapped[bool] = mapped_column(
        Boolean,
        unique=True,
        nullable=False,
        server_default=text("true"),
    )
    run_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'NORMAL'"),
    )
    shutdown_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("singleton IS TRUE", name="ck_system_states_singleton_true"),
        CheckConstraint(
            "run_state IN ('NORMAL', 'DEGRADED', 'EMERGENCY_SHUTDOWN')",
            name="ck_system_states_valid_run_state",
        ),
    )


class ConstitutionRecord(Base):
    """Immutable log of active and historical constitutional policy records."""

    __tablename__ = "constitution_records"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    schema_version: Mapped[int] = mapped_column(
        nullable=False,
    )
    policy_version: Mapped[int] = mapped_column(
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class Approval(Base):
    """Records actions requiring higher-tier or owner approval."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'MEDIUM'"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'PENDING'"),
        index=True,
    )
    decision: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_approvals_valid_risk_level",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="ck_approvals_valid_status",
        ),
    )


class Budget(Base):
    """Department and resource budget allocations."""

    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    allocated_amount: Mapped[float] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    spent_amount: Mapped[float] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        server_default=text("0.0"),
    )
    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        server_default=text("'USD'"),
    )
    reset_period: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'MONTHLY'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
