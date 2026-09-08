"""Deny-by-default authorization engine.

Governance checks:
1. Emergency shutdown state (blocks all non-owner execution)
2. Identity is authenticated
3. Role authorization (Phase 1/2: only OWNER authorized for executive commands)
4. Owner status is ACTIVE
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

import structlog

from domain.enums.governance import SystemRunState

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
    system_run_state: SystemRunState = SystemRunState.NORMAL,
) -> AuthorizationResult:
    """Evaluate authorization request using deny-by-default governance kernel.

    Every decision is logged. All checks are server-side.
    No client-selected roles or authority.
    """
    # Check 1: Emergency shutdown gate — only OWNER allowed during shutdown
    if system_run_state == SystemRunState.EMERGENCY_SHUTDOWN and actor_role != "OWNER":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="emergency_shutdown_active",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 2: Must be authenticated
    if actor_id is None:
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="not_authenticated",
            action=action,
            resource=resource,
        )

    # Check 3: Role check
    if actor_role != "OWNER":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 4: Status check
    if actor_status != "ACTIVE":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="owner_not_active",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Authorized
    return AuthorizationResult(
        decision=Decision.ALLOW,
        reason="owner_authorized",
        actor_id=actor_id,
        action=action,
        resource=resource,
    )
