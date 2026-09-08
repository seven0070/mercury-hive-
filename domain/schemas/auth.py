"""Pydantic v2 schemas for authentication endpoints.

Never include passwords, tokens, or sensitive data in response schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Owner login request."""

    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Authentication token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    """Refresh token rotation request."""

    refresh_token: str = Field(..., min_length=1)


class OwnerProfile(BaseModel):
    """Owner profile response. Never includes password_hash."""

    id: uuid.UUID
    email: str
    status: str
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class AuthError(BaseModel):
    """Generic authentication error. Never reveals internal reason."""

    detail: str = "Invalid credentials"
