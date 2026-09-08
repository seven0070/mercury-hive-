"""Enums for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

from enum import StrEnum


class ZoneType(StrEnum):
    """Types of 3D spatial zones."""

    EXECUTIVE_SUITE = "EXECUTIVE_SUITE"
    DEPARTMENT_POD = "DEPARTMENT_POD"
    BOARDROOM = "BOARDROOM"
    AUDITORIUM = "AUDITORIUM"
    SECURE_VAULT = "SECURE_VAULT"
    COMMONS = "COMMONS"


class AttireClass(StrEnum):
    """Hierarchically governed corporate attire classes."""

    EXECUTIVE_FORMAL = "EXECUTIVE_FORMAL"
    BUSINESS_PROFESSIONAL = "BUSINESS_PROFESSIONAL"
    TECHNICAL_SMART = "TECHNICAL_SMART"
    STANDARD_UTILITY = "STANDARD_UTILITY"


class PresenceState(StrEnum):
    """Real-time spatial presence states."""

    ONLINE = "ONLINE"
    IN_MEETING = "IN_MEETING"
    IDLE = "IDLE"
    OFFLINE = "OFFLINE"


class MeetingStatus(StrEnum):
    """Status of virtual boardroom or department conclaves."""

    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    CONCLUDED = "CONCLUDED"
    CANCELLED = "CANCELLED"


class MeetingRole(StrEnum):
    """Role of an entity within a virtual meeting."""

    HOST = "HOST"
    SPEAKER = "SPEAKER"
    ATTENDEE = "ATTENDEE"
    OBSERVER = "OBSERVER"
