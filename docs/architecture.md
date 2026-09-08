# Mercury Hive Architecture

## Overview

Mercury Hive is a governed virtual AI company operated by one human system owner.
The system enforces a strict hierarchy: Owner → CEO → HR → Managers → Workers → Sub-Agents.

## Phase 1 Architecture

```
┌─────────────────────────────────────────────────┐
│                  Client                          │
│              (curl / httpx)                       │
└──────────────────┬──────────────────────────────┘
                   │ HTTPS (future)
┌──────────────────▼──────────────────────────────┐
│              FastAPI + Uvicorn                    │
│  ┌──────────────────────────────────────────┐     │
│  │ /auth/login  /auth/refresh  /auth/logout │     │
│  │ /auth/me     /health/live  /health/ready │     │
│  └──────────────────────────────────────────┘     │
│  ┌──────────────────────────────────────────┐     │
│  │         Identity Service                 │     │
│  │  Argon2id │ JWT │ Session │ Refresh      │     │
│  └──────────────────────────────────────────┘     │
│  ┌──────────────────────────────────────────┐     │
│  │      Permission Engine (deny-by-default) │     │
│  └──────────────────────────────────────────┘     │
│  ┌──────────────────────────────────────────┐     │
│  │      Audit Service (dual-transaction)    │     │
│  └──────────────────────────────────────────┘     │
│  ┌──────────────────────────────────────────┐     │
│  │      Constitution Loader (fail-closed)   │     │
│  └──────────────────────────────────────────┘     │
└──────────────────┬──────────────────────────────┘
                   │ asyncpg
┌──────────────────▼──────────────────────────────┐
│            PostgreSQL 16                          │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐          │
│  │ owners  │ │ sessions │ │ refresh   │          │
│  │         │ │          │ │ tokens    │          │
│  └─────────┘ └──────────┘ └───────────┘          │
│  ┌──────────────────────────────────────────┐     │
│  │            audit_events                  │     │
│  └──────────────────────────────────────────┘     │
│  Column-level GRANT: mercury_runtime role         │
└─────────────────────────────────────────────────┘
```

## Security Boundaries

| Role | Can Do | Cannot Do |
|------|--------|-----------|
| mercury_admin | DDL, migrations, bootstrap | Used only by admin service |
| mercury_runtime | SELECT/INSERT/UPDATE on allowed columns | DDL, DELETE, update sensitive columns |

## Key Design Decisions

1. **Deny by default**: All access must be explicitly granted
2. **Fail closed**: Missing constitution prevents startup
3. **Generic errors**: Auth failures always return 401
4. **Separate transactions**: Failed-auth audit events survive rollback
5. **Column-level grants**: DB enforces immutability of sensitive fields
6. **Forward-only migrations**: No rollback without explicit action
