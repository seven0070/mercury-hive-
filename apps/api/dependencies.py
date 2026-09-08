"""FastAPI dependency injection.

Provides database sessions, settings, constitution, and auth.
"""

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.config import RuntimeSettings
from services.constitution.loader import Constitution
from services.identity.tokens import TokenError, validate_access_token


@dataclass(frozen=True)
class AuthenticatedOwner:
    """Represents the authenticated owner from a valid access token."""

    owner_id: uuid.UUID
    session_id: uuid.UUID
    token_id: uuid.UUID


def get_settings(request: Request) -> RuntimeSettings:
    """Get runtime settings from app state."""
    return request.app.state.settings


def get_constitution(request: Request) -> Constitution:
    """Get validated constitution from app state."""
    return request.app.state.constitution


def get_audit_engine(request: Request) -> AsyncEngine:
    """Get persistent audit engine from app state."""
    return request.app.state.audit_engine


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_owner(
    request: Request,
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
) -> AuthenticatedOwner:
    """Validate access token and return authenticated owner.

    All token validation failures return generic 401.
    Internal reasons are NOT returned to the client.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_header[7:]  # Strip 'Bearer '
    try:
        claims = validate_access_token(
            token=token,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except TokenError:
        # Internal reason logged elsewhere; generic error to client
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    return AuthenticatedOwner(
        owner_id=claims.sub,
        session_id=claims.sid,
        token_id=claims.jti,
    )
