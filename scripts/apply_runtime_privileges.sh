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
GRANT SELECT (id, singleton, email, password_hash, status, created_at, last_login_at)
  ON owners TO mercury_runtime;
GRANT UPDATE (last_login_at) ON owners TO mercury_runtime;

-- ============================================================
-- owner_sessions: auth session operations
-- ============================================================
GRANT SELECT ON owner_sessions TO mercury_runtime;
GRANT INSERT (id, owner_id, created_at, expires_at, revoked_at, revocation_reason) ON owner_sessions TO mercury_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON owner_sessions TO mercury_runtime;

-- ============================================================
-- refresh_tokens: rotation operations
-- ============================================================
GRANT SELECT ON refresh_tokens TO mercury_runtime;
GRANT INSERT (id, session_id, token_hash, created_at, expires_at, used_at) ON refresh_tokens TO mercury_runtime;
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
GRANT INSERT (id, action_type, requested_by, task_id, target_id, risk_level, status, decision, decided_by, reason, created_at, decided_at) ON approvals TO mercury_runtime;
GRANT UPDATE (status, decision, decided_by, reason, decided_at) ON approvals TO mercury_runtime;

-- ============================================================
-- budgets: read-only budget tracking
-- ============================================================
GRANT SELECT ON budgets TO mercury_runtime;
GRANT INSERT (id, department_id, allocated_amount, spent_amount, currency, reset_period, created_at, updated_at) ON budgets TO mercury_runtime;
GRANT UPDATE (allocated_amount, spent_amount, reset_period, updated_at) ON budgets TO mercury_runtime;

-- ============================================================
-- departments: Phase 3 department workspaces
-- ============================================================
GRANT SELECT ON departments TO mercury_runtime;
GRANT INSERT (id, name, purpose, status, manager_id, hr_owner_id, data_classification, budget, workspace_metadata, created_at) ON departments TO mercury_runtime;
GRANT UPDATE (purpose, status, manager_id, hr_owner_id, budget, workspace_metadata) ON departments TO mercury_runtime;

-- ============================================================
-- agents: Phase 3 agent registry & lifecycle
-- ============================================================
GRANT SELECT ON agents TO mercury_runtime;
GRANT INSERT (id, display_name, role, department_id, manager_id, status, persona_source, persona_disclosure, system_prompt_version, avatar_profile_id, parent_agent_id, created_at, suspended_at, terminated_at, termination_reason) ON agents TO mercury_runtime;
GRANT UPDATE (display_name, status, persona_disclosure, system_prompt_version, suspended_at, terminated_at, termination_reason) ON agents TO mercury_runtime;

-- ============================================================
-- permission_grants: Phase 3 scoped authority
-- ============================================================
GRANT SELECT ON permission_grants TO mercury_runtime;
GRANT INSERT (id, agent_id, task_id, department_id, allowed_actions, allowed_tools, memory_scopes, budget_limit, expires_at, approval_requirements, issued_by, created_at, revoked_at, revocation_reason) ON permission_grants TO mercury_runtime;
GRANT UPDATE (revoked_at, revocation_reason) ON permission_grants TO mercury_runtime;

-- ============================================================
-- tasks: Phase 4 task & mission engine
-- ============================================================
GRANT SELECT ON tasks TO mercury_runtime;
GRANT INSERT (id, title, description, priority, status, origin_department_id, assigned_department_id, assigned_agent_id, created_by, parent_task_id, required_capabilities, input_artifacts, output_artifacts, budget_allocated, budget_spent, deadline, created_at, updated_at, completed_at) ON tasks TO mercury_runtime;
GRANT UPDATE (title, description, priority, status, assigned_agent_id, required_capabilities, input_artifacts, output_artifacts, budget_allocated, budget_spent, deadline, completed_at, updated_at) ON tasks TO mercury_runtime;

-- ============================================================
-- cross_department_bridges: Phase 4 inter-department bridges
-- ============================================================
GRANT SELECT ON cross_department_bridges TO mercury_runtime;
GRANT INSERT (id, source_department_id, target_department_id, purpose, status, allowed_data_classification, data_sharing_scopes, requested_by, approved_by, expires_at, created_at, revoked_at, revocation_reason) ON cross_department_bridges TO mercury_runtime;
GRANT UPDATE (status, approved_by, revoked_at, revocation_reason) ON cross_department_bridges TO mercury_runtime;

-- ============================================================
-- task_delegations: Phase 4 task handoff tracking
-- ============================================================
GRANT SELECT ON task_delegations TO mercury_runtime;
GRANT INSERT (id, task_id, bridge_id, delegated_from_agent_id, delegated_to_agent_id, notes, created_at) ON task_delegations TO mercury_runtime;

-- ============================================================
-- tool_definitions: Phase 5 tool catalog
-- ============================================================
GRANT SELECT ON tool_definitions TO mercury_runtime;
GRANT INSERT (id, name, description, risk_level, schema_definition, is_enabled, requires_approval, created_at) ON tool_definitions TO mercury_runtime;
GRANT UPDATE (description, risk_level, schema_definition, is_enabled, requires_approval) ON tool_definitions TO mercury_runtime;

-- ============================================================
-- tool_executions: Phase 5 audited tool execution logs
-- ============================================================
GRANT SELECT ON tool_executions TO mercury_runtime;
GRANT INSERT (id, tool_name, agent_id, task_id, status, parameters, result, error_message, execution_duration_ms, created_at) ON tool_executions TO mercury_runtime;
GRANT UPDATE (status, result, error_message, execution_duration_ms) ON tool_executions TO mercury_runtime;

-- ============================================================
-- agent_memories: Phase 5 scoped memory
-- ============================================================
GRANT SELECT ON agent_memories TO mercury_runtime;
GRANT INSERT (id, agent_id, scope, scope_id, key, value, data_classification, version, created_at, updated_at) ON agent_memories TO mercury_runtime;
GRANT UPDATE (value, data_classification, version, updated_at) ON agent_memories TO mercury_runtime;

-- ============================================================
-- rollback_artifacts: Phase 5 reversible actions
-- ============================================================
GRANT SELECT ON rollback_artifacts TO mercury_runtime;
GRANT INSERT (id, task_id, agent_id, tool_name, target_resource, previous_state, new_state, status, created_at, reverted_at, reverted_by) ON rollback_artifacts TO mercury_runtime;
GRANT UPDATE (status, reverted_at, reverted_by) ON rollback_artifacts TO mercury_runtime;

-- ============================================================
-- rubrics: Phase 6 grading rubrics
-- ============================================================
GRANT SELECT ON rubrics TO mercury_runtime;
GRANT INSERT (id, name, version, description, criteria, minimum_passing_score, is_active, created_at) ON rubrics TO mercury_runtime;
GRANT UPDATE (description, criteria, minimum_passing_score, is_active) ON rubrics TO mercury_runtime;

-- ============================================================
-- evaluation_submissions: Phase 6 deliverable submissions
-- ============================================================
GRANT SELECT ON evaluation_submissions TO mercury_runtime;
GRANT INSERT (id, task_id, author_agent_id, title, deliverable_payload, submitted_at) ON evaluation_submissions TO mercury_runtime;

-- ============================================================
-- judging_sessions: Phase 6 council sessions
-- ============================================================
GRANT SELECT ON judging_sessions TO mercury_runtime;
GRANT INSERT (id, submission_id, rubric_id, status, required_judges, final_verdict, aggregate_score, consensus_notes, created_at, closed_at) ON judging_sessions TO mercury_runtime;
GRANT UPDATE (status, final_verdict, aggregate_score, consensus_notes, closed_at) ON judging_sessions TO mercury_runtime;

-- ============================================================
-- judge_scorecards: Phase 6 independent judge grading
-- ============================================================
GRANT SELECT ON judge_scorecards TO mercury_runtime;
GRANT INSERT (id, session_id, judge_agent_id, scores, total_score, verdict, feedback, conflict_declared, conflict_reason, submitted_at) ON judge_scorecards TO mercury_runtime;

-- ============================================================
-- evolution_candidates: Phase 7 governed mutation proposals
-- ============================================================
GRANT SELECT ON evolution_candidates TO mercury_runtime;
GRANT INSERT (id, title, evolution_type, target_identifier, proposed_change, status, proposer_agent_id, benchmark_results, shadow_traffic_percentage, created_at, approved_by, promoted_at, reverted_at, reversion_reason) ON evolution_candidates TO mercury_runtime;
GRANT UPDATE (status, benchmark_results, shadow_traffic_percentage, approved_by, promoted_at, reverted_at, reversion_reason) ON evolution_candidates TO mercury_runtime;

-- ============================================================
-- sandbox_runs: Phase 7 isolated benchmarking
-- ============================================================
GRANT SELECT ON sandbox_runs TO mercury_runtime;
GRANT INSERT (id, candidate_id, test_suite_name, baseline_score, candidate_score, metrics, verdict, executed_at) ON sandbox_runs TO mercury_runtime;

-- ============================================================
-- tribe_mappings: Phase 8 squad & department mapping
-- ============================================================
GRANT SELECT ON tribe_mappings TO mercury_runtime;
GRANT INSERT (id, department_id, tribe_name, squad_name, external_team_id, sync_status, created_at, updated_at) ON tribe_mappings TO mercury_runtime;
GRANT UPDATE (tribe_name, squad_name, external_team_id, sync_status, updated_at) ON tribe_mappings TO mercury_runtime;

-- ============================================================
-- agent_skills: Phase 8 capability matrix & certification
-- ============================================================
GRANT SELECT ON agent_skills TO mercury_runtime;
GRANT INSERT (id, agent_id, skill_name, proficiency_level, is_verified, verified_by, created_at) ON agent_skills TO mercury_runtime;
GRANT UPDATE (proficiency_level, is_verified, verified_by) ON agent_skills TO mercury_runtime;

-- ============================================================
-- task_sync_mappings: Phase 8 external task synchronization
-- ============================================================
GRANT SELECT ON task_sync_mappings TO mercury_runtime;
GRANT INSERT (id, task_id, external_system, external_task_id, sync_direction, sync_status, last_synced_at) ON task_sync_mappings TO mercury_runtime;
GRANT UPDATE (sync_direction, sync_status, last_synced_at) ON task_sync_mappings TO mercury_runtime;

-- ============================================================
-- workspace_zones: Phase 10 3D spatial office pods & rooms
-- ============================================================
GRANT SELECT ON workspace_zones TO mercury_runtime;
GRANT INSERT (id, name, zone_type, department_id, capacity, security_level, spatial_bounds, is_active, created_at) ON workspace_zones TO mercury_runtime;
GRANT UPDATE (name, capacity, security_level, spatial_bounds, is_active) ON workspace_zones TO mercury_runtime;

-- ============================================================
-- avatar_profiles: Phase 10 governed attire & avatar models
-- ============================================================
GRANT SELECT ON avatar_profiles TO mercury_runtime;
GRANT INSERT (id, agent_id, avatar_model_uri, attire_class, customization_payload, is_approved, approved_by, created_at, updated_at) ON avatar_profiles TO mercury_runtime;
GRANT UPDATE (avatar_model_uri, attire_class, customization_payload, is_approved, approved_by, updated_at) ON avatar_profiles TO mercury_runtime;

-- ============================================================
-- presence_sessions: Phase 10 3D presence telemetry & coords
-- ============================================================
GRANT SELECT ON presence_sessions TO mercury_runtime;
GRANT INSERT (id, entity_id, entity_type, zone_id, position_x, position_y, position_z, rotation_yaw, presence_state, current_task_id, last_heartbeat_at) ON presence_sessions TO mercury_runtime;
GRANT UPDATE (zone_id, position_x, position_y, position_z, rotation_yaw, presence_state, current_task_id, last_heartbeat_at) ON presence_sessions TO mercury_runtime;

-- ============================================================
-- virtual_meetings: Phase 10 boardroom conclaves & sessions
-- ============================================================
GRANT SELECT ON virtual_meetings TO mercury_runtime;
GRANT INSERT (id, title, zone_id, host_id, status, agenda, meeting_minutes, scheduled_start, started_at, ended_at) ON virtual_meetings TO mercury_runtime;
GRANT UPDATE (status, agenda, meeting_minutes, started_at, ended_at) ON virtual_meetings TO mercury_runtime;

-- ============================================================
-- meeting_participants: Phase 10 meeting attendees & roles
-- ============================================================
GRANT SELECT ON meeting_participants TO mercury_runtime;
GRANT INSERT (id, meeting_id, entity_id, role_in_meeting, joined_at, left_at) ON meeting_participants TO mercury_runtime;
GRANT UPDATE (left_at) ON meeting_participants TO mercury_runtime;

-- ============================================================
-- alembic_version: read-only for runtime
-- ============================================================
GRANT SELECT ON alembic_version TO mercury_runtime;

-- Sequences for INSERT operations
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mercury_runtime;

SQL

echo "Runtime privileges applied successfully (Phase 10)."
