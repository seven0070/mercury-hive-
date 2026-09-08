"""Authentication API endpoints.

All auth failures return generic 401 'Invalid credentials'.
Internal reasons are logged to audit but never sent to the client.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.config import RuntimeSettings
from apps.api.dependencies import (
    AuthenticatedOwner,
    get_audit_engine,
    get_current_owner,
    get_db,
    get_settings,
)
from domain.schemas.auth import LoginRequest, OwnerProfile, RefreshRequest, TokenResponse
from services.identity.service import AuthenticationError, get_owner_profile, login, logout, refresh

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def auth_login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
    audit_engine: Annotated[AsyncEngine, Depends(get_audit_engine)],
) -> TokenResponse:
    """Owner login. Returns access + refresh tokens."""
    try:
        return await login(session, request, settings, audit_engine=audit_engine)
    except AuthenticationError:
        # Generic error — internal reason already audited
        raise HTTPException(status_code=401, detail="Invalid credentials") from None


@router.post("/refresh", response_model=TokenResponse)
async def auth_refresh(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
    audit_engine: Annotated[AsyncEngine, Depends(get_audit_engine)],
) -> TokenResponse:
    """Rotate refresh token. Returns new access + refresh tokens."""
    try:
        return await refresh(session, request, settings, audit_engine=audit_engine)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None


@router.post("/logout", status_code=204)
async def auth_logout(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
) -> None:
    """Revoke the current session."""
    await logout(session, owner.owner_id, owner.session_id, settings)


@router.get("/me", response_model=OwnerProfile)
async def auth_me(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> OwnerProfile:
    """Get authenticated owner profile. Never returns sensitive fields."""
    try:
        return await get_owner_profile(session, owner.owner_id)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None
