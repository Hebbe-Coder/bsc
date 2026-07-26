import { apiFetch } from './fetchWrapper';

export type DbosStatus = 'draft' | 'ready_for_confirmation' | 'confirmed' | 'executing' | 'completed' | 'failed' | 'stopped' | 'rolled_back' | string;

export type DbosMission = {
  artifact_id: string;
  project_id?: string;
  title: string;
  intent?: string;
  intake_mode?: 'business' | 'career';
  mission_status: DbosStatus;
  status?: DbosStatus;
  authorization?: Record<string, unknown>;
  context?: Record<string, unknown>;
  [key: string]: unknown;
};

export type DbosCapability = {
  capability_name: string;
  task_family: string;
  score: number;
  reasons: string[];
  executable: boolean;
};

export type DbosExecutionResult = {
  artifact_id: string;
  execution_id: string;
  mission_id: string;
  capability_name: string;
  execution_status: DbosStatus;
  status?: DbosStatus;
  effects?: Array<Record<string, unknown>>;
  error?: string;
  idempotency_key?: string;
  rollback?: Record<string, unknown>;
  [key: string]: unknown;
};

export type DbosDiagnosis = {
  role?: string;
  industry?: string;
  organization_stage?: string;
  goal?: string;
  problem_statement?: string;
  constraints?: string[];
  stakeholders?: string[];
  decision_rights?: string[];
  success_metrics?: string[];
  operating_hypotheses?: string[];
  diagnostic_dimensions?: string[];
  evidence_refs?: string[];
  missing_fields?: string[];
  risk_summary?: string[];
  coverage?: number;
  [key: string]: any;
};

export type DbosTask = {
  task_id: string;
  title: string;
  task_family: string;
  capability_name: string;
  owner: string;
  deliverable: string;
  metric: string;
  trigger: string;
  decision_point: string;
  risk: string;
  check: string;
  retrospect: string;
  parent_refs: string[];
};

export type DbosPhase = {
  phase_id: string;
  title: string;
  objective: string;
  tasks: DbosTask[];
};

export type DbosDecision = {
  artifact_id: string;
  decision_statement: string;
  rationale?: string;
  recommendation?: string;
  decision_makers?: string[];
  metadata?: { task_id?: string; [key: string]: unknown };
  [key: string]: unknown;
};

export type DbosRuntimeContext = {
  artifact_id: string;
  context_revision: string;
  purpose: string;
  estimated_tokens: number;
  context_window_tokens: number;
  compaction_required: boolean;
  source_ids: string[];
  method_ids: string[];
  redacted: boolean;
  [key: string]: unknown;
};

export type DbosTaskVerification = {
  artifact_id: string;
  execution_id: string;
  capability_name: string;
  verification_status: 'passed' | 'failed' | 'pending' | string;
  findings?: string[];
  produced_artifact_ids?: string[];
  [key: string]: unknown;
};

export type DbosExternalWorkerRun = {
  artifact_id: string;
  worker_id: string;
  worker_status: 'queued' | 'executing' | 'cancellation_requested' | 'cancelled' | 'interrupted' | 'completed' | 'failed' | 'rejected' | string;
  egress_host?: string;
  model_id?: string;
  output_artifact_ids?: string[];
  reason?: string;
  requested_at?: string;
  outbound_started_at?: string;
  cancellation_requested_at?: string;
  cancelled_at?: string;
  recovered_at?: string;
  completed_at?: string;
  [key: string]: unknown;
};

export type DbosAdvisorReview = {
  artifact_id: string;
  mission_id: string;
  advisor_status: 'completed' | 'unavailable' | 'failed' | string;
  verdict?: 'advisory' | 'needs_attention' | 'insufficient_evidence' | 'unavailable' | 'invalid_response' | string;
  summary?: string;
  findings?: Array<{ severity: string; category: string; statement: string; recommendation?: string; evidence_refs?: string[] }>;
  open_questions?: string[];
  prompt_run_id?: string;
  prompt_agent_id?: string;
  prompt_agent_revision?: string;
  provider?: string;
  model_id?: string;
  error_category?: string;
  reviewed_at?: string;
  [key: string]: unknown;
};

export type DbosSopRoutingEvaluation = {
  artifact_id: string;
  evaluator_revision: string;
  selector_fingerprint: string;
  evaluation_status: 'passed' | 'failed' | 'pending' | string;
  positive_case_count: number;
  near_negative_case_count: number;
  holdout_case_count: number;
  holdout_passed: boolean;
  findings?: string[];
  case_results?: Array<{
    case_id: string;
    split: string;
    passed: boolean;
    observed_profile?: string;
    findings?: string[];
  }>;
  [key: string]: unknown;
};

export type DbosControlCenter = {
  mission: DbosMission;
  diagnosis: DbosDiagnosis | null;
  selection: { selected: DbosCapability[]; rejected?: DbosCapability[]; selection_reasoning?: string; metadata?: Record<string, unknown>; [key: string]: unknown } | null;
  dynamic_sop: { title?: string; objective?: string; diagnostic_summary?: string; quality_gates?: string[]; compilation_reasoning?: string; phases: DbosPhase[]; [key: string]: any } | null;
  execution_results: DbosExecutionResult[];
  decisions: DbosDecision[];
  memories: Array<{ artifact_id: string; statement?: string; [key: string]: any }>;
  assumptions: Array<{ artifact_id: string; statement?: string; criticality?: string; validation_method?: string; [key: string]: any }>;
  gaps: Array<{ artifact_id: string; label?: string; gap_statement?: string; category?: string; severity?: string; resolution?: string; [key: string]: any }>;
  risks: Array<{ artifact_id: string; risk_statement?: string; severity?: string; mitigation?: string; trigger_signals?: string[]; [key: string]: any }>;
  evidence: Array<{ artifact_id: string; source?: string; finding?: string; strength?: string; [key: string]: any }>;
  verifications: DbosTaskVerification[];
  external_worker_runs?: DbosExternalWorkerRun[];
  advisor_reviews?: DbosAdvisorReview[];
  sop_routing_evaluation?: DbosSopRoutingEvaluation | null;
  runtime_context: DbosRuntimeContext | null;
  knowledge_context?: Record<string, unknown>;
  health: { executions_total?: number; executions_completed?: number; executions_failed?: number; executions_rejected?: number; executions_verified?: number; executions_verification_failed?: number; executions_unverified?: number; external_worker_runs_total?: number; external_worker_runs_completed?: number; external_worker_runs_failed?: number; external_worker_runs_rejected?: number; external_worker_runs_active?: number; external_worker_runs_cancellation_requested?: number; external_worker_runs_cancelled?: number; external_worker_runs_interrupted?: number; advisor_reviews_total?: number; advisor_reviews_completed?: number; advisor_reviews_unavailable?: number; advisor_reviews_failed?: number; advisor_findings_open?: number; unresolved_gaps?: number; evidence_gaps?: number; sop_routing_evaluation_status?: string; sop_routing_holdouts_passed?: boolean; [key: string]: unknown };
  reasoning_graph: {
    root_id?: string;
    nodes: Array<{ id: string; type: string; label: string; status: string }>;
    edges: Array<{ source: string; target: string }>;
  };
};

export type DbosMissionList = {
  project_id: string;
  missions: DbosMission[];
};

// Uppercase aliases keep the original DBOS plan and its first control center
// compatible while new code follows the repository's Dbos type convention.
export type DBOSControlCenter = DbosControlCenter;
export type DBOSMission = DbosMission;

export type DbosMissionInput = {
  project_id: string;
  title: string;
  intent: string;
  intake_mode: 'business' | 'career';
  context: Record<string, unknown>;
};

export type DbosIntakeQuestion = {
  question_id: string;
  phase: 'qualify' | 'complete' | 'probe' | string;
  field: string;
  prompt: string;
  options: Array<{ label: string; value: string }>;
};

export type DbosIntake = {
  artifact_id: string;
  project_id: string;
  original_request: string;
  classification: 'build' | 'direct' | 'help' | 'uncertain' | string;
  classification_confidence: number;
  classification_rationale: string[];
  domain: string;
  phase: 'classified' | 'clarifying' | 'ready_for_review' | 'converted' | 'exited' | string;
  active_question?: Record<string, unknown>;
  tier?: 'lite' | 'standard' | 'full' | string;
  recommendation_state?: 'idle' | 'available' | 'unavailable' | string;
  recommendations?: Array<Record<string, unknown>>;
  unresolved_fields: string[];
  linked_mission_id?: string;
  handoff_path?: string;
  handoff_sha256?: string;
  [key: string]: unknown;
};

export class DbosRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = 'dbos_request_failed',
  ) {
    super(message);
    this.name = 'DbosRequestError';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, { ...init, skipRetry: true });
  const text = await response.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? (body as { detail?: unknown }).detail : body;
    const error = typeof detail === 'object' && detail !== null
      ? detail as { code?: string; message?: string }
      : {};
    throw new DbosRequestError(
      error.message || (typeof detail === 'string' ? detail : `DBOS request failed (${response.status})`),
      response.status,
      error.code || 'dbos_request_failed',
    );
  }
  return body as T;
}

function projectQuery(projectId: string): string {
  return `project_id=${encodeURIComponent(projectId)}`;
}

function json(init: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(init) };
}

export async function createDbosMission(input: DbosMissionInput): Promise<DbosMission> {
  const payload = await request<{ mission: DbosMission }>('/api/dbos/missions', json(input));
  return payload.mission;
}

export function listDbosMissions(projectId: string): Promise<DbosMissionList> {
  return request(`/api/dbos/missions?${projectQuery(projectId)}`);
}

export async function diagnoseDbosMission(projectId: string, missionId: string): Promise<{ mission: DbosMission; selection: { selected?: DbosCapability[] } }> {
  return request(`/api/dbos/missions/${encodeURIComponent(missionId)}/diagnose?${projectQuery(projectId)}`, json({}));
}

export async function fetchDbosControlCenter(projectId: string, missionId: string): Promise<DbosControlCenter> {
  return request(`/api/dbos/missions/${encodeURIComponent(missionId)}/control-center?${projectQuery(projectId)}`);
}

export async function confirmDbosMission(projectId: string, missionId: string, actorId: string, authorizedCapabilities: string[]): Promise<DbosMission> {
  const payload = await request<{ mission: DbosMission }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/confirm`,
    json({ project_id: projectId, actor_id: actorId, authorized_capabilities: authorizedCapabilities }),
  );
  return payload.mission;
}

export async function executeDbosMission(projectId: string, missionId: string, capabilityName: string, idempotencyKey = ''): Promise<DbosExecutionResult> {
  const payload = await request<{ execution_result: DbosExecutionResult }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/executions`,
    json({ project_id: projectId, capability_name: capabilityName, idempotency_key: idempotencyKey }),
  );
  return payload.execution_result;
}

export async function reviewDbosMission(projectId: string, missionId: string, idempotencyKey: string): Promise<DbosAdvisorReview> {
  const payload = await request<{ advisor_review: DbosAdvisorReview }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/advisor-reviews`,
    json({ project_id: projectId, idempotency_key: idempotencyKey }),
  );
  return payload.advisor_review;
}

export async function stopDbosMission(projectId: string, missionId: string, reason: string): Promise<DbosMission> {
  const payload = await request<{ mission: DbosMission }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/stop`,
    json({ project_id: projectId, reason }),
  );
  return payload.mission;
}

export async function rollbackDbosExecution(projectId: string, executionId: string, reason: string): Promise<DbosExecutionResult> {
  const payload = await request<{ execution_result: DbosExecutionResult }>(
    `/api/dbos/executions/${encodeURIComponent(executionId)}/rollback`,
    json({ project_id: projectId, reason }),
  );
  return payload.execution_result;
}

export async function reconcileDbosMissionVerifications(projectId: string, missionId: string): Promise<DbosTaskVerification[]> {
  const payload = await request<{ verifications: DbosTaskVerification[] }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/verifications/reconcile?${projectQuery(projectId)}`,
    json({}),
  );
  return payload.verifications;
}

export async function recordDbosFeedback(projectId: string, missionId: string, statement: string, sourceRefs: string[] = []): Promise<Record<string, unknown>> {
  const payload = await request<{ memory: Record<string, unknown> }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/feedback`,
    json({ project_id: projectId, statement, source_refs: sourceRefs }),
  );
  return payload.memory;
}

export async function recordDbosDecision(
  projectId: string,
  missionId: string,
  input: { task_id: string; statement: string; rationale: string; alternatives?: string[]; actor_id: string },
): Promise<DbosDecision> {
  const payload = await request<{ decision: DbosDecision }>(
    `/api/dbos/missions/${encodeURIComponent(missionId)}/decisions`,
    json({ project_id: projectId, ...input }),
  );
  return payload.decision;
}

export async function createDbosIntake(projectId: string, requestText: string, context: Record<string, unknown> = {}): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>('/api/dbos/intake', json({ project_id: projectId, request_text: requestText, context }));
  return payload.intake;
}

export async function fetchDbosIntake(projectId: string, sessionId: string): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>(`/api/dbos/intake/${encodeURIComponent(sessionId)}?${projectQuery(projectId)}`);
  return payload.intake;
}

export async function resolveDbosIntake(projectId: string, sessionId: string, action: 'clarify' | 'direct' | 'help'): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>(`/api/dbos/intake/${encodeURIComponent(sessionId)}/uncertainty`, json({ project_id: projectId, action }));
  return payload.intake;
}

export async function nextDbosIntakeQuestion(projectId: string, sessionId: string): Promise<{ intake: DbosIntake; question: DbosIntakeQuestion | null }> {
  return request(`/api/dbos/intake/${encodeURIComponent(sessionId)}/questions/next`, json({ project_id: projectId }));
}

export async function answerDbosIntake(projectId: string, sessionId: string, questionId: string, answer = '', skipped = false): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>(`/api/dbos/intake/${encodeURIComponent(sessionId)}/answers`, json({ project_id: projectId, question_id: questionId, answer, skipped }));
  return payload.intake;
}

export async function selectDbosIntakeTier(projectId: string, sessionId: string, tier: 'lite' | 'standard' | 'full'): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>(`/api/dbos/intake/${encodeURIComponent(sessionId)}/tier`, json({ project_id: projectId, tier }));
  return payload.intake;
}

export async function recommendDbosIntake(projectId: string, sessionId: string): Promise<DbosIntake> {
  const payload = await request<{ intake: DbosIntake }>(`/api/dbos/intake/${encodeURIComponent(sessionId)}/recommendations`, json({ project_id: projectId }));
  return payload.intake;
}

export async function convertDbosIntake(projectId: string, sessionId: string, title = ''): Promise<{ intake: DbosIntake; mission: DbosMission }> {
  return request(`/api/dbos/intake/${encodeURIComponent(sessionId)}/convert`, json({ project_id: projectId, title }));
}

export async function exportDbosIntakeHandoff(projectId: string, sessionId: string, actorId: string, approved: boolean): Promise<{ intake: DbosIntake; handoff: Record<string, unknown> }> {
  return request(`/api/dbos/intake/${encodeURIComponent(sessionId)}/handoff`, json({ project_id: projectId, actor_id: actorId, approved }));
}

export async function createDBOSMission(input: DbosMissionInput): Promise<{ mission: DbosMission }> {
  return { mission: await createDbosMission(input) };
}

export const diagnoseDBOSMission = diagnoseDbosMission;
export const getDBOSControlCenter = fetchDbosControlCenter;
export async function confirmDBOSMission(projectId: string, missionId: string, authorizedCapabilities: string[]): Promise<DbosMission> {
  return confirmDbosMission(projectId, missionId, 'studio-owner', authorizedCapabilities);
}
export const executeDBOSCapability = executeDbosMission;
export const reviewDBOSMission = reviewDbosMission;
export const stopDBOSMission = stopDbosMission;
export const rollbackDBOSExecution = rollbackDbosExecution;
export const reconcileDBOSMissionVerifications = reconcileDbosMissionVerifications;
export const recordDBOSFeedback = recordDbosFeedback;
export const recordDBOSDecision = recordDbosDecision;
