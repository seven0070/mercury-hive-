import React from 'react';
import { OwnerConsoleSummary } from '../types';

interface OverviewDashboardProps {
  summary: OwnerConsoleSummary | null;
}

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({ summary }) => {
  if (!summary) {
    return <div className="panel">Loading operational telemetry...</div>;
  }

  const metrics = [
    {
      label: 'Pending Approvals',
      value: summary.pending_approvals_count,
      foot: 'Awaiting human authorization',
      color: summary.pending_approvals_count > 0 ? '#f59e0b' : '#10b981',
    },
    {
      label: 'Active AI Agents',
      value: summary.active_agents_count,
      foot: `${summary.suspended_agents_count} suspended`,
      color: '#06b6d4',
    },
    {
      label: 'Seeded Departments',
      value: summary.departments_count,
      foot: 'Bounded organizational units',
      color: '#a855f7',
    },
    {
      label: 'Active Missions & Tasks',
      value: summary.active_tasks_count,
      foot: 'In progress or assigned',
      color: '#38bdf8',
    },
    {
      label: 'Cross-Dept Bridges',
      value: summary.active_bridges_count,
      foot: 'Governed permission channels',
      color: '#10b981',
    },
    {
      label: 'Evolution Candidates',
      value: summary.evolution_candidates_count,
      foot: 'Sandbox & shadow mutations',
      color: '#ec4899',
    },
    {
      label: 'Immutable Audit Trail',
      value: summary.recent_audit_count,
      foot: 'Total recorded security events',
      color: '#cbd5e1',
    },
    {
      label: 'Constitutional Hash',
      value: `v${summary.constitution_policy_version}`,
      foot: summary.constitution_hash ? summary.constitution_hash.slice(0, 16) : 'N/A',
      color: '#6366f1',
    },
  ];

  return (
    <div>
      <div className="metric-grid">
        {metrics.map((m, idx) => (
          <div key={idx} className="metric-card">
            <div className="metric-label">{m.label}</div>
            <div className="metric-value" style={{ color: m.color }}>
              {m.value}
            </div>
            <div className="metric-foot mono">{m.foot}</div>
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">System Invariants & Governance State</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', fontSize: '0.875rem' }}>
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <strong style={{ color: 'var(--accent-cyan)' }}>Single Sovereign Owner:</strong>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Enforced by PostgreSQL singleton boolean constraint. No additional humans can be added.
            </p>
          </div>
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <strong style={{ color: 'var(--accent-emerald)' }}>Tamper-Proof Audit Trail:</strong>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Write-through function with direct DML revoked. Dual-transaction guarantees persisted evidence.
            </p>
          </div>
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <strong style={{ color: 'var(--accent-amber)' }}>Deny-by-Default Execution:</strong>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              All actions require verified permission grants. Self-escalation and authority modification strictly blocked.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
