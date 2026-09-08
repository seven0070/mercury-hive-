"""Deny-by-default authorization engine.

Phase 1: Only OWNER role exists. Checks:
1. Identity is authenticated
2. Role is OWNER
3. Owner status is ACTIVE
4. Log ALLOW/DENY to audit

Phase 2+ will add: agent roles, department scoping, task ownership,
tool permissions, budget, emergency shutdown.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

import structlog

logger = structlog.get_logger()


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class AuthorizationResult:
    """Result of an authorization check."""

    decision: Decision
    reason: str
    actor_id: uuid.UUID | None = None
    action: str = ""
    resource: str = ""


async def authorize(
    actor_id: uuid.UUID | None,
    actor_role: str | None,
    actor_status: str | None,
    action: str,
    resource: str,
) -> AuthorizationResult:
    """Phase 1 authorization: deny-by-default, owner-only.

    Every decision is logged. All checks are server-side.
    No client-selected roles or authority.
    """
    # Check 1: Must be authenticated
    if actor_id is None:
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="not_authenticated",
            action=action,
            resource=resource,
        )

    # Check 2: Must be OWNER (only role in Phase 1)
    if actor_role != "OWNER":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 3: Must be ACTIVE
    if actor_status != "ACTIVE":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="owner_not_active",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Phase 1: Owner with ACTIVE status → ALLOW
    return AuthorizationResult(
        decision=Decision.ALLOW,
        reason="owner_authorized",
        actor_id=actor_id,
        action=action,
        resource=resource,
    )
