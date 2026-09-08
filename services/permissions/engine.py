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
    actor_department_id: uuid.UUID | None = None,
    target_department_id: uuid.UUID | None = None,
    target_agent_id: uuid.UUID | None = None,
    target_author_id: uuid.UUID | None = None,
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

    # Check 1b: Soft shutdown gate — block mutating actions for non-owner
    if (
        system_run_state == SystemRunState.DEGRADED
        and actor_role != "OWNER"
        and action
        in (
            "create_worker",
            "create_hr",
            "execute_task",
            "execute_tool",
            "promote_candidate",
        )
    ):
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="soft_shutdown_active",
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

    # Check 3: Status check
    if actor_status != "ACTIVE":
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="owner_not_active" if actor_role == "OWNER" else "actor_not_active",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 4: Anti-tamper & Conflict-of-interest checks
    # 4a: No actor can change their own permissions
    if (
        action in ("grant_permission", "revoke_permission", "change_own_permissions")
        and target_agent_id == actor_id
    ):
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="cannot_modify_own_permissions",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # 4b: No actor can approve or verify their own work
    if (
        action in ("approve_output", "verify_task", "judge_submission")
        and target_author_id is not None
        and actor_id == target_author_id
    ):
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="cannot_approve_own_output",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 5: Constitution modifications — strictly OWNER only
    if action in ("change_constitution", "update_constitution"):
        if actor_role == "OWNER":
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason="owner_authorized",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="only_owner_can_modify_constitution",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Check 6: Role hierarchy permissions
    if actor_role == "OWNER":
        return AuthorizationResult(
            decision=Decision.ALLOW,
            reason="owner_authorized",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action == "create_hr":
        if actor_role == "CEO":
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason="ceo_authorized_for_create_hr",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role_for_create_hr",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action == "create_worker":
        if actor_role in ("CEO", "HR"):
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason=f"{actor_role.lower()}_authorized_for_create_worker",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role_for_create_worker",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action == "assign_worker":
        if actor_role in ("CEO", "HR"):
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason=f"{actor_role.lower()}_authorized_for_assign_worker",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        if actor_role == "DEPARTMENT_MANAGER":
            if (
                actor_department_id
                and target_department_id
                and actor_department_id == target_department_id
            ):
                return AuthorizationResult(
                    decision=Decision.ALLOW,
                    reason="manager_authorized_within_department_scope",
                    actor_id=actor_id,
                    action=action,
                    resource=resource,
                )
            return AuthorizationResult(
                decision=Decision.DENY,
                reason="manager_out_of_department_scope",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role_for_assign_worker",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action == "create_permanent_agent":
        if actor_role in ("CEO", "HR"):
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason=f"{actor_role.lower()}_authorized_for_permanent_agent",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role_for_permanent_agent",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action == "terminate_worker":
        if actor_role == "CEO":
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason="ceo_authorized_for_terminate_worker",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        if actor_role == "HR":
            return AuthorizationResult(
                decision=Decision.ALLOW,
                reason="hr_authorized_for_terminate_worker",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        if actor_role == "DEPARTMENT_MANAGER":
            return AuthorizationResult(
                decision=Decision.DENY,
                reason="manager_can_only_recommend_termination",
                actor_id=actor_id,
                action=action,
                resource=resource,
            )
        return AuthorizationResult(
            decision=Decision.DENY,
            reason="insufficient_role_for_terminate_worker",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action in ("execute_task", "perform_work") and actor_role in (
        "WORKER",
        "TEMPORARY_SUB_AGENT",
        "DEPARTMENT_MANAGER",
        "CEO",
        "VERIFIER",
        "JUDGE",
    ):
        return AuthorizationResult(
            decision=Decision.ALLOW,
            reason="agent_authorized_for_task_execution",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action in ("execute_tool", "call_tool") and actor_role in (
        "WORKER",
        "TEMPORARY_SUB_AGENT",
    ):
        return AuthorizationResult(
            decision=Decision.ALLOW,
            reason="worker_authorized_for_tool_execution",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    if action in ("verify_task", "judge_submission") and actor_role in (
        "VERIFIER",
        "JUDGE",
    ):
        return AuthorizationResult(
            decision=Decision.ALLOW,
            reason="verifier_authorized_for_verification",
            actor_id=actor_id,
            action=action,
            resource=resource,
        )

    # Deny by default
    return AuthorizationResult(
        decision=Decision.DENY,
        reason="insufficient_role",
        actor_id=actor_id,
        action=action,
        resource=resource,
    )
