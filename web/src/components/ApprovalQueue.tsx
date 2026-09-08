import React, { useState } from 'react';
import { Approval } from '../types';

interface ApprovalQueueProps {
  approvals: Approval[];
  onDecide: (id: string, decision: 'APPROVE' | 'REJECT', reason: string) => Promise<void>;
  onRefresh: () => void;
}

export const ApprovalQueue: React.FC<ApprovalQueueProps> = ({
  approvals,
  onDecide,
  onRefresh,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [decisionType, setDecisionType] = useState<'APPROVE' | 'REJECT' | null>(null);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);

  const handleOpenDecision = (id: string, type: 'APPROVE' | 'REJECT') => {
    setSelectedId(id);
    setDecisionType(type);
    setReason(type === 'APPROVE' ? 'Approved by System Owner' : 'Denied per security policy');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !decisionType) return;

    setLoading(true);
    try {
      await onDecide(selectedId, decisionType, reason);
      setSelectedId(null);
      setDecisionType(null);
      setReason('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Failed to submit decision');
    } finally {
      setLoading(false);
    }
  };

  const pendingApprovals = approvals.filter((a) => a.status === 'PENDING');

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Pending Governance Approvals</h2>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            High-risk mutations requiring explicit human authorization
          </div>
        </div>
        <button className="btn-sm btn-secondary" onClick={onRefresh}>
          Refresh Queue
        </button>
      </div>

      {pendingApprovals.length === 0 ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          ✓ No pending approvals requiring human review.
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Action Type</th>
              <th>Risk Level</th>
              <th>Requested By</th>
              <th>Context / Reason</th>
              <th>Requested At</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pendingApprovals.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.action_type}</strong>
                </td>
                <td>
                  <span
                    className="badge"
                    style={{
                      background:
                        a.risk_level === 'CRITICAL'
                          ? 'rgba(239, 68, 68, 0.2)'
                          : a.risk_level === 'HIGH'
                          ? 'rgba(245, 158, 11, 0.2)'
                          : 'rgba(56, 189, 248, 0.2)',
                      color:
                        a.risk_level === 'CRITICAL'
                          ? '#ef4444'
                          : a.risk_level === 'HIGH'
                          ? '#f59e0b'
                          : '#38bdf8',
                    }}
                  >
                    {a.risk_level}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '0.8rem' }}>
                  {a.requested_by.slice(0, 8)}...
                </td>
                <td>{a.reason || 'N/A'}</td>
                <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {new Date(a.created_at).toLocaleString()}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      className="btn-sm btn-approve"
                      onClick={() => handleOpenDecision(a.id, 'APPROVE')}
                    >
                      Approve
                    </button>
                    <button
                      className="btn-sm btn-reject"
                      onClick={() => handleOpenDecision(a.id, 'REJECT')}
                    >
                      Reject
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedId && decisionType && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 style={{ marginBottom: '1rem', color: '#fff' }}>
              {decisionType === 'APPROVE' ? 'Confirm Approval' : 'Confirm Rejection'}
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Provide the audited human justification for this governance decision.
            </p>
            <form onSubmit={handleSubmit}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Justification / Reason
              </label>
              <textarea
                className="input-field"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn-sm btn-secondary"
                  onClick={() => {
                    setSelectedId(null);
                    setDecisionType(null);
                  }}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={`btn-sm ${decisionType === 'APPROVE' ? 'btn-approve' : 'btn-reject'}`}
                  disabled={loading}
                >
                  {loading ? 'Submitting...' : `Confirm ${decisionType}`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
