"""Audit service with dual-transaction support and Phase 2 write-through DB function.

Two modes:
1. log_audit_event() — within current transaction via fn_record_audit_event.
2. log_audit_event_independent() — separate transaction via fn_record_audit_event.
   For failed operations where the request transaction rolls back.

Phase 2 Hardening: Direct INSERT on audit_events is revoked from runtime.
All audit record writes strictly pass through the PostgreSQL SECURITY DEFINER
function `fn_record_audit_event`.
"""

import json
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from domain.schemas.audit import AuditEventCreate

logger = structlog.get_logger()

# Allowed audit event types
ALLOWED_EVENT_TYPES = frozenset({"AUTH", "ACCESS", "SYSTEM", "GOVERNANCE", "SECURITY"})

# Sensitive keys that must be redacted from audit payloads
_REDACT_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "refresh_token",
        "access_token",
        "secret",
        "key",
        "authorization",
    }
)


def _redact_payload(payload: dict | None) -> dict | None:
    """Remove sensitive keys from audit payloads before storage."""
    if payload is None:
        return None
    return {k: "[REDACTED]" if k.lower() in _REDACT_KEYS else v for k, v in payload.items()}


def _validate_event_type(event_type: str) -> str:
    """Validate and sanitize event_type against allowed types."""
    upper = event_type.upper()
    if upper not in ALLOWED_EVENT_TYPES:
        logger.warning("unrecognized_audit_event_type", event_type=event_type)
        return "SYSTEM"
    return upper


async def log_audit_event(
    session: AsyncSession,
    event: AuditEventCreate,
) -> uuid.UUID | None:
    """Log audit event within the current transaction using fn_record_audit_event.

    Use for successful operations where the transaction commits.
    """
    data = event.model_dump()
    data["event_type"] = _validate_event_type(data["event_type"])
    redacted = _redact_payload(data.get("payload"))
    payload_json = json.dumps(redacted) if redacted else None

    result = await session.execute(
        text(
            "SELECT fn_record_audit_event("
            ":event_type, :actor_id, :actor_role, :target_type, :target_id, "
            ":action, :decision, :reason, :payload::jsonb, :correlation_id)"
        ),
        {
            "event_type": data["event_type"],
            "actor_id": str(data["actor_id"]) if data.get("actor_id") else None,
            "actor_role": data.get("actor_role"),
            "target_type": data.get("target_type"),
            "target_id": str(data["target_id"]) if data.get("target_id") else None,
            "action": data["action"],
            "decision": data.get("decision"),
            "reason": data.get("reason"),
            "payload": payload_json,
            "correlation_id": str(data["correlation_id"]) if data.get("correlation_id") else None,
        },
    )
    return result.scalar_one_or_none()


async def log_audit_event_independent(
    engine_or_url: AsyncEngine | str,
    event: AuditEventCreate,
) -> uuid.UUID | None:
    """Log audit event in a separate short-lived transaction via fn_record_audit_event.

    Use for failed operations where the request transaction rolls back.
    Ensures AUTH_LOGIN_FAILED, AUTH_REFRESH_REPLAY etc. are persisted
    even when the main request raises an HTTP error.
    """
    data = event.model_dump()
    data["event_type"] = _validate_event_type(data["event_type"])
    redacted = _redact_payload(data.get("payload"))
    payload_json = json.dumps(redacted) if redacted else None

    should_dispose = False
    if isinstance(engine_or_url, str):
        engine = create_async_engine(engine_or_url, pool_size=1, max_overflow=0)
        should_dispose = True
    else:
        engine = engine_or_url

    audit_id: uuid.UUID | None = None
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    "SELECT fn_record_audit_event("
                    ":event_type, :actor_id, :actor_role, :target_type, :target_id, "
                    ":action, :decision, :reason, :payload::jsonb, :correlation_id)"
                ),
                {
                    "event_type": data["event_type"],
                    "actor_id": str(data["actor_id"]) if data.get("actor_id") else None,
                    "actor_role": data.get("actor_role"),
                    "target_type": data.get("target_type"),
                    "target_id": str(data["target_id"]) if data.get("target_id") else None,
                    "action": data["action"],
                    "decision": data.get("decision"),
                    "reason": data.get("reason"),
                    "payload": payload_json,
                    "correlation_id": str(data["correlation_id"])
                    if data.get("correlation_id")
                    else None,
                },
            )
            audit_id = result.scalar_one_or_none()
    except Exception:
        # Audit failure must not crash the application
        logger.warning(
            "audit_event_write_failed",
            event_type=data.get("event_type"),
            action=data.get("action"),
        )
    finally:
        if should_dispose:
            await engine.dispose()

    return audit_id
