"""Phase 10: 3D Workspace Contracts, Avatars, Attire, Presence & Virtual Meetings."""

from services.workspace.service import (
    WorkspaceError,
    conclude_meeting,
    create_avatar_profile,
    create_zone,
    list_active_presence,
    list_zones,
    schedule_meeting,
    start_meeting,
    update_presence,
)

__all__ = [
    "WorkspaceError",
    "create_zone",
    "list_zones",
    "create_avatar_profile",
    "update_presence",
    "list_active_presence",
    "schedule_meeting",
    "start_meeting",
    "conclude_meeting",
]
