import React, { useState } from 'react';
import { Agent, Department } from '../types';

interface AgentRegistryViewProps {
  departments: Department[];
  agents: Agent[];
  onSuspend: (agentId: string) => Promise<void>;
  onRestore: (agentId: string) => Promise<void>;
  onTerminate: (agentId: string, reason: string) => Promise<void>;
  onRefresh: () => void;
}

export const AgentRegistryView: React.FC<AgentRegistryViewProps> = ({
  departments,
  agents,
  onSuspend,
  onRestore,
  onTerminate,
  onRefresh,
}) => {
  const [selectedDept, setSelectedDept] = useState<string>('ALL');
  const [termAgentId, setTermAgentId] = useState<string | null>(null);
  const [termReason, setTermReason] = useState('');
  const [loading, setLoading] = useState(false);

  const filteredAgents =
    selectedDept === 'ALL'
      ? agents
      : agents.filter((a) => a.department_id === selectedDept);

  const getDeptName = (id: string) => {
    const d = departments.find((dept) => dept.id === id);
    return d ? d.name : id.slice(0, 8);
  };

  const handleTerminateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!termAgentId) return;
    setLoading(true);
    try {
      await onTerminate(termAgentId, termReason);
      setTermAgentId(null);
      setTermReason('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Termination failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">AI Workforce & Department Registry</h2>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Governed hierarchy: Owner → CEO → HR → Managers → Workers → Temporary Subagents
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <select
            className="input-field"
            style={{ margin: 0, padding: '0.35rem 0.75rem', width: 'auto' }}
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
          >
            <option value="ALL">All Departments ({departments.length})</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <button className="btn-sm btn-secondary" onClick={onRefresh}>
            Refresh
          </button>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Display Name</th>
            <th>Role</th>
            <th>Department</th>
            <th>Status</th>
            <th>Prompt Ver.</th>
            <th>Registered</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredAgents.length === 0 ? (
            <tr>
              <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                No agents registered in this scope.
              </td>
            </tr>
          ) : (
            filteredAgents.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.display_name}</strong>
                </td>
                <td>
                  <span
                    className="badge"
                    style={{
                      background:
                        a.role === 'CEO'
                          ? 'rgba(168, 85, 247, 0.2)'
                          : a.role === 'DIGITAL_HR'
                          ? 'rgba(236, 72, 153, 0.2)'
                          : a.role === 'DEPARTMENT_MANAGER'
                          ? 'rgba(6, 182, 212, 0.2)'
                          : 'rgba(100, 116, 139, 0.2)',
                      color:
                        a.role === 'CEO'
                          ? '#a855f7'
                          : a.role === 'DIGITAL_HR'
                          ? '#ec4899'
                          : a.role === 'DEPARTMENT_MANAGER'
                          ? '#06b6d4'
                          : '#94a3b8',
                    }}
                  >
                    {a.role}
                  </span>
                </td>
                <td>{getDeptName(a.department_id)}</td>
                <td>
                  <span
                    className="badge"
                    style={{
                      background:
                        a.status === 'ACTIVE'
                          ? 'rgba(16, 185, 129, 0.15)'
                          : a.status === 'SUSPENDED'
                          ? 'rgba(245, 158, 11, 0.15)'
                          : 'rgba(239, 68, 68, 0.15)',
                      color:
                        a.status === 'ACTIVE'
                          ? '#10b981'
                          : a.status === 'SUSPENDED'
                          ? '#f59e0b'
                          : '#ef4444',
                    }}
                  >
                    {a.status}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '0.8rem' }}>
                  {a.system_prompt_version}
                </td>
                <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {new Date(a.created_at).toLocaleDateString()}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {a.status === 'ACTIVE' && (
                      <button
                        className="btn-sm btn-secondary"
                        onClick={async () => {
                          await onSuspend(a.id);
                          onRefresh();
                        }}
                      >
                        Suspend
                      </button>
                    )}
                    {a.status === 'SUSPENDED' && (
                      <button
                        className="btn-sm btn-approve"
                        onClick={async () => {
                          await onRestore(a.id);
                          onRefresh();
                        }}
                      >
                        Restore
                      </button>
                    )}
                    {a.status !== 'TERMINATED' && (
                      <button
                        className="btn-sm btn-reject"
                        onClick={() => {
                          setTermAgentId(a.id);
                          setTermReason('Revoked by System Owner');
                        }}
                      >
                        Terminate
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {termAgentId && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 style={{ marginBottom: '1rem', color: '#ef4444' }}>
              Permanent Agent Termination
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Terminating an agent permanently revokes its identity. Per constitutional law, terminated agents CANNOT be restored.
            </p>
            <form onSubmit={handleTerminateSubmit}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Termination Justification
              </label>
              <textarea
                className="input-field"
                rows={3}
                value={termReason}
                onChange={(e) => setTermReason(e.target.value)}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn-sm btn-secondary"
                  onClick={() => setTermAgentId(null)}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-sm btn-reject"
                  disabled={loading}
                >
                  {loading ? 'Terminating...' : 'Confirm Termination'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
