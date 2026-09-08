"""SQLAlchemy models for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class TribeMapping(Base):
    """Mapping between a Mercury Hive department and an external tribe/squad."""

    __tablename__ = "tribe_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tribe_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    squad_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    external_team_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    sync_status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'SYNCED'"),
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
            "sync_status IN ('SYNCED', 'PENDING', 'FAILED')",
            name="ck_tribe_mappings_sync_status",
        ),
    )


class AgentSkill(Base):
    """Certified capability and proficiency level for an agent."""

    __tablename__ = "agent_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    proficiency_level: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'COMPETENT'"),
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        Uuid(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "proficiency_level IN ('NOVICE', 'COMPETENT', 'EXPERT', 'MASTER')",
            name="ck_agent_skills_proficiency",
        ),
        UniqueConstraint("agent_id", "skill_name", name="uq_agent_skills_agent_skill"),
    )


class TaskSyncMapping(Base):
    """Mapping connecting a Mercury task to an external tracker ticket/issue."""

    __tablename__ = "task_sync_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_system: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    external_task_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    sync_direction: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'BIDIRECTIONAL'"),
        nullable=False,
    )
    sync_status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'SYNCED'"),
        nullable=False,
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "sync_direction IN ('INBOUND', 'OUTBOUND', 'BIDIRECTIONAL')",
            name="ck_task_sync_direction",
        ),
        CheckConstraint(
            "sync_status IN ('SYNCED', 'PENDING', 'FAILED')",
            name="ck_task_sync_status",
        ),
        UniqueConstraint(
            "external_system",
            "external_task_id",
            name="uq_task_sync_system_task",
        ),
    )

