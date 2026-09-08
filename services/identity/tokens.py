"""JWT access token creation and validation.

Access tokens: 5-minute signed JWTs with standard claims.
Refresh tokens: opaque random values — NOT JWTs. Stored as SHA-256 digests.

Never log or return token values in error responses.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt


class TokenError(Exception):
    """Raised for any token validation failure.

    The error message is for internal logging only.
    Never return it to the client.
    """


@dataclass(frozen=True)
class AccessTokenClaims:
    """Validated access token claims."""

    sub: uuid.UUID  # Owner ID or Agent ID
    sid: uuid.UUID  # Session ID
    jti: uuid.UUID  # Token ID
    token_type: str  # Must be "access"
    iat: datetime
    nbf: datetime
    exp: datetime
    iss: str
    aud: str
    role: str = "OWNER"
    department_id: uuid.UUID | None = None


def create_access_token(
    owner_id: uuid.UUID,
    session_id: uuid.UUID,
    secret_key: str,
    algorithm: str = "HS256",
    issuer: str = "mercury-hive",
    audience: str = "mercury-hive-api",
    expires_minutes: int = 5,
    role: str = "OWNER",
    department_id: uuid.UUID | None = None,
) -> str:
    """Create a signed JWT access token.

    Claims include: sub, sid, jti, type, iat, nbf, exp, iss, aud, role, department_id.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(owner_id),
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "role": role,
        "department_id": str(department_id) if department_id else None,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_agent_token(
    agent_id: uuid.UUID,
    role: str,
    secret_key: str,
    department_id: uuid.UUID | None = None,
    algorithm: str = "HS256",
    issuer: str = "mercury-hive",
    audience: str = "mercury-hive-api",
    expires_minutes: int = 15,
) -> str:
    """Create a signed JWT access token for an authenticated internal AI Agent."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(agent_id),
        "sid": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "role": role,
        "department_id": str(department_id) if department_id else None,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def validate_access_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
    issuer: str = "mercury-hive",
    audience: str = "mercury-hive-api",
) -> AccessTokenClaims:
    """Validate and decode a JWT access token.

    Raises TokenError for any validation failure.
    Error messages are for internal logging — never return to client.
    """
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            issuer=issuer,
            audience=audience,
            options={
                "require": ["sub", "sid", "jti", "type", "iat", "nbf", "exp", "iss", "aud"],
            },
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token_expired") from e
    except jwt.InvalidIssuerError as e:
        raise TokenError("invalid_issuer") from e
    except jwt.InvalidAudienceError as e:
        raise TokenError("invalid_audience") from e
    except jwt.InvalidAlgorithmError as e:
        raise TokenError("invalid_algorithm") from e
    except jwt.MissingRequiredClaimError as e:
        raise TokenError(f"missing_claim: {e}") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid_token: {e}") from e

    # Validate token type
    if payload.get("type") != "access":
        raise TokenError("invalid_token_type")

    # Validate UUID format of critical claims
    try:
        sub = uuid.UUID(payload["sub"])
        sid = uuid.UUID(payload["sid"])
        jti = uuid.UUID(payload["jti"])
    except (ValueError, KeyError) as e:
        raise TokenError(f"invalid_uuid_claim: {e}") from e

    role = payload.get("role", "OWNER")
    dept_raw = payload.get("department_id")
    dept_id = None
    if dept_raw:
        try:
            dept_id = uuid.UUID(dept_raw)
        except ValueError:
            dept_id = None

    return AccessTokenClaims(
        sub=sub,
        sid=sid,
        jti=jti,
        token_type="access",
        iat=datetime.fromtimestamp(payload["iat"], tz=UTC),
        nbf=datetime.fromtimestamp(payload["nbf"], tz=UTC),
        exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
        iss=payload["iss"],
        aud=payload["aud"],
        role=role,
        department_id=dept_id,
    )


def generate_refresh_token() -> str:
    """Generate a cryptographically random opaque refresh token.

    Returns a 64-character hex string (32 random bytes).
    """
    return secrets.token_hex(32)


def hash_refresh_token(token: str) -> str:
    """Compute SHA-256 hex digest of a refresh token for database storage.

    The raw token is never stored — only this digest.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
