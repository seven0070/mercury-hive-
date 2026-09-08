"""Identity service — owner authentication flows.

All authentication failures return generic errors to the caller.
Internal reasons are logged to audit only.

Failed-auth audit events use a separate short-lived transaction
via the persistent audit_engine to survive request transaction rollback (Option A).
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.config import RuntimeSettings
from domain.models.owner import Owner
from domain.models.refresh_token import RefreshToken
from domain.models.session import OwnerSession
from domain.schemas.audit import AuditEventCreate
from domain.schemas.auth import (
    LoginRequest,
    OwnerProfile,
    RefreshRequest,
    SessionInfo,
    TokenResponse,
)
from services.audit.service import log_audit_event, log_audit_event_independent
from services.identity.hashing import needs_rehash, verify_password
from services.identity.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from services.identity.totp import verify_totp_code

logger = structlog.get_logger()


async def _log_audit_independent(
    audit_engine: AsyncEngine | str,
    event_type: str,
    action: str,
    decision: str | None = None,
    reason: str | None = None,
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Log audit event in a separate transaction using the persistent audit engine."""
    try:
        await log_audit_event_independent(
            audit_engine,
            AuditEventCreate(
                event_type=event_type,
                action=action,
                decision=decision,
                reason=reason,
                actor_id=actor_id,
                target_id=target_id,
                correlation_id=correlation_id,
                actor_role="OWNER",
            ),
        )
    except Exception as exc:
        logger.warning("audit_log_independent_failed", error=str(exc))


async def _log_audit(
    session: AsyncSession,
    event_type: str,
    action: str,
    decision: str | None = None,
    reason: str | None = None,
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Log audit event within the current transaction via fn_record_audit_event."""
    try:
        await log_audit_event(
            session,
            AuditEventCreate(
                event_type=event_type,
                actor_id=actor_id,
                actor_role="OWNER",
                action=action,
                decision=decision,
                reason=reason,
                target_id=target_id,
                correlation_id=correlation_id,
            ),
        )
    except Exception as exc:
        logger.warning("audit_log_failed", error=str(exc))


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime object is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class AuthenticationError(Exception):
    """Internal auth error. Message is for logging, not client response."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def login(
    session: AsyncSession,
    request: LoginRequest,
    settings: RuntimeSettings,
    audit_engine: AsyncEngine | None = None,
    client_ip: str | None = None,
) -> TokenResponse:
    """Authenticate owner and return token pair.

    All failures raise AuthenticationError with internal reason.
    The router converts this to a generic 401.
    """
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()
    audit_target = audit_engine or settings.database_url

    # Find owner by email
    result = await session.execute(select(Owner).where(Owner.email == request.email))
    owner = result.scalar_one_or_none()

    if owner is None:
        await _log_audit_independent(
            audit_target,
            "AUTH",
            "login",
            decision="DENY",
            reason="owner_not_found",
            correlation_id=correlation_id,
        )
        raise AuthenticationError("owner_not_found")

    # Verify password
    if not verify_password(request.password, owner.password_hash):
        await _log_audit_independent(
            audit_target,
            "AUTH",
            "login",
            decision="DENY",
            reason="password_mismatch",
            actor_id=owner.id,
            correlation_id=correlation_id,
        )
        raise AuthenticationError("password_mismatch")

    # Check status
    if owner.status != "ACTIVE":
        await _log_audit_independent(
            audit_target,
            "AUTH",
            "login",
            decision="DENY",
            reason="owner_locked",
            actor_id=owner.id,
            correlation_id=correlation_id,
        )
        raise AuthenticationError("owner_locked")

    # Verify TOTP MFA if enabled
    mfa_enabled = getattr(settings, "owner_mfa_enabled", False) or getattr(
        owner, "mfa_enabled", False
    )
    if mfa_enabled:
        mfa_secret = getattr(settings, "owner_mfa_secret", None) or getattr(
            owner, "totp_secret", None
        )
        if (
            not mfa_secret
            or not request.totp_code
            or not verify_totp_code(mfa_secret, request.totp_code)
        ):
            await _log_audit_independent(
                audit_target,
                "AUTH",
                "login",
                decision="DENY",
                reason="mfa_failed",
                actor_id=owner.id,
                correlation_id=correlation_id,
            )
            raise AuthenticationError("mfa_failed")

    # Rehash if parameters changed
    if needs_rehash(owner.password_hash):
        # Note: runtime role can't UPDATE password_hash.
        # This is a documented limitation — rehash requires admin.
        logger.info("password_rehash_needed", owner_id=str(owner.id))

    # Create session (7-day absolute expiry)
    session_id = uuid.uuid4()
    owner_session = OwnerSession(
        id=session_id,
        owner_id=owner.id,
        created_at=now,
        expires_at=now + timedelta(days=settings.jwt_session_days),
    )
    session.add(owner_session)

    # Create refresh token (24-hour expiry)
    raw_refresh = generate_refresh_token()
    refresh_token = RefreshToken(
        id=uuid.uuid4(),
        session_id=session_id,
        token_hash=hash_refresh_token(raw_refresh),
        created_at=now,
        expires_at=now + timedelta(hours=settings.jwt_refresh_token_hours),
    )
    session.add(refresh_token)

    # Update last_login_at
    await session.execute(
        update(Owner).where(Owner.id == owner.id).values(last_login_at=now)
    )

    # Create access token
    access_token = create_access_token(
        owner_id=owner.id,
        session_id=session_id,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expires_minutes=settings.jwt_access_token_minutes,
    )

    # Audit success (same transaction — commits with the session)
    await _log_audit(
        session,
        "AUTH",
        "login",
        decision="ALLOW",
        reason="login_success",
        actor_id=owner.id,
        correlation_id=correlation_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.jwt_access_token_minutes * 60,
    )


async def refresh(
    session: AsyncSession,
    request: RefreshRequest,
    settings: RuntimeSettings,
    audit_engine: AsyncEngine | None = None,
    client_ip: str | None = None,
) -> TokenResponse:
    """Rotate refresh token with replay detection and row-level locking.

    Locking order:
    1. Find token by digest
    2. Lock session row (SELECT FOR UPDATE)
    3. Lock token row (SELECT FOR UPDATE)
    4. Check used_at -> replay detection (revokes session & commits)
    5. Check session validity (revocation & <= now expiry check)
    6. Check token expiry (<= now)
    7. Check owner status
    8. Rotate
    """
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()
    audit_target = audit_engine or settings.database_url
    token_digest = hash_refresh_token(request.refresh_token)

    # 1. Find token by digest
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_digest)
    )
    token = result.scalar_one_or_none()

    if token is None:
        await _log_audit_independent(
            audit_target,
            "AUTH",
            "refresh",
            decision="DENY",
            reason="token_not_found",
            correlation_id=correlation_id,
        )
        raise AuthenticationError("token_not_found")

    # 2. Lock session row
    result = await session.execute(
        select(OwnerSession).where(OwnerSession.id == token.session_id).with_for_update()
    )
    owner_session = result.scalar_one_or_none()
    if owner_session is None:
        raise AuthenticationError("session_not_found")

    # 3. Lock token row
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.id == token.id).with_for_update()
    )
    token = result.scalar_one()

    # 4. REPLAY CHECK (before session checks)
    if token.used_at is not None:
        # REPLAY DETECTED — revoke entire session
        owner_session.revoked_at = now
        owner_session.revocation_reason = "refresh_token_replay"
        await session.commit()
        await _log_audit_independent(
            audit_target,
            "AUTH",
            "refresh",
            decision="DENY",
            reason="replay_detected",
            actor_id=owner_session.owner_id,
            correlation_id=correlation_id,
        )
        raise AuthenticationError("replay_detected")

    # 5. Check session validity (using <= for exact boundary checking)
    if owner_session.revoked_at is not None:
        raise AuthenticationError("session_revoked")
    if _ensure_utc(owner_session.expires_at) <= now:
        raise AuthenticationError("session_expired")

    # 6. Check token expiry (using <= for exact boundary checking)
    if _ensure_utc(token.expires_at) <= now:
        raise AuthenticationError("token_expired")

    # 7. Reload and check owner
    result = await session.execute(select(Owner).where(Owner.id == owner_session.owner_id))
    owner = result.scalar_one()
    if owner.status != "ACTIVE":
        raise AuthenticationError("owner_locked")

    # 8. Mark current token as used
    token.used_at = now

    # 9. Create rotated token (expiry capped at session end)
    new_raw = generate_refresh_token()
    new_expiry = min(
        now + timedelta(hours=settings.jwt_refresh_token_hours),
        _ensure_utc(owner_session.expires_at),
    )
    new_token = RefreshToken(
        id=uuid.uuid4(),
        session_id=owner_session.id,
        token_hash=hash_refresh_token(new_raw),
        created_at=now,
        expires_at=new_expiry,
    )
    session.add(new_token)

    # Create new access token
    access_token = create_access_token(
        owner_id=owner.id,
        session_id=owner_session.id,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expires_minutes=settings.jwt_access_token_minutes,
    )

    # Audit success
    await _log_audit(
        session,
        "AUTH",
        "refresh",
        decision="ALLOW",
        reason="refresh_success",
        actor_id=owner.id,
        correlation_id=correlation_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw,
        expires_in=settings.jwt_access_token_minutes * 60,
    )


async def logout(
    session: AsyncSession,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
    settings: RuntimeSettings,
) -> None:
    """Revoke the current session and invalidate its refresh tokens."""
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()

    result = await session.execute(
        select(OwnerSession).where(OwnerSession.id == session_id).with_for_update()
    )
    owner_session = result.scalar_one_or_none()

    if owner_session is not None and owner_session.revoked_at is None:
        owner_session.revoked_at = now
        owner_session.revocation_reason = "logout"

        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.session_id == session_id,
                RefreshToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

    await _log_audit(
        session,
        "AUTH",
        "logout",
        decision="ALLOW",
        reason="logout",
        actor_id=owner_id,
        correlation_id=correlation_id,
    )


async def list_active_sessions(
    session: AsyncSession,
    owner_id: uuid.UUID,
    current_session_id: uuid.UUID | None = None,
) -> list[SessionInfo]:
    """List active, non-expired, non-revoked sessions for current owner."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(OwnerSession)
        .where(
            OwnerSession.owner_id == owner_id,
            OwnerSession.revoked_at.is_(None),
            OwnerSession.expires_at > now,
        )
        .order_by(OwnerSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionInfo(
            id=s.id,
            created_at=_ensure_utc(s.created_at),
            expires_at=_ensure_utc(s.expires_at),
            is_current=(s.id == current_session_id),
        )
        for s in sessions
    ]


async def revoke_session(
    session: AsyncSession,
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    """Revoke specified session and invalidate associated refresh tokens."""
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()

    result = await session.execute(
        select(OwnerSession)
        .where(
            OwnerSession.id == session_id,
            OwnerSession.owner_id == owner_id,
        )
        .with_for_update()
    )
    owner_session = result.scalar_one_or_none()
    if owner_session is None:
        return False

    if owner_session.revoked_at is None:
        owner_session.revoked_at = now
        owner_session.revocation_reason = "revoked_by_owner"

    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.session_id == session_id,
            RefreshToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    await _log_audit(
        session,
        "AUTH",
        "revoke_session",
        decision="ALLOW",
        reason="revoked_by_owner",
        actor_id=owner_id,
        target_id=session_id,
        correlation_id=correlation_id,
    )

    return True


async def revoke_all_sessions(
    session: AsyncSession,
    owner_id: uuid.UUID,
    include_current: bool = False,
    current_session_id: uuid.UUID | None = None,
) -> int:
    """Revoke all active sessions (or all other sessions) for the owner."""
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()

    stmt = (
        select(OwnerSession)
        .where(
            OwnerSession.owner_id == owner_id,
            OwnerSession.revoked_at.is_(None),
            OwnerSession.expires_at > now,
        )
        .with_for_update()
    )
    if not include_current and current_session_id is not None:
        stmt = stmt.where(OwnerSession.id != current_session_id)

    result = await session.execute(stmt)
    sessions_to_revoke = list(result.scalars().all())

    if not sessions_to_revoke:
        return 0

    session_ids = [s.id for s in sessions_to_revoke]
    for s in sessions_to_revoke:
        s.revoked_at = now
        s.revocation_reason = "revoked_by_owner"

    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.session_id.in_(session_ids),
            RefreshToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    await _log_audit(
        session,
        "AUTH",
        "revoke_all_sessions",
        decision="ALLOW",
        reason=f"revoked_{len(sessions_to_revoke)}_sessions",
        actor_id=owner_id,
        correlation_id=correlation_id,
    )

    return len(sessions_to_revoke)


async def get_owner_profile(
    session: AsyncSession,
    owner_id: uuid.UUID,
) -> OwnerProfile:
    """Get owner profile. Never returns password_hash."""
    result = await session.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise AuthenticationError("owner_not_found")

    return OwnerProfile(
        id=owner.id,
        email=owner.email,
        status=owner.status,
        created_at=owner.created_at,
        last_login_at=owner.last_login_at,
    )
