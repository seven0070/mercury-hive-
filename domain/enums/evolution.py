"""Enums for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

from enum import StrEnum


class EvolutionType(StrEnum):
    SYSTEM_PROMPT = "SYSTEM_PROMPT"
    TOOL_DEFINITION = "TOOL_DEFINITION"
    WORKFLOW_PIPELINE = "WORKFLOW_PIPELINE"
    POLICY_RULE = "POLICY_RULE"


class EvolutionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    SANDBOX_TESTING = "SANDBOX_TESTING"
    SHADOW_DEPLOYED = "SHADOW_DEPLOYED"
    APPROVED_FOR_PROMOTION = "APPROVED_FOR_PROMOTION"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class SandboxVerdict(StrEnum):
    PASSED = "PASSED"
    REGRESSED = "REGRESSED"
    FAILED = "FAILED"
