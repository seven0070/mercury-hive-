"""Pydantic schemas for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.enums.workspace import (
    AttireClass,
    MeetingRole,
    MeetingStatus,
    PresenceState,
    ZoneType,
)


class WorkspaceZoneCreate(BaseModel):
    """Schema for creating a 3D workspace zone."""

    name: str = Field(min_length=2, max_length=100)
    zone_type: ZoneType
    department_id: uuid.UUID | None = None
    capacity: int = Field(default=20, ge=1, le=1000)
    security_level: str = Field(default="CONFIDENTIAL")
    spatial_bounds: dict[str, Any]


class WorkspaceZoneResponse(BaseModel):
    """Schema for returning workspace zone details."""

    id: uuid.UUID
    name: str
    zone_type: ZoneType
    department_id: uuid.UUID | None = None
    capacity: int
    security_level: str
    spatial_bounds: dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AvatarProfileCreate(BaseModel):
    """Schema for creating or updating an agent/owner avatar profile."""

    agent_id: uuid.UUID | None = None
    avatar_model_uri: str = Field(min_length=3, max_length=512)
    attire_class: AttireClass
    customization_payload: dict[str, Any] | None = None


class AvatarProfileResponse(BaseModel):
    """Schema for returning avatar profile details."""

    id: uuid.UUID
    agent_id: uuid.UUID | None = None
    avatar_model_uri: str
    attire_class: AttireClass
    customization_payload: dict[str, Any] | None = None
    is_approved: bool
    approved_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PresenceUpdate(BaseModel):
    """Schema for updating spatial location and telemetry in 3D office."""

    zone_id: uuid.UUID
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    rotation_yaw: float = 0.0
    presence_state: PresenceState = PresenceState.ONLINE
    current_task_id: uuid.UUID | None = None


class PresenceSessionResponse(BaseModel):
    """Schema for returning presence session telemetry."""

    id: uuid.UUID
    entity_id: uuid.UUID
    entity_type: str
    zone_id: uuid.UUID
    position_x: float
    position_y: float
    position_z: float
    rotation_yaw: float
    presence_state: PresenceState
    current_task_id: uuid.UUID | None = None
    last_heartbeat_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VirtualMeetingCreate(BaseModel):
    """Schema for scheduling a virtual meeting or boardroom conclave."""

    title: str = Field(min_length=3, max_length=256)
    zone_id: uuid.UUID
    agenda: str | None = None
    scheduled_start: datetime


class VirtualMeetingResponse(BaseModel):
    """Schema for returning virtual meeting details."""

    id: uuid.UUID
    title: str
    zone_id: uuid.UUID
    host_id: uuid.UUID
    status: MeetingStatus
    agenda: str | None = None
    meeting_minutes: dict[str, Any] | None = None
    scheduled_start: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MeetingParticipantAdd(BaseModel):
    """Schema for adding an attendee to a virtual meeting."""

    entity_id: uuid.UUID
    role_in_meeting: MeetingRole = MeetingRole.ATTENDEE


class MeetingParticipantResponse(BaseModel):
    """Schema for returning meeting participant details."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    entity_id: uuid.UUID
    role_in_meeting: MeetingRole
    joined_at: datetime
    left_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MeetingConcludeRequest(BaseModel):
    """Schema for concluding a virtual meeting and recording minutes."""

    meeting_minutes: dict[str, Any] | None = None
