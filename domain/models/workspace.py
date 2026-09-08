"""SQLAlchemy models for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class WorkspaceZone(Base):
    """Spatial zone or departmental pod within the 3D virtual office."""

    __tablename__ = "workspace_zones"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    zone_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    capacity: Mapped[int] = mapped_column(
        Integer,
        server_default=text("20"),
        nullable=False,
    )
    security_level: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'CONFIDENTIAL'"),
        nullable=False,
    )
    spatial_bounds: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('EXECUTIVE_SUITE', 'DEPARTMENT_POD', 'BOARDROOM', "
            "'AUDITORIUM', 'SECURE_VAULT', 'COMMONS')",
            name="ck_workspace_zones_valid_type",
        ),
        CheckConstraint(
            "security_level IN ('PUBLIC', 'CONFIDENTIAL', 'RESTRICTED')",
            name="ck_workspace_zones_security_level",
        ),
    )


class AvatarProfile(Base):
    """Governed 3D digital persona and corporate attire profile."""

    __tablename__ = "avatar_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
    )
    avatar_model_uri: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    attire_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    customization_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("owners.id", ondelete="SET NULL"),
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

    __table_args__ = (
        CheckConstraint(
            "attire_class IN ('EXECUTIVE_FORMAL', 'BUSINESS_PROFESSIONAL', "
            "'TECHNICAL_SMART', 'STANDARD_UTILITY')",
            name="ck_avatar_profiles_attire",
        ),
    )


class PresenceSession(Base):
    """Real-time spatial coordinates and channel presence in 3D space."""

    __tablename__ = "presence_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'AGENT'"),
        nullable=False,
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_zones.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position_x: Mapped[float] = mapped_column(
        Numeric(8, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    position_y: Mapped[float] = mapped_column(
        Numeric(8, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    position_z: Mapped[float] = mapped_column(
        Numeric(8, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    rotation_yaw: Mapped[float] = mapped_column(
        Numeric(6, 2),
        server_default=text("0.0"),
        nullable=False,
    )
    presence_state: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'ONLINE'"),
        nullable=False,
    )
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "presence_state IN ('ONLINE', 'IN_MEETING', 'IDLE', 'OFFLINE')",
            name="ck_presence_sessions_state",
        ),
        CheckConstraint(
            "entity_type IN ('OWNER', 'AGENT')",
            name="ck_presence_sessions_entity_type",
        ),
    )


class VirtualMeeting(Base):
    """Governed boardroom conclave or departmental virtual meeting."""

    __tablename__ = "virtual_meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace_zones.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'SCHEDULED'"),
        nullable=False,
    )
    agenda: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    meeting_minutes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('SCHEDULED', 'IN_PROGRESS', 'CONCLUDED', 'CANCELLED')",
            name="ck_virtual_meetings_status",
        ),
    )


class MeetingParticipant(Base):
    """Participant or observer attached to a virtual meeting."""

    __tablename__ = "meeting_participants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("virtual_meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    role_in_meeting: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'ATTENDEE'"),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role_in_meeting IN ('HOST', 'SPEAKER', 'ATTENDEE', 'OBSERVER')",
            name="ck_meeting_participants_role",
        ),
    )

