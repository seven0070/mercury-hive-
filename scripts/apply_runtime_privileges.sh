#!/bin/sh
set -eu

echo "=== Applying runtime privileges (Phase 2 Hardened) ==="

psql --set=ON_ERROR_STOP=1 <<'SQL'

-- Revoke all defaults from runtime role
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mercury_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mercury_runtime;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM mercury_runtime;

-- ============================================================
-- owners: narrow column-level grants
-- ============================================================
GRANT SELECT (id, email, password_hash, status, created_at, last_login_at)
  ON owners TO mercury_runtime;
GRANT UPDATE (last_login_at) ON owners TO mercury_runtime;

-- ============================================================
-- owner_sessions: auth session operations
-- ============================================================
GRANT SELECT ON owner_sessions TO mercury_runtime;
GRANT INSERT (id, owner_id, expires_at) ON owner_sessions TO mercury_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON owner_sessions TO mercury_runtime;

-- ============================================================
-- refresh_tokens: rotation operations
-- ============================================================
GRANT SELECT ON refresh_tokens TO mercury_runtime;
GRANT INSERT (id, session_id, token_hash, expires_at) ON refresh_tokens TO mercury_runtime;
GRANT UPDATE (used_at) ON refresh_tokens TO mercury_runtime;

-- ============================================================
-- audit_events: Phase 2 Tamper-Proof Hardening
-- Direct INSERT revoked. Insertion strictly via SECURITY DEFINER function.
-- ============================================================
GRANT SELECT ON audit_events TO mercury_runtime;
GRANT EXECUTE ON FUNCTION fn_record_audit_event TO mercury_runtime;
-- No direct INSERT, no UPDATE, no DELETE on audit_events

-- ============================================================
-- system_states: emergency shutdown controls
-- ============================================================
GRANT SELECT ON system_states TO mercury_runtime;
GRANT UPDATE (run_state, shutdown_reason, updated_by, updated_at) ON system_states TO mercury_runtime;

-- ============================================================
-- constitution_records: read-only for verification
-- ============================================================
GRANT SELECT ON constitution_records TO mercury_runtime;

-- ============================================================
-- approvals: creation, review, and decision recording
-- ============================================================
GRANT SELECT ON approvals TO mercury_runtime;
GRANT INSERT (id, action_type, requested_by, task_id, target_id, risk_level, status, reason) ON approvals TO mercury_runtime;
GRANT UPDATE (status, decision, decided_by, reason, decided_at) ON approvals TO mercury_runtime;

-- ============================================================
-- budgets: read-only budget tracking
-- ============================================================
GRANT SELECT ON budgets TO mercury_runtime;

-- ============================================================
-- alembic_version: read-only for runtime
-- ============================================================
GRANT SELECT ON alembic_version TO mercury_runtime;

-- Sequences for INSERT operations
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_runtime;

SQL

echo "Runtime privileges applied successfully (Phase 2)."
