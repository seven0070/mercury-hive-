import React, { useState } from 'react';
import { EvolutionCandidate } from '../types';

interface EvolutionViewProps {
  candidates: EvolutionCandidate[];
  onPromote: (id: string, notes?: string) => Promise<void>;
  onRollback: (id: string, reason: string) => Promise<void>;
  onRefresh: () => void;
}

export const EvolutionView: React.FC<EvolutionViewProps> = ({
  candidates,
  onPromote,
  onRollback,
  onRefresh,
}) => {
  const [promoteId, setPromoteId] = useState<string | null>(null);
  const [rollbackId, setRollbackId] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');
  const [loading, setLoading] = useState(false);

  const handlePromoteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promoteId) return;
    setLoading(true);
    try {
      await onPromote(promoteId, notes);
      setPromoteId(null);
      setNotes('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Promotion failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRollbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rollbackId) return;
    setLoading(true);
    try {
      await onRollback(rollbackId, rollbackReason);
      setRollbackId(null);
      setRollbackReason('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Rollback failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Controlled Evolution & Sandboxes</h2>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Governed AI mutation proposals: Prompts, Tools, Workflows & Policies
          </div>
        </div>
        <button className="btn-sm btn-secondary" onClick={onRefresh}>
          Refresh
        </button>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Proposal Title</th>
            <th>Type</th>
            <th>Target Identifier</th>
            <th>Status</th>
            <th>Shadow Traffic</th>
            <th>Benchmark Verdict</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {candidates.length === 0 ? (
            <tr>
              <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                No active evolution candidates proposed.
              </td>
            </tr>
          ) : (
            candidates.map((c) => (
              <tr key={c.id}>
                <td>
                  <strong>{c.title}</strong>
                </td>
                <td>
                  <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8' }}>
                    {c.evolution_type}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '0.8rem' }}>
                  {c.target_identifier}
                </td>
                <td>
                  <span
                    className="badge"
                    style={{
                      background:
                        c.status === 'PROMOTED'
                          ? 'rgba(16, 185, 129, 0.2)'
                          : c.status === 'SHADOW_DEPLOYED'
                          ? 'rgba(236, 72, 153, 0.2)'
                          : c.status === 'ROLLED_BACK'
                          ? 'rgba(239, 68, 68, 0.2)'
                          : 'rgba(245, 158, 11, 0.2)',
                      color:
                        c.status === 'PROMOTED'
                          ? '#10b981'
                          : c.status === 'SHADOW_DEPLOYED'
                          ? '#ec4899'
                          : c.status === 'ROLLED_BACK'
                          ? '#ef4444'
                          : '#f59e0b',
                    }}
                  >
                    {c.status}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div
                      style={{
                        width: '80px',
                        height: '8px',
                        background: 'var(--bg-primary)',
                        borderRadius: '4px',
                        overflow: 'hidden',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div
                        style={{
                          width: `${c.shadow_traffic_percentage}%`,
                          height: '100%',
                          background: c.shadow_traffic_percentage === 100 ? '#10b981' : '#ec4899',
                        }}
                      />
                    </div>
                    <span className="mono" style={{ fontSize: '0.75rem' }}>
                      {c.shadow_traffic_percentage}%
                    </span>
                  </div>
                </td>
                <td>
                  {c.benchmark_results?.verdict ? (
                    <span
                      className="badge mono"
                      style={{
                        background:
                          c.benchmark_results.verdict === 'PASSED'
                            ? 'rgba(16, 185, 129, 0.2)'
                            : 'rgba(239, 68, 68, 0.2)',
                        color:
                          c.benchmark_results.verdict === 'PASSED'
                            ? '#10b981'
                            : '#ef4444',
                      }}
                    >
                      {c.benchmark_results.verdict} ({c.benchmark_results.candidate_score} vs {c.benchmark_results.baseline_score})
                    </span>
                  ) : (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Untested</span>
                  )}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {c.status !== 'PROMOTED' && c.status !== 'ROLLED_BACK' && (
                      <button
                        className="btn-sm btn-approve"
                        onClick={() => {
                          setPromoteId(c.id);
                          setNotes('Promoted after successful verification');
                        }}
                      >
                        Promote (100%)
                      </button>
                    )}
                    {(c.status === 'PROMOTED' || c.status === 'SHADOW_DEPLOYED') && (
                      <button
                        className="btn-sm btn-reject"
                        onClick={() => {
                          setRollbackId(c.id);
                          setRollbackReason('Safety rollback triggered by Owner');
                        }}
                      >
                        Rollback
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {promoteId && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 style={{ marginBottom: '1rem', color: '#10b981' }}>
              Promote Mutation to 100% Production
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              System Owner promotion applies this mutation across all operational workloads.
            </p>
            <form onSubmit={handlePromoteSubmit}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Promotion Notes
              </label>
              <textarea
                className="input-field"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn-sm btn-secondary"
                  onClick={() => setPromoteId(null)}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-sm btn-approve" disabled={loading}>
                  {loading ? 'Promoting...' : 'Confirm Production Promotion'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {rollbackId && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 style={{ marginBottom: '1rem', color: '#ef4444' }}>
              Instant Evolution Rollback
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Immediately drops shadow and live production traffic to 0% and reverts target configuration.
            </p>
            <form onSubmit={handleRollbackSubmit}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Reversion Justification
              </label>
              <textarea
                className="input-field"
                rows={3}
                value={rollbackReason}
                onChange={(e) => setRollbackReason(e.target.value)}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn-sm btn-secondary"
                  onClick={() => setRollbackId(null)}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-sm btn-reject" disabled={loading}>
                  {loading ? 'Rolling back...' : 'Confirm Instant Rollback'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
