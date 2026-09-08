"""SQLAlchemy models for Phase 4: Tasks, Missions, and Cross-Department Bridges."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class Task(Base):
    """Governed task or mission within Mercury Hive."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'MEDIUM'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'CREATED'"),
        nullable=False,
    )
    origin_department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    required_capabilities: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    input_artifacts: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    output_artifacts: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    budget_allocated: Mapped[float] = mapped_column(
        Numeric(14, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    budget_spent: Mapped[float] = mapped_column(
        Numeric(14, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_tasks_valid_priority",
        ),
        CheckConstraint(
            "status IN ('CREATED', 'ASSIGNED', 'IN_PROGRESS', 'BLOCKED', "
            "'AWAITING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_tasks_valid_status",
        ),
    )


class CrossDepartmentBridge(Base):
    """Audited, temporary permission gateway connecting two isolated departments."""

    __tablename__ = "cross_department_bridges"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'PENDING'"),
        nullable=False,
    )
    allowed_data_classification: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'INTERNAL'"),
        nullable=False,
    )
    data_sharing_scopes: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'ACTIVE', 'REVOKED', 'EXPIRED')",
            name="ck_bridges_valid_status",
        ),
        CheckConstraint(
            "allowed_data_classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')",
            name="ck_bridges_valid_classification",
        ),
        CheckConstraint(
            "source_department_id != target_department_id",
            name="ck_bridges_distinct_departments",
        ),
    )


class TaskDelegation(Base):
    """Record of task handoff across an active cross-department bridge."""

    __tablename__ = "task_delegations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cross_department_bridges.id", ondelete="RESTRICT"),
        nullable=False,
    )
    delegated_from_agent_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    delegated_to_agent_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

