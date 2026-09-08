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


@dataclass(frozen=True)
class AuthenticatedAgent:
    """Represents an authenticated AI agent with live database-verified authority."""

    agent_id: uuid.UUID
    role: str
    status: str
    department_id: uuid.UUID | None
    token_id: uuid.UUID


@dataclass(frozen=True)
class AuthenticatedActor:
    """Unified actor identity for routes accessible to either Owner or Agent."""

    actor_id: uuid.UUID
    actor_role: str
    actor_status: str
    department_id: uuid.UUID | None = None
    is_owner: bool = False
    token_id: uuid.UUID | None = None


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


async def get_current_agent(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
) -> AuthenticatedAgent:
    """Validate token and resolve agent authority directly from PostgreSQL.

    Security guarantees:
    - Never trusts client-visible 'role' or 'department_id' claims in JWT.
    - Always reloads the live Agent record from the database.
    - Rejects suspended, quarantined, or terminated agents immediately (403).
    - Ensures instant revocation and role change propagation without token reissue.
    """
    from domain.enums.agent_status import AgentStatus
    from domain.models.agents import Agent

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_header[7:]
    try:
        claims = validate_access_token(
            token=token,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    # Reload from live database - do NOT trust claims for authority
    agent = await session.get(Agent, claims.sub)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Immediate status revocation check
    if agent.status != AgentStatus.ACTIVE.value:
        raise HTTPException(
            status_code=403,
            detail=f"Agent is not active: status is {agent.status}",
        )

    return AuthenticatedAgent(
        agent_id=agent.id,
        role=agent.role,  # Authoritative from DB
        status=agent.status,  # Authoritative from DB
        department_id=agent.department_id,  # Authoritative from DB
        token_id=claims.jti,
    )


async def get_current_actor(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
) -> AuthenticatedActor:
    """Resolve actor identity from database for routes open to Owner or Agents."""
    from domain.enums.agent_status import AgentStatus
    from domain.models.agents import Agent
    from domain.models.owner import Owner

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_header[7:]
    try:
        claims = validate_access_token(
            token=token,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    # Check if Owner
    owner = await session.get(Owner, claims.sub)
    if owner is not None:
        if owner.status != "ACTIVE":
            raise HTTPException(status_code=403, detail="Owner account is not active")
        return AuthenticatedActor(
            actor_id=owner.id,
            actor_role="OWNER",
            actor_status=owner.status,
            is_owner=True,
            token_id=claims.jti,
        )

    # Otherwise must be Agent
    agent = await session.get(Agent, claims.sub)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if agent.status != AgentStatus.ACTIVE.value:
        raise HTTPException(
            status_code=403,
            detail=f"Agent is not active: status is {agent.status}",
        )

    return AuthenticatedActor(
        actor_id=agent.id,
        actor_role=agent.role,
        actor_status=agent.status,
        department_id=agent.department_id,
        is_owner=False,
        token_id=claims.jti,
    )
