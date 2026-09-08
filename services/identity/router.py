"""Authentication API endpoints.

All auth failures return generic 401 'Invalid credentials'.
Internal reasons are logged to audit but never sent to the client.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.config import RuntimeSettings
from apps.api.dependencies import (
    AuthenticatedOwner,
    get_audit_engine,
    get_current_owner,
    get_db,
    get_settings,
)
from domain.schemas.auth import (
    LoginRequest,
    OwnerProfile,
    RefreshRequest,
    SessionInfo,
    TokenResponse,
)
from services.identity.rate_limiter import login_rate_limiter, refresh_rate_limiter
from services.identity.service import (
    AuthenticationError,
    get_owner_profile,
    list_active_sessions,
    login,
    logout,
    refresh,
    revoke_all_sessions,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from X-Forwarded-For or direct client host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


@router.post("/login", response_model=TokenResponse)
async def auth_login(
    request: LoginRequest,
    http_request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
    audit_engine: Annotated[AsyncEngine, Depends(get_audit_engine)],
) -> TokenResponse:
    """Owner login. Returns access + refresh tokens.

    Protected by sliding-window rate limiter (5 failed attempts / min -> 429).
    """
    client_ip = _get_client_ip(http_request)
    await login_rate_limiter.check(client_ip)

    try:
        token_response = await login(
            session, request, settings, audit_engine=audit_engine, client_ip=client_ip
        )
        await login_rate_limiter.reset(client_ip)
        return token_response
    except AuthenticationError:
        await login_rate_limiter.record_attempt(client_ip)
        # Generic error — internal reason already audited
        raise HTTPException(status_code=401, detail="Invalid credentials") from None


@router.post("/refresh", response_model=TokenResponse)
async def auth_refresh(
    request: RefreshRequest,
    http_request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
    audit_engine: Annotated[AsyncEngine, Depends(get_audit_engine)],
) -> TokenResponse:
    """Rotate refresh token. Returns new access + refresh tokens.

    Protected by sliding-window rate limiter.
    """
    client_ip = _get_client_ip(http_request)
    await refresh_rate_limiter.check(client_ip)

    try:
        token_response = await refresh(
            session, request, settings, audit_engine=audit_engine, client_ip=client_ip
        )
        await refresh_rate_limiter.reset(client_ip)
        return token_response
    except AuthenticationError:
        await refresh_rate_limiter.record_attempt(client_ip)
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


@router.get("/sessions", response_model=list[SessionInfo])
async def auth_list_sessions(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[SessionInfo]:
    """List active, non-expired, non-revoked sessions for current owner."""
    return await list_active_sessions(
        session=session,
        owner_id=owner.owner_id,
        current_session_id=owner.session_id,
    )


@router.delete("/sessions", status_code=200)
async def auth_revoke_all_sessions(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    include_current: bool = Query(
        False, description="Whether to revoke the current session as well"
    ),
) -> dict[str, int]:
    """Revoke all sessions (or all other sessions if include_current=False)."""
    revoked_count = await revoke_all_sessions(
        session=session,
        owner_id=owner.owner_id,
        include_current=include_current,
        current_session_id=owner.session_id,
    )
    return {"revoked_count": revoked_count}


@router.delete("/sessions/{session_id}", status_code=204)
async def auth_revoke_session(
    session_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> None:
    """Revoke specified session and invalidate associated refresh tokens."""
    revoked = await revoke_session(
        session=session,
        owner_id=owner.owner_id,
        session_id=session_id,
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found")
