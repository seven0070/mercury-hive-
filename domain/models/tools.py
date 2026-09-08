"""SQLAlchemy models for Phase 5: Tool Gateway, Scoped Memory, and Rollback Artifacts."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class ToolDefinition(Base):
    """Registered tool catalog entry with security constraints."""

    __tablename__ = "tool_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'MEDIUM'"),
        nullable=False,
    )
    schema_definition: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_tools_valid_risk_level",
        ),
    )


class ToolExecution(Base):
    """Audited record of an individual tool invocation by an agent."""

    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tool_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    parameters: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    execution_duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', "
            "'BLOCKED_BY_POLICY', 'TIMED_OUT')",
            name="ck_tool_executions_valid_status",
        ),
    )


class AgentMemory(Base):
    """Scoped persistent key-value memory item."""

    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )
    key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    value: Mapped[dict | list | str | int | float | bool] = mapped_column(
        JSONB,
        nullable=False,
    )
    data_classification: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'INTERNAL'"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        server_default=text("1"),
        nullable=False,
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

    __table_args__ = (
        CheckConstraint(
            "scope IN ('TASK', 'DEPARTMENT', 'AGENT_PRIVATE', 'COMPANY_SHARED')",
            name="ck_memory_valid_scope",
        ),
        CheckConstraint(
            "data_classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')",
            name="ck_memory_valid_classification",
        ),
        UniqueConstraint(
            "agent_id",
            "scope",
            "scope_id",
            "key",
            name="uq_agent_memory_scoped_key",
        ),
    )


class RollbackArtifact(Base):
    """Reversible snapshot of state modifications for automated rollback."""

    __tablename__ = "rollback_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    target_resource: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    previous_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    new_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'AVAILABLE'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reverted_by: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('AVAILABLE', 'EXECUTED', 'FAILED', 'EXPIRED')",
            name="ck_rollback_valid_status",
        ),
    )
