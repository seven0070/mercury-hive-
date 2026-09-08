"""Pydantic v2 schemas for audit events."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventCreate(BaseModel):
    """Schema for creating audit events.

    Payload must never contain secrets (passwords, tokens, keys).
    The audit service is responsible for redaction before storage.
    """

    event_type: str
    actor_id: uuid.UUID | None = None
    actor_role: str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    action: str
    decision: str | None = None
    reason: str | None = None
    payload: dict | None = None
    correlation_id: uuid.UUID | None = None


class AuditEventResponse(BaseModel):
    """Audit event response schema."""

    id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    actor_role: str | None
    target_type: str | None
    target_id: uuid.UUID | None
    action: str
    decision: str | None
    reason: str | None
    payload: dict | None
    timestamp: datetime
    correlation_id: uuid.UUID | None

    model_config = {"from_attributes": True}
