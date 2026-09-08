from enum import StrEnum


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SystemRunState(StrEnum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
