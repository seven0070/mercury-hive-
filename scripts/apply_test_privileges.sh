#!/bin/sh
set -eu

echo "=== Applying test runtime privileges (Phase 2 Hardened) ==="

psql --set=ON_ERROR_STOP=1 <<'SQL'
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mercury_test_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mercury_test_runtime;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM mercury_test_runtime;

GRANT SELECT (id, email, password_hash, status, created_at, last_login_at)
  ON owners TO mercury_test_runtime;
GRANT UPDATE (last_login_at) ON owners TO mercury_test_runtime;

GRANT SELECT ON owner_sessions TO mercury_test_runtime;
GRANT INSERT (id, owner_id, expires_at) ON owner_sessions TO mercury_test_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON owner_sessions TO mercury_test_runtime;

GRANT SELECT ON refresh_tokens TO mercury_test_runtime;
GRANT INSERT (id, session_id, token_hash, expires_at) ON refresh_tokens TO mercury_test_runtime;
GRANT UPDATE (used_at) ON refresh_tokens TO mercury_test_runtime;

-- Phase 2 Tamper-Proof Audit
GRANT SELECT ON audit_events TO mercury_test_runtime;
GRANT EXECUTE ON FUNCTION fn_record_audit_event TO mercury_test_runtime;

-- Phase 2 Governance
GRANT SELECT ON system_states TO mercury_test_runtime;
GRANT UPDATE (run_state, shutdown_reason, updated_by, updated_at) ON system_states TO mercury_test_runtime;

GRANT SELECT ON constitution_records TO mercury_test_runtime;

GRANT SELECT ON approvals TO mercury_test_runtime;
GRANT INSERT (id, action_type, requested_by, task_id, target_id, risk_level, status, reason) ON approvals TO mercury_test_runtime;
GRANT UPDATE (status, decision, decided_by, reason, decided_at) ON approvals TO mercury_test_runtime;

GRANT SELECT ON budgets TO mercury_test_runtime;

GRANT SELECT ON alembic_version TO mercury_test_runtime;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_test_runtime;
SQL

echo "Test privileges applied (Phase 2)."
