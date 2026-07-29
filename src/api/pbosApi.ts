import { fetchWrapper } from './fetchWrapper';

export interface PbosCockpit {
  profile: PbosProfile | null;
  today: Record<string, unknown> | null;
  capabilities: Array<Record<string, unknown>>;
  outcomes: Array<Record<string, unknown>>;
  feedback: Array<Record<string, unknown>>;
  strategies: Array<Record<string, unknown>>;
  failure_patterns: Array<Record<string, unknown>>;
  project_health: Record<string, unknown>;
  connectors: Record<string, string>;
}

export interface PbosProfile {
  focus: string[];
  goals: string[];
  preferences: Record<string, unknown>;
  resources: string[];
  constraints: string[];
}

export interface PbosExecutionPayload {
  plan_id: string;
  actions: string[];
  tool_receipts?: Array<Record<string, unknown>>;
  reflection: Record<string, string>;
}

export function fetchPbosCockpit(projectId: string): Promise<PbosCockpit> {
  return fetchWrapper.fetch<PbosCockpit>(`/api/pbos/projects/${encodeURIComponent(projectId)}/cockpit`);
}

export function fetchPbosProfile(projectId: string): Promise<{ profile: PbosProfile | null }> {
  return fetchWrapper.fetch<{ profile: PbosProfile | null }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/profile`);
}

export function savePbosProfile(projectId: string, profile: PbosProfile): Promise<{ profile: PbosProfile }> {
  return fetchWrapper.fetch<{ profile: PbosProfile }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/profile`, {
    method: 'PUT', body: JSON.stringify(profile),
  });
}

export function recordPbosExecution(projectId: string, missionId: string, payload: PbosExecutionPayload): Promise<{ execution: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ execution: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/missions/${encodeURIComponent(missionId)}/executions`, {
    method: 'POST', body: JSON.stringify(payload),
  });
}

export function recordPbosOutcome(projectId: string, executionId: string, payload: Record<string, unknown>): Promise<{ outcome: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ outcome: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/executions/${encodeURIComponent(executionId)}/outcomes`, {
    method: 'POST', body: JSON.stringify(payload),
  });
}

export function recordPbosFeedback(projectId: string, outcomeId: string, statement: string): Promise<{ feedback: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ feedback: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/outcomes/${encodeURIComponent(outcomeId)}/feedback`, {
    method: 'POST', body: JSON.stringify({ source: 'three_minute_reflection', sentiment: 'neutral', statement }),
  });
}
