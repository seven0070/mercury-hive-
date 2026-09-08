#!/bin/sh
set -eu

echo "=== Applying test runtime privileges (Phase 3) ==="

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

GRANT SELECT ON audit_events TO mercury_test_runtime;
GRANT EXECUTE ON FUNCTION fn_record_audit_event TO mercury_test_runtime;

GRANT SELECT ON system_states TO mercury_test_runtime;
GRANT UPDATE (run_state, shutdown_reason, updated_by, updated_at) ON system_states TO mercury_test_runtime;

GRANT SELECT ON constitution_records TO mercury_test_runtime;

GRANT SELECT ON approvals TO mercury_test_runtime;
GRANT INSERT (id, action_type, requested_by, task_id, target_id, risk_level, status, reason) ON approvals TO mercury_test_runtime;
GRANT UPDATE (status, decision, decided_by, reason, decided_at) ON approvals TO mercury_test_runtime;

GRANT SELECT ON budgets TO mercury_test_runtime;

GRANT SELECT ON departments TO mercury_test_runtime;
GRANT INSERT (id, name, purpose, status, data_classification, budget, workspace_metadata) ON departments TO mercury_test_runtime;
GRANT UPDATE (purpose, status, manager_id, hr_owner_id, budget, workspace_metadata) ON departments TO mercury_test_runtime;

GRANT SELECT ON agents TO mercury_test_runtime;
GRANT INSERT (id, display_name, role, department_id, manager_id, status, persona_source, persona_disclosure, system_prompt_version, avatar_profile_id, parent_agent_id) ON agents TO mercury_test_runtime;
GRANT UPDATE (display_name, status, persona_disclosure, system_prompt_version, suspended_at, terminated_at, termination_reason) ON agents TO mercury_test_runtime;

GRANT SELECT ON permission_grants TO mercury_test_runtime;
GRANT INSERT (id, agent_id, task_id, department_id, allowed_actions, allowed_tools, memory_scopes, budget_limit, expires_at, approval_requirements, issued_by) ON permission_grants TO mercury_test_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON permission_grants TO mercury_test_runtime;

GRANT SELECT ON alembic_version TO mercury_test_runtime;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_test_runtime;
SQL

echo "Test privileges applied (Phase 3)."
