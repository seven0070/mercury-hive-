#!/bin/sh
set -eu

echo "=== Applying runtime privileges (Phase 3) ==="

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
-- ============================================================
GRANT SELECT ON audit_events TO mercury_runtime;
GRANT EXECUTE ON FUNCTION fn_record_audit_event TO mercury_runtime;

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
-- departments: Phase 3 department workspaces
-- ============================================================
GRANT SELECT ON departments TO mercury_runtime;
GRANT INSERT (id, name, purpose, status, data_classification, budget, workspace_metadata) ON departments TO mercury_runtime;
GRANT UPDATE (purpose, status, manager_id, hr_owner_id, budget, workspace_metadata) ON departments TO mercury_runtime;

-- ============================================================
-- agents: Phase 3 agent registry & lifecycle
-- ============================================================
GRANT SELECT ON agents TO mercury_runtime;
GRANT INSERT (id, display_name, role, department_id, manager_id, status, persona_source, persona_disclosure, system_prompt_version, avatar_profile_id, parent_agent_id) ON agents TO mercury_runtime;
GRANT UPDATE (display_name, status, persona_disclosure, system_prompt_version, suspended_at, terminated_at, termination_reason) ON agents TO mercury_runtime;

-- ============================================================
-- permission_grants: Phase 3 scoped authority
-- ============================================================
GRANT SELECT ON permission_grants TO mercury_runtime;
GRANT INSERT (id, agent_id, task_id, department_id, allowed_actions, allowed_tools, memory_scopes, budget_limit, expires_at, approval_requirements, issued_by) ON permission_grants TO mercury_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON permission_grants TO mercury_runtime;

-- ============================================================
-- tasks: Phase 4 task & mission engine
-- ============================================================
GRANT SELECT ON tasks TO mercury_runtime;
GRANT INSERT (id, title, description, priority, status, origin_department_id, assigned_department_id, assigned_agent_id, created_by, parent_task_id, required_capabilities, input_artifacts, output_artifacts, budget_allocated, budget_spent, deadline) ON tasks TO mercury_runtime;
GRANT UPDATE (title, description, priority, status, assigned_agent_id, required_capabilities, input_artifacts, output_artifacts, budget_allocated, budget_spent, deadline, completed_at, updated_at) ON tasks TO mercury_runtime;

-- ============================================================
-- cross_department_bridges: Phase 4 inter-department bridges
-- ============================================================
GRANT SELECT ON cross_department_bridges TO mercury_runtime;
GRANT INSERT (id, source_department_id, target_department_id, purpose, status, allowed_data_classification, data_sharing_scopes, requested_by, approved_by, expires_at) ON cross_department_bridges TO mercury_runtime;
GRANT UPDATE (status, approved_by, revoked_at, revocation_reason) ON cross_department_bridges TO mercury_runtime;

-- ============================================================
-- task_delegations: Phase 4 task handoff tracking
-- ============================================================
GRANT SELECT ON task_delegations TO mercury_runtime;
GRANT INSERT (id, task_id, bridge_id, delegated_from_agent_id, delegated_to_agent_id, notes) ON task_delegations TO mercury_runtime;

-- ============================================================
-- tool_definitions: Phase 5 tool catalog
-- ============================================================
GRANT SELECT ON tool_definitions TO mercury_runtime;
GRANT INSERT (id, name, description, risk_level, schema_definition, is_enabled, requires_approval) ON tool_definitions TO mercury_runtime;
GRANT UPDATE (description, risk_level, schema_definition, is_enabled, requires_approval) ON tool_definitions TO mercury_runtime;

-- ============================================================
-- tool_executions: Phase 5 audited tool execution logs
-- ============================================================
GRANT SELECT ON tool_executions TO mercury_runtime;
GRANT INSERT (id, tool_name, agent_id, task_id, status, parameters, result, error_message, execution_duration_ms) ON tool_executions TO mercury_runtime;

-- ============================================================
-- agent_memories: Phase 5 scoped memory
-- ============================================================
GRANT SELECT ON agent_memories TO mercury_runtime;
GRANT INSERT (id, agent_id, scope, scope_id, key, value, data_classification, version) ON agent_memories TO mercury_runtime;
GRANT UPDATE (value, data_classification, version, updated_at) ON agent_memories TO mercury_runtime;

-- ============================================================
-- rollback_artifacts: Phase 5 reversible actions
-- ============================================================
GRANT SELECT ON rollback_artifacts TO mercury_runtime;
GRANT INSERT (id, task_id, agent_id, tool_name, target_resource, previous_state, new_state, status) ON rollback_artifacts TO mercury_runtime;
GRANT UPDATE (status, reverted_at, reverted_by) ON rollback_artifacts TO mercury_runtime;

-- ============================================================
-- rubrics: Phase 6 grading rubrics
-- ============================================================
GRANT SELECT ON rubrics TO mercury_runtime;
GRANT INSERT (id, name, version, description, criteria, minimum_passing_score, is_active) ON rubrics TO mercury_runtime;
GRANT UPDATE (description, criteria, minimum_passing_score, is_active) ON rubrics TO mercury_runtime;

-- ============================================================
-- evaluation_submissions: Phase 6 deliverable submissions
-- ============================================================
GRANT SELECT ON evaluation_submissions TO mercury_runtime;
GRANT INSERT (id, task_id, author_agent_id, title, deliverable_payload) ON evaluation_submissions TO mercury_runtime;

-- ============================================================
-- judging_sessions: Phase 6 council sessions
-- ============================================================
GRANT SELECT ON judging_sessions TO mercury_runtime;
GRANT INSERT (id, submission_id, rubric_id, status, required_judges, final_verdict, aggregate_score, consensus_notes) ON judging_sessions TO mercury_runtime;
GRANT UPDATE (status, final_verdict, aggregate_score, consensus_notes, closed_at) ON judging_sessions TO mercury_runtime;

-- ============================================================
-- judge_scorecards: Phase 6 independent judge grading
-- ============================================================
GRANT SELECT ON judge_scorecards TO mercury_runtime;
GRANT INSERT (id, session_id, judge_agent_id, scores, total_score, verdict, feedback, conflict_declared, conflict_reason) ON judge_scorecards TO mercury_runtime;

-- ============================================================
-- alembic_version: read-only for runtime
-- ============================================================
GRANT SELECT ON alembic_version TO mercury_runtime;

-- Sequences for INSERT operations
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_runtime;

SQL

echo "Runtime privileges applied successfully (Phase 6)."
