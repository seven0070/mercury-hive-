export type SystemRunState = 'NORMAL' | 'DEGRADED' | 'EMERGENCY_SHUTDOWN';

export type AgentRole =
  | 'OWNER'
  | 'CEO'
  | 'DIGITAL_HR'
  | 'DEPARTMENT_MANAGER'
  | 'WORKER'
  | 'TEMPORARY_SUBAGENT';

export type AgentStatus = 'ACTIVE' | 'SUSPENDED' | 'TERMINATED';

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type EvolutionType =
  | 'SYSTEM_PROMPT'
  | 'TOOL_DEFINITION'
  | 'WORKFLOW_PIPELINE'
  | 'POLICY_RULE';

export type EvolutionStatus =
  | 'PROPOSED'
  | 'SANDBOX_TESTING'
  | 'SHADOW_DEPLOYED'
  | 'APPROVED_FOR_PROMOTION'
  | 'PROMOTED'
  | 'REJECTED'
  | 'ROLLED_BACK';

export interface OwnerConsoleSummary {
  system_run_state: SystemRunState;
  shutdown_reason: string | null;
  pending_approvals_count: number;
  active_agents_count: number;
  suspended_agents_count: number;
  departments_count: number;
  active_tasks_count: number;
  active_bridges_count: number;
  evolution_candidates_count: number;
  recent_audit_count: number;
  constitution_policy_version: number;
  constitution_hash: string;
}

export interface Department {
  id: string;
  name: string;
  purpose: string;
  status: 'ACTIVE' | 'ARCHIVED';
  data_classification: string;
  budget: number;
  manager_id?: string | null;
}

export interface Agent {
  id: string;
  display_name: string;
  role: AgentRole;
  department_id: string;
  status: AgentStatus;
  system_prompt_version: string;
  created_at: string;
  suspended_at?: string | null;
  terminated_at?: string | null;
}

export interface Approval {
  id: string;
  action_type: string;
  requested_by: string;
  task_id?: string | null;
  target_id?: string | null;
  risk_level: RiskLevel;
  status: ApprovalStatus;
  decision?: string | null;
  decided_by?: string | null;
  reason?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  actor_id?: string | null;
  actor_role?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  action: string;
  decision?: string | null;
  reason?: string | null;
  payload?: Record<string, any> | null;
  timestamp: string;
}

export interface EvolutionCandidate {
  id: string;
  title: string;
  evolution_type: EvolutionType;
  target_identifier: string;
  proposed_change: Record<string, any>;
  status: EvolutionStatus;
  proposer_agent_id: string;
  benchmark_results?: Record<string, any> | null;
  shadow_traffic_percentage: number;
  created_at: string;
  approved_by?: string | null;
  promoted_at?: string | null;
  reverted_at?: string | null;
  reversion_reason?: string | null;
}
