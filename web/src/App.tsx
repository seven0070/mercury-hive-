import React, { useEffect, useState } from 'react';
import { api } from './api/client';
import { Agent, Approval, AuditEvent, Department, EvolutionCandidate, OwnerConsoleSummary } from './types';
import { Header } from './components/Header';
import { OverviewDashboard } from './components/OverviewDashboard';
import { ApprovalQueue } from './components/ApprovalQueue';
import { AgentRegistryView } from './components/AgentRegistryView';
import { EvolutionView } from './components/EvolutionView';
import { AuditLogViewer } from './components/AuditLogViewer';
import { LoginModal } from './components/LoginModal';

type ActiveTab = 'overview' | 'approvals' | 'workforce' | 'evolution' | 'audit';

export const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(api.isAuthenticated());
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');
  const [summary, setSummary] = useState<OwnerConsoleSummary | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [candidates, setCandidates] = useState<EvolutionCandidate[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditEvent[]>([]);

  const fetchAllData = async () => {
    if (!api.isAuthenticated()) return;
    try {
      const [sum, apprs, depts, agts, cands, logs] = await Promise.all([
        api.getConsoleSummary().catch(() => null),
        api.getApprovals().catch(() => []),
        api.getDepartments().catch(() => []),
        api.getAgents().catch(() => []),
        api.getEvolutionCandidates().catch(() => []),
        api.getAuditLogs(50).catch(() => []),
      ]);

      if (sum) setSummary(sum);
      setApprovals(apprs);
      setDepartments(depts);
      setAgents(agts);
      setCandidates(cands);
      setAuditLogs(logs);
    } catch (err) {
      console.error('Failed to refresh console data', err);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchAllData();
      const interval = setInterval(fetchAllData, 10000); // 10s telemetry polling
      return () => clearInterval(interval);
    }
  }, [isAuthenticated]);

  const handleLogin = async (email: string, pass: string) => {
    await api.login(email, pass);
    setIsAuthenticated(true);
    await fetchAllData();
  };

  const handleLogout = async () => {
    await api.logout();
    setIsAuthenticated(false);
  };

  const handleEmergencyShutdown = async () => {
    const reason = prompt(
      'EMERGENCY SHUTDOWN: Enter audited reason for halting all non-owner operations:',
      'Hostile divergence or anomalous autonomous activity detected'
    );
    if (!reason) return;
    try {
      await api.triggerEmergencyShutdown(reason);
      await fetchAllData();
      alert('EMERGENCY SHUTDOWN ACTIVE. All worker/manager execution halted.');
    } catch (err: any) {
      alert(err.message || 'Shutdown failed');
    }
  };

  const handleRestoreNormal = async () => {
    const reason = prompt('RESTORE NORMAL STATE: Enter justification:', 'System integrity verified');
    if (!reason) return;
    try {
      await api.overrideSystemState('NORMAL', reason);
      await fetchAllData();
      alert('System restored to NORMAL operational state.');
    } catch (err: any) {
      alert(err.message || 'Recovery failed');
    }
  };

  if (!isAuthenticated) {
    return <LoginModal onLogin={handleLogin} />;
  }

  return (
    <div className="console-container">
      <Header
        summary={summary}
        onEmergencyShutdown={handleEmergencyShutdown}
        onRestoreNormal={handleRestoreNormal}
        onLogout={handleLogout}
      />

      <nav className="nav-tabs">
        <button
          className={`nav-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Executive Overview
        </button>
        <button
          className={`nav-tab ${activeTab === 'approvals' ? 'active' : ''}`}
          onClick={() => setActiveTab('approvals')}
        >
          Approvals ({summary?.pending_approvals_count || 0})
        </button>
        <button
          className={`nav-tab ${activeTab === 'workforce' ? 'active' : ''}`}
          onClick={() => setActiveTab('workforce')}
        >
          Workforce Registry ({summary?.active_agents_count || 0})
        </button>
        <button
          className={`nav-tab ${activeTab === 'evolution' ? 'active' : ''}`}
          onClick={() => setActiveTab('evolution')}
        >
          Controlled Evolution ({summary?.evolution_candidates_count || 0})
        </button>
        <button
          className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          Audit Logs
        </button>
      </nav>

      <main>
        {activeTab === 'overview' && <OverviewDashboard summary={summary} />}

        {activeTab === 'approvals' && (
          <ApprovalQueue
            approvals={approvals}
            onDecide={async (id, dec, rsn) => {
              await api.decideApproval(id, dec, rsn);
            }}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'workforce' && (
          <AgentRegistryView
            departments={departments}
            agents={agents}
            onSuspend={async (id) => {
              await api.suspendAgent(id);
            }}
            onRestore={async (id) => {
              await api.restoreAgent(id);
            }}
            onTerminate={async (id, rsn) => {
              await api.terminateAgent(id, rsn);
            }}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'evolution' && (
          <EvolutionView
            candidates={candidates}
            onPromote={async (id, notes) => {
              await api.promoteEvolutionCandidate(id, notes);
            }}
            onRollback={async (id, rsn) => {
              await api.rollbackEvolutionCandidate(id, rsn);
            }}
            onRefresh={fetchAllData}
          />
        )}

        {activeTab === 'audit' && (
          <AuditLogViewer
            logs={auditLogs}
            onRefresh={async (eventType) => {
              const fresh = await api.getAuditLogs(50, eventType);
              setAuditLogs(fresh);
            }}
          />
        )}
      </main>
    </div>
  );
};
