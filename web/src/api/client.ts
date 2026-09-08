import {
  Agent,
  Approval,
  AuditEvent,
  Department,
  EvolutionCandidate,
  OwnerConsoleSummary,
  SystemRunState,
} from '../types';

const BASE_URL = '/api';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('mercury_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('mercury_token', token);
    } else {
      localStorage.removeItem('mercury_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  isAuthenticated(): boolean {
    return !!this.token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    headers.set('Content-Type', 'application/json');

    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      throw new Error('Authentication expired. Please log in.');
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Network request failed' }));
      throw new Error(err.detail || `Error ${response.status}`);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // Auth
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const res = await this.request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(res.access_token);
    return res;
  }

  async logout(): Promise<void> {
    try {
      await this.request<void>('/auth/logout', { method: 'POST' });
    } finally {
      this.setToken(null);
    }
  }

  // Executive Console
  async getConsoleSummary(): Promise<OwnerConsoleSummary> {
    return this.request<OwnerConsoleSummary>('/owner/console/summary');
  }

  async triggerEmergencyShutdown(reason: string): Promise<{ run_state: SystemRunState }> {
    return this.request('/owner/emergency-shutdown', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  async overrideSystemState(
    target_state: SystemRunState,
    reason: string
  ): Promise<{ run_state: SystemRunState }> {
    return this.request('/owner/override', {
      method: 'POST',
      body: JSON.stringify({ target_state, reason }),
    });
  }

  // Approvals
  async getApprovals(): Promise<Approval[]> {
    return this.request<Approval[]>('/approvals');
  }

  async decideApproval(approvalId: string, decision: 'APPROVE' | 'REJECT', reason: string): Promise<Approval> {
    return this.request<Approval>(`/approvals/${approvalId}/decision?decision=${decision}`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // Departments & Agents
  async getDepartments(): Promise<Department[]> {
    return this.request<Department[]>('/departments');
  }

  async getAgents(departmentId?: string): Promise<Agent[]> {
    const q = departmentId ? `?department_id=${departmentId}` : '';
    return this.request<Agent[]>(`/agents${q}`);
  }

  async suspendAgent(agentId: string): Promise<Agent> {
    return this.request<Agent>(`/agents/${agentId}/suspend`, { method: 'POST' });
  }

  async restoreAgent(agentId: string): Promise<Agent> {
    return this.request<Agent>(`/agents/${agentId}/restore`, { method: 'POST' });
  }

  async terminateAgent(agentId: string, reason: string): Promise<Agent> {
    return this.request<Agent>(`/agents/${agentId}/terminate`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // Evolution
  async getEvolutionCandidates(): Promise<EvolutionCandidate[]> {
    return this.request<EvolutionCandidate[]>('/evolution/candidates');
  }

  async promoteEvolutionCandidate(candidateId: string, notes?: string): Promise<EvolutionCandidate> {
    return this.request<EvolutionCandidate>(`/evolution/candidates/${candidateId}/promote`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  async rollbackEvolutionCandidate(candidateId: string, reason: string): Promise<EvolutionCandidate> {
    return this.request<EvolutionCandidate>(`/evolution/candidates/${candidateId}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // Audit Logs
  async getAuditLogs(limit: number = 50, eventType?: string): Promise<AuditEvent[]> {
    let url = `/owner/audit?limit=${limit}`;
    if (eventType) {
      url += `&event_type=${eventType}`;
    }
    return this.request<AuditEvent[]>(url);
  }
}

export const api = new ApiClient();
