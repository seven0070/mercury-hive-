# Authentication

## Overview

Mercury Hive uses a single-owner authentication model with:
- Argon2id password hashing
- Short-lived JWT access tokens (5 minutes)
- Opaque refresh tokens with SHA-256 digest storage (24 hours)
- 7-day absolute sessions
- Refresh token rotation with replay detection

## Token Lifecycle

```
Login → Access Token (5 min) + Refresh Token (24h)
  │
  └─ Refresh → New Access + New Refresh (old marked used)
       │
       └─ Replay old token → ENTIRE SESSION REVOKED
```

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| /auth/login | POST | None | Email + password login |
| /auth/refresh | POST | Refresh token (body) | Token rotation |
| /auth/logout | POST | Access token (Bearer) | Revoke session |
| /auth/me | GET | Access token (Bearer) | Owner profile |

## Security Properties

- No signup endpoint (owner created via admin bootstrap)
- All auth failures return generic 401
- Passwords never in logs, errors, or responses
- Refresh tokens stored as SHA-256 digests only
- Session cannot be extended past 7-day absolute expiry
- Replay detection revokes the entire session
- Row-level locking prevents concurrent refresh races

## Password Policy

- Minimum: 16 characters
- Maximum: 128 characters
- No composition rules
