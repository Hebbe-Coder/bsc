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
    outcome_state: 'awaiting_outcome' | 'unverified_outcome' | 'rejected_outcome' | 'accepted_incomplete' | 'learning_eligible' | string;
    created_at: string;
  }>;
  outcome_observations?: PbosOutcomeObservation[];
  feedback: Array<Record<string, unknown>>;
  strategies: Array<Record<string, unknown>>;
  failure_patterns: Array<Record<string, unknown>>;
  personalization_readiness?: PbosPersonalizationReadiness;
  project_health: PbosProjectHealth;
  connectors: Record<string, string>;
}

export interface PbosPersonalizationReadiness {
  state: 'profile_context_required' | 'learning_evidence_required' | 'promotion_evaluation_required' | 'personalized' | string;
  declared_profile_ready: boolean;
  missing_profile_fields: string[];
  accepted_outcome_count: number;
  required_comparable_outcomes: number;
  comparison_key?: string;
  comparison_context?: string;
}

export interface PbosProjectHealth {
  accepted_outcomes?: number;
  eligible_personal_outcomes?: number;
  unverified_outcomes?: number;
  rejected_outcomes?: number;
  reviewable_executions?: number;
  verified_capabilities?: number;
  active_strategies?: number;
  knowledge_context_ready?: boolean;
  knowledge_context_reference_count?: number;
  personal_learning_ready?: boolean;
  /** @deprecated Use personal_learning_ready. */
  evidence_ready?: boolean;
}

export interface PbosOutcomeObservation {
  artifact_id: string;
  acceptance_status: string;
  quality_score: number | null;
  eligible_for_evolution: boolean;
  missing_requirements: string[];
}

export interface PbosOutcomeReviewPayload {
  decision: 'accepted' | 'rejected';
  quality_score?: number;
  review_note?: string;
}

export interface PbosProfile {
  role?: string;
  industry?: string;
  organization_stage?: string;
  focus: string[];
  goals: string[];
  work_style?: string[];
  decision_style?: string[];
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

export function compilePbosPlan(projectId: string, missionId: string, diagnosisId = ''): Promise<{ plan: Record<string, unknown> }> {
  const query = diagnosisId ? `?diagnosis_id=${encodeURIComponent(diagnosisId)}` : '';
  return fetchWrapper.fetch<{ plan: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/missions/${encodeURIComponent(missionId)}/plans${query}`, {
    method: 'POST',
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

export function reviewPbosOutcome(projectId: string, outcomeId: string, payload: PbosOutcomeReviewPayload): Promise<{ outcome: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ outcome: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/outcomes/${encodeURIComponent(outcomeId)}/review`, {
    method: 'POST', body: JSON.stringify(payload),
  });
}

export function recordPbosFeedback(projectId: string, outcomeId: string, statement: string): Promise<{ feedback: Record<string, unknown> }> {
  return fetchWrapper.fetch<{ feedback: Record<string, unknown> }>(`/api/pbos/projects/${encodeURIComponent(projectId)}/outcomes/${encodeURIComponent(outcomeId)}/feedback`, {
    method: 'POST', body: JSON.stringify({ source: 'three_minute_reflection', sentiment: 'neutral', statement }),
  });
}
