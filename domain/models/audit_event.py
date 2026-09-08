"""Audit event model — immutable authentication and security event log.

Phase 1 scope: authentication events only (login, refresh, logout, permission checks).
Full governance audit deferred to Phase 2.

Limitation: Runtime role has INSERT access. A compromised auth service
could forge audit entries. Phase 2 will add a controlled write-through
database function.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domain.models.base import Base


class AuditEvent(Base):
    """Immutable audit record. No UPDATE or DELETE by runtime role."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    actor_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    target_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    decision: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_actor_id", "actor_id"),
        CheckConstraint(
            "decision IS NULL OR decision IN ('ALLOW', 'DENY', 'ERROR')",
            name="valid_audit_decision",
        ),
    )
