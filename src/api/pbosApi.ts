import { fetchWrapper } from './fetchWrapper';

export interface PbosCockpit {
  profile: PbosProfile | null;
  today: Record<string, unknown> | null;
  today_action?: Record<string, unknown>;
  capabilities: Array<Record<string, unknown>>;
  outcomes: Array<Record<string, unknown>>;
  executions?: Array<{
    artifact_id: string;
    mission_id: string;
    plan_id: string;
    actions_count: number;
    receipt_count: number;
    verified_receipt_count: number;
    reflection_recorded: boolean;
    outcome_state: 'awaiting_outcome' | 'unverified_outcome' | 'accepted_incomplete' | 'learning_eligible' | string;
    created_at: string;
  }>;
  outcome_observations?: Array<Record<string, unknown>>;
  feedback: Array<Record<string, unknown>>;
  strategies: Array<Record<string, unknown>>;
  failure_patterns: Array<Record<string, unknown>>;
  project_health: PbosProjectHealth;
  connectors: Record<string, string>;
}

export interface PbosProjectHealth {
  accepted_outcomes?: number;
  eligible_personal_outcomes?: number;
  unverified_outcomes?: number;
  reviewable_executions?: number;
  verified_capabilities?: number;
  active_strategies?: number;
  knowledge_context_ready?: boolean;
  knowledge_context_reference_count?: number;
  personal_learning_ready?: boolean;
  /** @deprecated Use personal_learning_ready. */
  evidence_ready?: boolean;
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

export interface PbosWorkspaceCapturePayload {
  plan_id: string;
  paths: string[];
  actions: string[];
  reflection: Record<string, string>;
  observed_at?: string;
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

export function capturePbosWorkspaceExecution(projectId: string, missionId: string, payload: PbosWorkspaceCapturePayload): Promise<{ execution: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ execution: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/missions/${encodeURIComponent(missionId)}/capture-bsc-workspace`, {
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
