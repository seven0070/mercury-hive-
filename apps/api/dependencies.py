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
from domain.enums.governance import SystemRunState
from services.constitution.loader import Constitution
from services.governance.shutdown import get_cached_run_state, get_system_state
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
    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        return settings
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


async def get_optional_db(request: Request) -> AsyncGenerator[AsyncSession | None, None]:
    """Get async database session if available in app state, otherwise yield None."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        yield None
        return
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


RECOVERY_ENDPOINTS: frozenset[str] = frozenset(
    {
        "/owner/emergency-shutdown",
        "/owner/override",
        "/owner/dashboard",
        "/owner/console/summary",
        "/owner/audit",
        "/auth/logout",
        "/auth/login",
        "/auth/refresh",
        "/auth/me",
    }
)


def verify_shutdown_state(
    mutation: bool = True,
    allow_in_degraded: bool = False,
):
    """FastAPI dependency to enforce system shutdown state constraints across route modules.

    Guarantees:
    - NORMAL: All requests proceed normally.
    - DEGRADED: Safe read-only queries (GET) proceed. Mutations (POST, PUT, PATCH, DELETE)
      are blocked with HTTP 503 Service Unavailable unless allow_in_degraded=True.
    - EMERGENCY_SHUTDOWN: All mutation operations and all non-owner operations are halted
      with HTTP 503 Service Unavailable. Only recovery endpoints are permitted.
    """

    async def _verifier(
        request: Request,
        session: Annotated[AsyncSession | None, Depends(get_optional_db)] = None,
    ) -> None:
        # 1. Determine current run state and reason
        run_state: SystemRunState | None = None
        shutdown_reason: str | None = None

        # Check app.state override (e.g. for testing)
        app_state_run = getattr(request.app.state, "system_run_state", None)
        if app_state_run is not None:
            run_state = (
                SystemRunState(app_state_run)
                if isinstance(app_state_run, str)
                else app_state_run
            )
            shutdown_reason = getattr(request.app.state, "shutdown_reason", None)

        # Check module-level in-memory cache (fast-path when emergency state is activated)
        if run_state is None:
            cached_state, cached_reason = get_cached_run_state()
            if cached_state != SystemRunState.NORMAL:
                run_state = cached_state
                shutdown_reason = cached_reason

        # Check database if session available and not yet determined
        if run_state is None and session is not None:
            try:
                db_state = await get_system_state(session, for_update=False)
                run_state = SystemRunState(db_state.run_state)
                shutdown_reason = db_state.shutdown_reason
            except Exception:  # noqa: S110
                pass  # Graceful fallback to in-memory cache below

        # Fallback to module-level cache
        if run_state is None:
            run_state, shutdown_reason = get_cached_run_state()

        if run_state == SystemRunState.NORMAL:
            return

        is_mutation_req = mutation or request.method in ("POST", "PUT", "PATCH", "DELETE")
        path = request.url.path
        is_recovery = any(path.rstrip("/").endswith(ep.rstrip("/")) for ep in RECOVERY_ENDPOINTS)

        # 2. DEGRADED mode: permit GET queries, block high-risk mutations
        if run_state == SystemRunState.DEGRADED:
            if is_mutation_req and not allow_in_degraded:
                reason_str = f" Reason: {shutdown_reason}" if shutdown_reason else ""
                raise HTTPException(
                    status_code=503,
                    detail=f"System in degraded mode: mutations temporarily suspended.{reason_str}",
                    headers={"Retry-After": "60"},
                )
            return

        # 3. EMERGENCY_SHUTDOWN mode: halt non-owner ops and all non-recovery mutations
        if run_state == SystemRunState.EMERGENCY_SHUTDOWN:
            if is_recovery:
                return

            # All mutations halted across the system
            if is_mutation_req:
                reason_str = f" Reason: {shutdown_reason}" if shutdown_reason else ""
                raise HTTPException(
                    status_code=503,
                    detail=f"Emergency shutdown active: all mutations halted.{reason_str}",
                    headers={"Retry-After": "300"},
                )

            # Check if actor is owner for read queries
            is_owner = False
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                try:
                    settings = get_settings(request)
                    claims = validate_access_token(
                        token=token,
                        secret_key=settings.jwt_secret_key,
                        algorithm=settings.jwt_algorithm,
                        issuer=settings.jwt_issuer,
                        audience=settings.jwt_audience,
                    )
                    if claims.role == "OWNER":
                        if session is not None:
                            from domain.models.owner import Owner

                            owner_rec = await session.get(Owner, claims.sub)
                            if owner_rec is not None:
                                is_owner = owner_rec.status == "ACTIVE"
                            else:
                                is_owner = True
                        else:
                            is_owner = True
                except Exception:
                    is_owner = False

            if not is_owner:
                reason_str = f" Reason: {shutdown_reason}" if shutdown_reason else ""
                raise HTTPException(
                    status_code=503,
                    detail=f"Emergency shutdown active: non-owner operations halted.{reason_str}",
                    headers={"Retry-After": "300"},
                )

    return _verifier


verify_mutation_allowed = verify_shutdown_state(mutation=True)
verify_query_allowed = verify_shutdown_state(mutation=False)
