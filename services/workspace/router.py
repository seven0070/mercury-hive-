"""FastAPI router for Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import AuthenticatedOwner, get_current_owner, get_db
from domain.schemas.workspace import (
    AvatarProfileCreate,
    AvatarProfileResponse,
    MeetingConcludeRequest,
    PresenceSessionResponse,
    PresenceUpdate,
    VirtualMeetingCreate,
    VirtualMeetingResponse,
    WorkspaceZoneCreate,
    WorkspaceZoneResponse,
)
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

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/zones", response_model=WorkspaceZoneResponse)
async def api_create_zone(
    request: WorkspaceZoneCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> WorkspaceZoneResponse:
    """Create a new spatial zone or departmental pod in the 3D office."""
    try:
        zone = await create_zone(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return WorkspaceZoneResponse.model_validate(zone)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/zones", response_model=list[WorkspaceZoneResponse])
async def api_list_zones(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    zone_type: Annotated[str | None, Query()] = None,
) -> list[WorkspaceZoneResponse]:
    """List active spatial zones in the 3D office."""
    zones = await list_zones(session=session, zone_type=zone_type)
    return [WorkspaceZoneResponse.model_validate(z) for z in zones]


@router.post("/avatars", response_model=AvatarProfileResponse)
async def api_create_avatar_profile(
    request: AvatarProfileCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AvatarProfileResponse:
    """Create or update a governed 3D avatar profile with hierarchical attire rules."""
    try:
        profile = await create_avatar_profile(
            session=session,
            data=request,
            creator_id=owner.owner_id,
            creator_role="OWNER",
        )
        return AvatarProfileResponse.model_validate(profile)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/presence", response_model=PresenceSessionResponse)
async def api_update_presence(
    request: PresenceUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[str, Query()] = "OWNER",
) -> PresenceSessionResponse:
    """Update spatial position, orientation, and presence state in a zone."""
    target_id = entity_id or owner.owner_id
    try:
        presence = await update_presence(
            session=session,
            entity_id=target_id,
            entity_type=entity_type,
            data=request,
        )
        return PresenceSessionResponse.model_validate(presence)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/presence", response_model=list[PresenceSessionResponse])
async def api_list_presence(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    zone_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PresenceSessionResponse]:
    """List active online entities occupying spatial zones."""
    sessions = await list_active_presence(session=session, zone_id=zone_id)
    return [PresenceSessionResponse.model_validate(p) for p in sessions]


@router.post("/meetings", response_model=VirtualMeetingResponse)
async def api_schedule_meeting(
    request: VirtualMeetingCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> VirtualMeetingResponse:
    """Schedule a virtual meeting or boardroom conclave."""
    try:
        meeting = await schedule_meeting(
            session=session,
            data=request,
            host_id=owner.owner_id,
            host_role="OWNER",
        )
        return VirtualMeetingResponse.model_validate(meeting)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/meetings/{meeting_id}/start", response_model=VirtualMeetingResponse)
async def api_start_meeting(
    meeting_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> VirtualMeetingResponse:
    """Start a scheduled virtual meeting."""
    try:
        meeting = await start_meeting(
            session=session,
            meeting_id=meeting_id,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return VirtualMeetingResponse.model_validate(meeting)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/meetings/{meeting_id}/conclude", response_model=VirtualMeetingResponse)
async def api_conclude_meeting(
    meeting_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    request: MeetingConcludeRequest | None = None,
) -> VirtualMeetingResponse:
    """Conclude a virtual meeting and record minutes."""
    try:
        minutes = request.meeting_minutes if request else None
        meeting = await conclude_meeting(
            session=session,
            meeting_id=meeting_id,
            minutes=minutes,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return VirtualMeetingResponse.model_validate(meeting)
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
