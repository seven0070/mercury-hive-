"""Owner model — the single human system administrator."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.models.base import Base

if TYPE_CHECKING:
    from domain.models.session import OwnerSession


class Owner(Base):
    """System owner. Enforces single-owner constraint via the singleton column.

    The singleton column is always True with a UNIQUE constraint,
    guaranteeing at most one row in the table.
    """

    __tablename__ = "owners"

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
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    sessions: Mapped[list["OwnerSession"]] = relationship(
        back_populates="owner",
        lazy="noload",
    )

    __table_args__ = (
        CheckConstraint("singleton IS TRUE", name="singleton_true"),
        CheckConstraint(
            "status IN ('ACTIVE', 'LOCKED')",
            name="valid_owner_status",
        ),
    )
