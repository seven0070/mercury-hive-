import React, { useState } from 'react';
import { AuditEvent } from '../types';

interface AuditLogViewerProps {
  logs: AuditEvent[];
  onRefresh: (eventType?: string) => void;
}

export const AuditLogViewer: React.FC<AuditLogViewerProps> = ({ logs, onRefresh }) => {
  const [filterType, setFilterType] = useState<string>('ALL');
  const [search, setSearch] = useState('');
  const [activePayload, setActivePayload] = useState<Record<string, any> | null>(null);

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setFilterType(val);
    onRefresh(val === 'ALL' ? undefined : val);
  };

  const filteredLogs = logs.filter((l) => {
    if (!search) return true;
    const term = search.toLowerCase();
    return (
      l.action.toLowerCase().includes(term) ||
      (l.reason && l.reason.toLowerCase().includes(term)) ||
      (l.actor_role && l.actor_role.toLowerCase().includes(term))
    );
  });

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Tamper-Proof Audit Trail</h2>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Immutable PostgreSQL security evidence (direct DML revoked)
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <input
            type="text"
            className="input-field"
            placeholder="Search action or reason..."
            style={{ margin: 0, padding: '0.35rem 0.75rem', width: '220px' }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="input-field"
            style={{ margin: 0, padding: '0.35rem 0.75rem', width: 'auto' }}
            value={filterType}
            onChange={handleTypeChange}
          >
            <option value="ALL">All Event Types</option>
            <option value="AUTH">AUTH</option>
            <option value="SYSTEM">SYSTEM</option>
            <option value="GOVERNANCE">GOVERNANCE</option>
            <option value="SECURITY">SECURITY</option>
            <option value="ACCESS">ACCESS</option>
          </select>
          <button
            className="btn-sm btn-secondary"
            onClick={() => onRefresh(filterType === 'ALL' ? undefined : filterType)}
          >
            Refresh
          </button>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Type</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Decision</th>
            <th>Reason / Details</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          {filteredLogs.length === 0 ? (
            <tr>
              <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                No audit events found matching filters.
              </td>
            </tr>
          ) : (
            filteredLogs.map((l) => (
              <tr key={l.id}>
                <td className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {new Date(l.timestamp).toLocaleString()}
                </td>
                <td>
                  <span
                    className="badge mono"
                    style={{
                      background:
                        l.event_type === 'SECURITY'
                          ? 'rgba(239, 68, 68, 0.2)'
                          : l.event_type === 'AUTH'
                          ? 'rgba(168, 85, 247, 0.2)'
                          : 'rgba(56, 189, 248, 0.2)',
                      color:
                        l.event_type === 'SECURITY'
                          ? '#ef4444'
                          : l.event_type === 'AUTH'
                          ? '#a855f7'
                          : '#38bdf8',
                    }}
                  >
                    {l.event_type}
                  </span>
                </td>
                <td>
                  <span style={{ fontWeight: 600 }}>{l.actor_role || 'SYSTEM'}</span>
                </td>
                <td>
                  <code>{l.action}</code>
                </td>
                <td>
                  {l.decision && (
                    <span
                      className="badge mono"
                      style={{
                        background:
                          l.decision === 'ALLOW'
                            ? 'rgba(16, 185, 129, 0.15)'
                            : 'rgba(239, 68, 68, 0.15)',
                        color: l.decision === 'ALLOW' ? '#10b981' : '#ef4444',
                      }}
                    >
                      {l.decision}
                    </span>
                  )}
                </td>
                <td style={{ fontSize: '0.85rem' }}>{l.reason || '—'}</td>
                <td>
                  {l.payload ? (
                    <button
                      className="btn-sm btn-secondary"
                      onClick={() => setActivePayload(l.payload as Record<string, any>)}
                    >
                      Inspect JSON
                    </button>
                  ) : (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>None</span>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {activePayload && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '600px' }}>
            <h3 style={{ marginBottom: '1rem', color: '#38bdf8' }}>
              Audited Payload Telemetry
            </h3>
            <pre
              className="mono"
              style={{
                background: 'var(--bg-primary)',
                padding: '1rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                fontSize: '0.8rem',
                color: '#f1f5f9',
                maxHeight: '350px',
                overflowY: 'auto',
              }}
            >
              {JSON.stringify(activePayload, null, 2)}
            </pre>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
              <button
                className="btn-sm btn-secondary"
                onClick={() => setActivePayload(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
