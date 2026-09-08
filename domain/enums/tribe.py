"""Enums for Phase 8: Tribe Adapter and Team/Skill/Task Synchronization."""

from enum import StrEnum


class SkillProficiency(StrEnum):
    """Proficiency levels for agent skills."""

    NOVICE = "NOVICE"
    COMPETENT = "COMPETENT"
    EXPERT = "EXPERT"
    MASTER = "MASTER"


class SyncDirection(StrEnum):
    """Direction of synchronization between external tribe and Mercury Hive."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class SyncStatus(StrEnum):
    """Synchronization state."""

    SYNCED = "SYNCED"
    PENDING = "PENDING"
    FAILED = "FAILED"

