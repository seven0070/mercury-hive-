#!/bin/sh
set -eu

echo "=== Applying test runtime privileges ==="

psql --set=ON_ERROR_STOP=1 <<'SQL'
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mercury_test_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mercury_test_runtime;

GRANT SELECT (id, email, password_hash, status, created_at, last_login_at)
  ON owners TO mercury_test_runtime;
GRANT UPDATE (last_login_at) ON owners TO mercury_test_runtime;

GRANT SELECT ON owner_sessions TO mercury_test_runtime;
GRANT INSERT (id, owner_id, expires_at) ON owner_sessions TO mercury_test_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON owner_sessions TO mercury_test_runtime;

GRANT SELECT ON refresh_tokens TO mercury_test_runtime;
GRANT INSERT (id, session_id, token_hash, expires_at) ON refresh_tokens TO mercury_test_runtime;
GRANT UPDATE (used_at) ON refresh_tokens TO mercury_test_runtime;

GRANT SELECT ON audit_events TO mercury_test_runtime;
GRANT INSERT ON audit_events TO mercury_test_runtime;

GRANT SELECT ON alembic_version TO mercury_test_runtime;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_test_runtime;
SQL

echo "Test privileges applied."
