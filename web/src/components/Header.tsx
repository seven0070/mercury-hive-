import React from 'react';
import { OwnerConsoleSummary, SystemRunState } from '../types';

interface HeaderProps {
  summary: OwnerConsoleSummary | null;
  onEmergencyShutdown: () => void;
  onRestoreNormal: () => void;
  onLogout: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  summary,
  onEmergencyShutdown,
  onRestoreNormal,
  onLogout,
}) => {
  const runState: SystemRunState = summary?.system_run_state || 'NORMAL';

  return (
    <header className="header">
      <div className="logo-group">
        <span className="mercury-glyph">☿</span>
        <div>
          <div className="title-sub">Governed AI Enterprise</div>
          <h1 className="title-main">Mercury Hive Sovereign Console</h1>
        </div>
      </div>

      <div className="header-controls">
        {summary?.constitution_hash && (
          <div className="badge mono" style={{ background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
            CONST: {summary.constitution_hash.slice(0, 10)}
          </div>
        )}

        <div className={`badge badge-${runState.toLowerCase()}`}>
          ● {runState}
        </div>

        {runState === 'EMERGENCY_SHUTDOWN' ? (
          <button className="btn-recover" onClick={onRestoreNormal}>
            Restore Normal State
          </button>
        ) : (
          <button className="btn-killswitch" onClick={onEmergencyShutdown}>
            ⚠ Emergency Shutdown
          </button>
        )}

        <button className="btn-sm btn-secondary" onClick={onLogout}>
          Logout
        </button>
      </div>
    </header>
  );
};
