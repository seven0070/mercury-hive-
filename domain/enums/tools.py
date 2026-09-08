"""Enums for Phase 5: Tool Gateway, Scoped Memory, and Repair/Rollback."""

from enum import StrEnum


class ToolExecutionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    TIMED_OUT = "TIMED_OUT"


class MemoryScope(StrEnum):
    TASK = "TASK"
    DEPARTMENT = "DEPARTMENT"
    AGENT_PRIVATE = "AGENT_PRIVATE"
    COMPANY_SHARED = "COMPANY_SHARED"


class RollbackStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

