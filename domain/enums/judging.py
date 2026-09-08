"""Enums for Phase 6: Judging Council, Rubrics, and Evaluation."""

from enum import StrEnum


class EvaluationVerdict(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NEEDS_REVISION = "NEEDS_REVISION"
    DISQUALIFIED = "DISQUALIFIED"


class CouncilStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    IN_DELIBERATION = "IN_DELIBERATION"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"
    ESCALATED_TO_OWNER = "ESCALATED_TO_OWNER"
    CLOSED = "CLOSED"
