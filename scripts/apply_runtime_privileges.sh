#!/bin/sh
set -eu

echo "=== Applying runtime privileges ==="

psql --set=ON_ERROR_STOP=1 <<'SQL'

-- Revoke all defaults from runtime role
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mercury_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mercury_runtime;

-- ============================================================
-- owners: narrow column-level grants
-- ============================================================
-- SELECT: includes password_hash for argon2id verification during login
GRANT SELECT (id, email, password_hash, status, created_at, last_login_at)
  ON owners TO mercury_runtime;
-- UPDATE: only last_login_at
GRANT UPDATE (last_login_at) ON owners TO mercury_runtime;
-- No INSERT (owner created via admin bootstrap only)
-- No DELETE

-- ============================================================
-- owner_sessions: auth session operations
-- No created_at in INSERT — server default used
-- ============================================================
GRANT SELECT ON owner_sessions TO mercury_runtime;
GRANT INSERT (id, owner_id, expires_at) ON owner_sessions TO mercury_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON owner_sessions TO mercury_runtime;
-- No DELETE

-- ============================================================
-- refresh_tokens: rotation operations
-- No created_at in INSERT — server default used
-- ============================================================
GRANT SELECT ON refresh_tokens TO mercury_runtime;
GRANT INSERT (id, session_id, token_hash, expires_at) ON refresh_tokens TO mercury_runtime;
GRANT UPDATE (used_at) ON refresh_tokens TO mercury_runtime;
-- No DELETE

-- ============================================================
-- audit_events: insert + read
-- Phase 1 limitation: runtime INSERT is non-trustworthy.
-- Phase 2 adds write-through DB function + separate roles.
-- ============================================================
GRANT SELECT ON audit_events TO mercury_runtime;
GRANT INSERT ON audit_events TO mercury_runtime;
-- No UPDATE, no DELETE

-- ============================================================
-- alembic_version: read-only for runtime
-- ============================================================
GRANT SELECT ON alembic_version TO mercury_runtime;

-- Sequences for INSERT operations
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_runtime;

SQL

echo "Runtime privileges applied successfully."
