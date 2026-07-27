import { apiFetch, fetchWrapper } from './fetchWrapper';

export type GrowthStage = 'A' | 'B' | 'C' | 'D' | 'review';
export type GrowthAssetKind = 'source' | 'page' | 'method' | 'method_proposal' | 'candidate' | 'output' | 'feedback' | 'proposal' | 'distillation';
export type GrowthRequestState = 'idle' | 'loading' | 'success' | 'empty' | 'permission' | 'offline' | 'unavailable' | 'error';

export type GrowthSourcePolicy = {
  primary_origin_prefixes: string[];
  trusted_origin_prefixes: string[];
  community_origin_prefixes: string[];
  blocked_origin_prefixes: string[];
  trusted_source_types: string[];
  require_triage_source_types: string[];
  primary_retention_days: number;
  trusted_retention_days: number;
  community_retention_days: number;
  untrusted_retention_days: number;
};

export type ExternalWorkerPolicy = {
  enabled: boolean;
  worker_ids: string[];
  allowed_model_ids: string[];
  allowed_https_hosts: string[];
  allowed_capabilities: string[];
  credential_ref: string;
  allowed_environments: string[];
  max_calls: number;
  max_concurrent: number;
  max_cost_microusd: number;
  timeout_seconds: number;
};

export type GrowthProfile = {
  project_id: string;
  revision?: number;
  user_role?: string;
  research_domains?: string[];
  primary_output_types?: string[];
  target_audiences?: string[];
  preferred_channels?: string[];
  language?: string;
  content_voice?: string;
  evidence_threshold?: number;
  automatic_publication_policy?: string;
  method_promotion_policy?: string;
  source_policy?: GrowthSourcePolicy;
  external_worker_policy?: ExternalWorkerPolicy;
  [key: string]: unknown;
};

export type GrowthProfileUpdate = Pick<
  GrowthProfile,
  | 'user_role'
  | 'research_domains'
  | 'primary_output_types'
  | 'target_audiences'
  | 'preferred_channels'
  | 'language'
  | 'content_voice'
  | 'evidence_threshold'
  | 'automatic_publication_policy'
  | 'method_promotion_policy'
  | 'source_policy'
  | 'external_worker_policy'
> & { expected_revision: number };

export type GrowthCounts = {
  sources: number;
  eligible_sources: number;
  pages: number;
  methods: number;
  published_methods: number;
  outputs: number;
  // Compatibility field name. The backend counts accepted and durably filed D-layer outputs.
  accepted_outputs: number;
  rejected_outputs: number;
  feedback: number;
  wiki_proposals?: number;
  method_proposals?: number;
  candidates?: number;
  pending_candidates?: number;
  review_records?: number;
  open_failures?: number;
};

export type GrowthSummary = { project_id: string; counts: GrowthCounts };
export type GrowthRecord = {
  id: string;
  project_id?: string;
  asset_type?: string;
  status?: string;
  title?: string;
  name?: string;
  origin?: string;
  path?: string;
  slug?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type GrowthAssets = {
  project_id: string;
  stage: string;
  items?: GrowthRecord[];
  pagination?: {
    limit: number;
    cursor: string | null;
    next_cursor: string | null;
    count: number;
  };
  sources?: GrowthRecord[];
  pages?: GrowthRecord[];
  methods?: GrowthRecord[];
  outputs?: GrowthRecord[];
  feedback?: GrowthRecord[];
  candidates?: GrowthRecord[];
  proposals?: GrowthRecord[];
};

export type GrowthLineageEdge = {
  id: string;
  from_id: string;
  to_id: string;
  from_type?: string;
  to_type?: string;
  edge_type: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

export type GrowthLineageNode = {
  id: string;
  type: string;
  label: string;
  status: string;
};

export type GrowthLineage = {
  project_id: string;
  edges: GrowthLineageEdge[];
  nodes?: GrowthLineageNode[];
  limit: number;
  truncated: boolean;
};

export type GrowthAccess = {
  role: string;
  can_write: boolean;
  features: Record<string, boolean>;
  access?: { role: string; can_write: boolean };
  vault?: {
    configured: boolean;
    status: string;
    connection?: { state: string; message?: string };
  };
  plugins?: {
    plugins: Array<{
      id: string;
      status: string;
      path_status: string;
      captured_sources: number;
      registered_outputs: number;
    }>;
  };
  sync?: { status: string };
  horizon?: {
    enabled: boolean;
    captured_sources: number;
    artifact_store?: { configured: boolean; available: boolean; mode: string };
    last_run?: {
      status: string;
      accepted: number;
      created: number;
      duplicates: number;
      skipped: boolean;
      outcome: 'processed' | 'empty_result' | 'no_new_artifact' | 'channel_error' | 'configuration_error' | 'failed';
      items_observed: number;
      failure: { category: string; code: string; retryable: boolean } | null;
    } | null;
  };
  scheduler?: { available: boolean; mode: 'celery' | 'manual' };
  growth?: { status: string };
};

export type GrowthHealth = {
  status: string;
  citation_coverage: number | null;
  orphan_page_ids: string[];
  stale_page_ids: string[];
  uncited_eligible_source_ids: string[];
  pending_proposal_ids: string[];
  dangling_citation_count: number;
  stale_citation_count: number;
  contradiction_count: number;
  contradiction_pairs: string[][];
  evaluation: { status: string; latest_score: number | null; runs: number; reason: string };
};

export type GrowthTrend = {
  source_throughput: Array<{ date: string; count: number }>;
  proposal_outcomes: Array<{ date: string; statuses: Record<string, number> }>;
  evaluations: Array<{ at: string; score: number | null; baseline_score: number | null; score_delta: number | null; latency_ms: number | null; status: string }>;
  current: GrowthHealth;
};

export type GrowthOverview = {
  profile: GrowthProfile;
  summary: GrowthSummary;
};

export type GrowthStageResult = {
  project_id: string;
  stage: GrowthStage;
  records: GrowthRecord[];
  limit: number;
  truncated: boolean;
};

export type GrowthRun = GrowthRecord & {
  run_id?: string;
  run_type?: 'growth_daily' | 'growth_weekly_distillation' | 'source_sync' | 'horizon_capture' | 'source_method_distillation' | 'cangjie_candidate_extraction';
  status?: string;
};

export type GrowthCaptureAttempt = GrowthRecord & {
  source_type: string;
  origin?: string;
  content_hash?: string;
  run_id?: string;
  source_id?: string;
  outcome: 'captured' | 'duplicate' | 'rejected_by_policy' | 'projection_failed' | string;
  policy?: Record<string, unknown>;
  projection?: Record<string, unknown>;
};

export type GrowthRunEvent = GrowthRecord & {
  run_id: string;
  sequence: number;
  event_type: string;
  payload?: Record<string, unknown>;
};

export type GrowthFailure = GrowthRecord & {
  code: string;
  diagnostic_pattern?: 'P01' | 'P02' | 'P03' | 'P04' | 'P05' | 'P06' | 'P07' | 'P08' | 'P09' | 'P10' | 'P11' | 'P12';
  secondary_diagnostic_patterns?: Array<'P01' | 'P02' | 'P03' | 'P04' | 'P05' | 'P06' | 'P07' | 'P08' | 'P09' | 'P10' | 'P11' | 'P12'>;
  severity: 'info' | 'warning' | 'error' | 'critical';
  summary: string;
  run_id?: string;
  event_sequence?: number | null;
  evidence_refs?: string[];
  root_cause?: string;
  minimal_structural_fix?: string;
  retryable?: boolean;
  status: 'open' | 'retry_scheduled' | 'resolved';
  resolution?: Record<string, unknown>;
};

export type GrowthDistillation = GrowthRecord & {
  record_type?: 'legacy' | 'growth';
  kind?: 'daily' | 'weekly';
  period?: string;
  week?: string;
  paths?: string[];
  source_cutoff?: string;
  current?: boolean;
  revision_count?: number;
  generation?: GrowthGenerationProvenance;
  manifest?: { generation?: GrowthGenerationProvenance };
};

export type GrowthGenerationProvenance = {
  mode?: 'llm' | 'hybrid' | 'deterministic' | string;
  provider?: string;
  model?: string;
  reason?: string;
  llm_documents?: string[];
  fallback_documents?: string[];
};

export type GrowthDistillationDetail = {
  distillation: GrowthDistillation;
  documents: Record<string, string>;
};

export type GrowthPageDetail = {
  page: GrowthRecord;
  content: string;
  revisions: GrowthRecord[];
  citations: GrowthRecord[];
  backlinks: GrowthLineageEdge[];
};

export type GrowthAssetDetail = {
  kind: GrowthAssetKind;
  record: GrowthRecord;
  content?: string;
  citations?: GrowthRecord[];
  revisions?: GrowthRecord[];
  backlinks?: GrowthLineageEdge[];
  baselines?: Record<string, string>;
  evaluations?: GrowthRecord[];
  feedback?: GrowthRecord[];
  contentDescriptor?: GrowthOutputContent;
  evidence?: GrowthOutputEvidence;
  detailAvailability: 'complete' | 'metadata_only';
  detailMessage?: string;
};

export type GrowthOutputContent = {
  output_id: string;
  mime_type: string;
  content_hash: string;
  byte_size: number;
  vault_path: string;
  render_mode: 'text' | 'binary' | 'oversized_text';
  content: string;
};

export type GrowthOutputEvidence = {
  source_ids: string[];
  page_ids: string[];
};

export type GrowthFeedbackInput = {
  feedback_type: 'accepted' | 'rejected' | 'corrected' | 'rated' | 'reused';
  rating?: number;
  correction?: string;
  comment?: string;
};

export type GrowthOutputEvaluationInput = {
  groundedness: number;
  task_fit: number;
  usefulness: number;
  coherence: number;
  format_quality: number;
  findings: string[];
};

export type GrowthOutputEvidenceInput = {
  source_ids: string[];
  page_ids: string[];
};

export type GrowthMethodReviewInput = {
  comparable_uses?: number;
  average_quality?: number;
  groundedness?: number;
  security_failures?: number;
  regression_failures?: number;
};

export type GrowthMethodDistillationSubmission = {
  run: GrowthRun;
  proposals: GrowthRecord[];
  publication_status: 'proposal_only';
  execution: { execution: 'celery' | 'in_process'; task_id: string };
};

export type GrowthCandidateExtractionSubmission = {
  run: GrowthRun;
  candidates: GrowthRecord[];
  publication_status: 'review_only';
  execution: { execution: 'celery' | 'in_process'; task_id: string; task_name?: string };
};

export type GrowthCandidateReviewInput = {
  decision: 'accepted' | 'rejected';
  review_note?: string;
};

type ApiEnvelope<T> = {
  success?: boolean;
  data?: T;
  detail?: unknown;
  message?: unknown;
  error_code?: string;
};

export class GrowthRequestError extends Error {
  readonly code: string;
  readonly status: number;
  readonly state: Exclude<GrowthRequestState, 'idle' | 'loading' | 'success' | 'empty'>;

  constructor(message: string, code: string, status: number, state?: GrowthRequestError['state']) {
    super(message);
    this.name = 'GrowthRequestError';
    this.code = code;
    this.status = status;
    this.state = state ?? classifyGrowthStatus(status);
  }
}

function classifyGrowthStatus(status: number): GrowthRequestError['state'] {
  if (status === 401 || status === 403) return 'permission';
  if (status === 503) return 'unavailable';
  return 'error';
}

export function classifyGrowthError(reason: unknown): GrowthRequestError {
  if (reason instanceof GrowthRequestError) return reason;
  if (reason instanceof DOMException && reason.name === 'AbortError') {
    return new GrowthRequestError('Request cancelled', 'request_aborted', 0, 'error');
  }
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
  if (offline || reason instanceof TypeError) {
    return new GrowthRequestError(
      'The browser cannot reach the knowledge service. Check the network and retry.',
      'knowledge_growth_offline',
      0,
      'offline',
    );
  }
  return new GrowthRequestError(reason instanceof Error ? reason.message : 'Knowledge growth request failed', 'knowledge_growth_request_failed', 0, 'error');
}

async function request<T>(path: string, signal?: AbortSignal, init: RequestInit = {}): Promise<T> {
  let response: Response;
  let onAbort: (() => void) | undefined;
  try {
    if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
    const responsePromise = apiFetch(path, { ...init, signal });
    if (!signal) response = await responsePromise;
    else {
      const aborted = new Promise<never>((_, reject) => {
        onAbort = () => reject(new DOMException('Request cancelled', 'AbortError'));
        signal.addEventListener('abort', onAbort, { once: true });
      });
      response = await Promise.race([responsePromise, aborted]);
    }
  } catch (reason) {
    throw classifyGrowthError(reason);
  } finally {
    if (signal && onAbort) signal.removeEventListener('abort', onAbort);
  }
  let payload: ApiEnvelope<T> = {};
  try {
    payload = await response.json() as ApiEnvelope<T>;
  } catch {
    payload = {};
  }
  if (!response.ok || !payload.success || payload.data === undefined) {
    const structured = typeof payload.detail === 'object' && payload.detail !== null
      ? payload.detail as { code?: string; message?: string }
      : typeof payload.message === 'object' && payload.message !== null
        ? payload.message as { code?: string; message?: string }
        : undefined;
    const message = structured?.message
      || (typeof payload.detail === 'string' ? payload.detail : '')
      || (typeof payload.message === 'string' ? payload.message : '')
      || (response.status >= 500 ? `Knowledge service returned a server error (${response.status}).` : `Growth request failed (${response.status}).`);
    throw new GrowthRequestError(message, structured?.code || payload.error_code || 'knowledge_growth_request_failed', response.status);
  }
  return payload.data;
}

function encoded(value: string): string {
  return encodeURIComponent(value);
}

function stageRecords(payload: GrowthAssets, stage: GrowthStage): GrowthRecord[] {
  if (Array.isArray(payload.items)) return payload.items;
  if (stage === 'A') return payload.sources ?? [];
  if (stage === 'B') return payload.pages ?? [];
  if (stage === 'C') return payload.methods ?? [];
  if (stage === 'D') return payload.outputs ?? [];
  return [...(payload.candidates ?? []), ...(payload.feedback ?? []), ...(payload.proposals ?? [])];
}

function referenceIds(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item)) : [];
}

export function growthRecordKind(record: GrowthRecord, stage: GrowthStage): GrowthAssetKind {
  if (record.asset_type === 'distillation') return 'distillation';
  if (record.asset_type === 'method_proposal') return 'method_proposal';
  if (record.asset_type === 'candidate') return 'candidate';
  if (record.asset_type === 'wiki_proposal' || record.asset_type === 'proposal') return 'proposal';
  if (record.asset_type === 'feedback') return 'feedback';
  if (stage === 'A') return 'source';
  if (stage === 'B') return 'page';
  if (stage === 'C') return 'method';
  if (stage === 'D') return 'output';
  return Array.isArray(record.operations) || typeof record.operation === 'string' ? 'proposal' : 'feedback';
}

export function setGrowthAccessKey(value: string) {
  fetchWrapper.setAuthToken(value.trim() || undefined);
}

export async function fetchGrowthOverview(projectId: string, signal?: AbortSignal): Promise<GrowthOverview> {
  const project = encoded(projectId);
  const [profile, summary] = await Promise.all([
    request<{ profile: GrowthProfile }>(`/knowledge/growth/${project}/profile`, signal),
    request<GrowthSummary>(`/knowledge/growth/${project}/summary`, signal),
  ]);
  return { profile: profile.profile, summary };
}

export async function updateGrowthProfile(projectId: string, profile: GrowthProfileUpdate, signal?: AbortSignal): Promise<GrowthProfile> {
  const payload = await request<{ profile: GrowthProfile }>(
    `/knowledge/growth/${encoded(projectId)}/profile`,
    signal,
    { method: 'PATCH', body: JSON.stringify(profile) },
  );
  return payload.profile;
}

export async function fetchGrowthAccess(projectId: string, signal?: AbortSignal): Promise<GrowthAccess> {
  const workspace = await request<GrowthAccess>(
    `/knowledge/workspaces/${encoded(projectId)}`,
    signal,
  );
  return {
    ...workspace,
    role: workspace.access?.role || workspace.role || '',
    can_write: workspace.access?.can_write ?? workspace.can_write ?? false,
    features: workspace.features || {},
  };
}

export async function runGrowthWorkspaceJob(
  projectId: string,
  jobType: 'source_sync' | 'horizon_capture',
  signal?: AbortSignal,
): Promise<{ status: string; run_id: string; execution?: string }> {
  return request(
    '/knowledge/runs',
    signal,
    { method: 'POST', body: JSON.stringify({ project_id: projectId, job_type: jobType }) },
  );
}

export async function fetchGrowthRuns(projectId: string, signal?: AbortSignal): Promise<GrowthRun[]> {
  const payload = await request<{ runs: GrowthRun[] }>(
    `/knowledge/growth/${encoded(projectId)}/runs?limit=20`,
    signal,
  );
  return payload.runs;
}

export async function fetchGrowthRunEvents(
  projectId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<{ run: GrowthRun; events: GrowthRunEvent[] }> {
  return request<{ run: GrowthRun; events: GrowthRunEvent[] }>(
    `/knowledge/growth/${encoded(projectId)}/runs/${encoded(runId)}/events?limit=500`,
    signal,
  );
}

export async function fetchGrowthCaptureAttempts(
  projectId: string,
  options: { runId?: string; sourceId?: string } = {},
  signal?: AbortSignal,
): Promise<GrowthCaptureAttempt[]> {
  const query = new URLSearchParams({ limit: '500' });
  if (options.runId) query.set('run_id', options.runId);
  if (options.sourceId) query.set('source_id', options.sourceId);
  const payload = await request<{ capture_attempts: GrowthCaptureAttempt[] }>(
    `/knowledge/growth/${encoded(projectId)}/capture-attempts?${query.toString()}`,
    signal,
  );
  return payload.capture_attempts;
}

export async function fetchGrowthFailures(
  projectId: string,
  options: { runId?: string; status?: string; diagnosticPattern?: GrowthFailure['diagnostic_pattern'] } = {},
  signal?: AbortSignal,
): Promise<GrowthFailure[]> {
  const query = new URLSearchParams({ limit: '500' });
  if (options.runId) query.set('run_id', options.runId);
  if (options.status) query.set('status', options.status);
  if (options.diagnosticPattern) query.set('diagnostic_pattern', options.diagnosticPattern);
  const payload = await request<{ failures: GrowthFailure[] }>(
    `/knowledge/growth/${encoded(projectId)}/failures?${query.toString()}`,
    signal,
  );
  return payload.failures;
}

export async function resolveGrowthFailure(
  projectId: string,
  failureId: string,
  payload: { resolution_note: string; retry_scheduled?: boolean },
): Promise<GrowthFailure> {
  const response = await request<{ failure: GrowthFailure }>(
    `/knowledge/growth/${encoded(projectId)}/failures/${encoded(failureId)}/resolve`,
    undefined,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  );
  return response.failure;
}

export async function startGrowthRun(
  projectId: string,
  jobType: 'growth_daily' | 'growth_weekly_distillation',
  signal?: AbortSignal,
): Promise<GrowthRun> {
  const payload = await request<{ run: GrowthRun }>(
    `/knowledge/growth/${encoded(projectId)}/runs`,
    signal,
    { method: 'POST', body: JSON.stringify({ job_type: jobType }) },
  );
  return payload.run;
}

async function fetchGrowthDistillations(projectId: string, limit: number, signal?: AbortSignal): Promise<{ records: GrowthRecord[]; truncated: boolean }> {
  const boundedLimit = Math.max(1, Math.min(limit, 500));
  const payload = await request<{
    distillations: GrowthDistillation[];
    pagination?: { next_cursor?: string | null };
  }>(`/knowledge/growth/${encoded(projectId)}/distillations?limit=${boundedLimit}`, signal);
  return {
    records: (payload.distillations ?? []).map((item) => ({
      ...item,
      asset_type: 'distillation',
      title: item.title || `${item.kind === 'daily' ? 'Daily' : 'Weekly'} distillation ${item.period || item.week || item.id}`,
      path: item.path || item.paths?.[0] || '',
    })),
    truncated: Boolean(payload.pagination?.next_cursor),
  };
}

export async function fetchLatestGrowthDistillation(
  projectId: string,
  signal?: AbortSignal,
): Promise<GrowthDistillation | null> {
  const payload = await request<{ distillations: GrowthDistillation[] }>(
    `/knowledge/growth/${encoded(projectId)}/distillations?limit=1`,
    signal,
  );
  const record = payload.distillations?.[0];
  if (!record) return null;
  return {
    ...record,
    generation: record.generation ?? record.manifest?.generation,
  };
}

export async function fetchGrowthStage(projectId: string, stage: GrowthStage, limit = 40, signal?: AbortSignal): Promise<GrowthStageResult> {
  const boundedLimit = Math.max(1, Math.min(limit, 500));
  const [payload, distillations] = await Promise.all([
    request<GrowthAssets>(
      `/knowledge/growth/${encoded(projectId)}/assets?stage=${encoded(stage)}&limit=${boundedLimit}`,
      signal,
    ),
    stage === 'review' ? fetchGrowthDistillations(projectId, boundedLimit, signal) : Promise.resolve(null),
  ]);
  const records = stage === 'review'
    ? [...stageRecords(payload, stage), ...(distillations?.records ?? [])]
    : stageRecords(payload, stage);
  const truncated = Array.isArray(payload.items)
    ? Boolean(payload.pagination?.next_cursor)
    : stage === 'review'
      ? (payload.candidates?.length ?? 0) >= boundedLimit || (payload.feedback?.length ?? 0) >= boundedLimit || (payload.proposals?.length ?? 0) >= boundedLimit || Boolean(distillations?.truncated)
      : records.length >= boundedLimit;
  return { project_id: payload.project_id, stage, records, limit: boundedLimit, truncated };
}

export async function fetchGrowthLineage(projectId: string, relation = '', limit = 200, signal?: AbortSignal): Promise<GrowthLineage> {
  const boundedLimit = Math.max(1, Math.min(limit, 500));
  const suffix = relation ? `&relation=${encoded(relation)}` : '';
  const payload = await request<{ project_id: string; edges: GrowthLineageEdge[]; nodes?: GrowthLineageNode[] }>(
    `/knowledge/growth/${encoded(projectId)}/lineage?limit=${boundedLimit}${suffix}`,
    signal,
  );
  return { ...payload, nodes: payload.nodes ?? [], limit: boundedLimit, truncated: payload.edges.length >= boundedLimit };
}

export const fetchGrowthHealth = (projectId: string, signal?: AbortSignal) => request<GrowthHealth>(`/knowledge/health?project_id=${encoded(projectId)}`, signal);
export const fetchGrowthTrend = (projectId: string, signal?: AbortSignal) => request<GrowthTrend>(`/knowledge/health/trend?project_id=${encoded(projectId)}`, signal);

async function fetchGrowthPageDetail(projectId: string, pageId: string, signal?: AbortSignal): Promise<GrowthPageDetail> {
  return request<GrowthPageDetail>(`/knowledge/wiki/pages/${encoded(pageId)}?project_id=${encoded(projectId)}`, signal);
}

async function fetchProposalBaselines(projectId: string, record: GrowthRecord, signal?: AbortSignal): Promise<Record<string, string>> {
  const operations = Array.isArray(record.operations) ? record.operations as Array<{ path?: unknown; operation?: unknown }> : [];
  const paths = [...new Set(operations.map((item) => typeof item.path === 'string' ? item.path : '').filter(Boolean))];
  if (!paths.length) return {};
  const pagesPayload = await request<{ pages: GrowthRecord[] }>(`/knowledge/wiki/pages?project_id=${encoded(projectId)}`, signal);
  const baselines = await Promise.all(paths.map(async (path) => {
    const page = pagesPayload.pages.find((candidate) => candidate.path === path);
    if (!page) return [path, ''] as const;
    const detail = await fetchGrowthPageDetail(projectId, page.id, signal);
    return [path, detail.content] as const;
  }));
  return Object.fromEntries(baselines);
}

export async function fetchGrowthAssetDetail(
  projectId: string,
  stage: GrowthStage,
  assetId: string,
  signal?: AbortSignal,
): Promise<GrowthAssetDetail> {
  const payload = await fetchGrowthStage(projectId, stage, 500, signal);
  const record = payload.records.find((candidate) => candidate.id === assetId)
    ?? (stage === 'C' ? payload.records.find((candidate) => candidate.active_revision_id === assetId) : undefined);
  if (!record) throw new GrowthRequestError('The selected asset no longer exists in this project.', 'knowledge_growth_asset_not_found', 404);
  const kind = growthRecordKind(record, stage);
  if (kind === 'distillation') {
    const detail = await request<GrowthDistillationDetail>(
      `/knowledge/distillations/${encoded(record.id)}?project_id=${encoded(projectId)}`,
      signal,
    );
    const maximumPreviewCharacters = 200_000;
    let remaining = maximumPreviewCharacters;
    let truncated = false;
    const blocks: string[] = [];
    for (const [path, document] of Object.entries(detail.documents ?? {})) {
      const heading = `# ${path.split('/').at(-1) || path}`;
      const body = typeof document === 'string' ? document : '';
      const block = `${heading}\n\n${body}`;
      if (block.length > remaining) {
        blocks.push(block.slice(0, Math.max(0, remaining)));
        truncated = true;
        break;
      }
      blocks.push(block);
      remaining -= block.length + 2;
    }
    return {
      kind,
      record: { ...record, ...detail.distillation, asset_type: 'distillation' },
      content: blocks.join('\n\n'),
      detailAvailability: 'complete',
      detailMessage: truncated ? 'The stored bundle is larger than the bounded Studio preview. Open the managed Vault files for the complete bundle.' : undefined,
    };
  }
  if (kind === 'page') {
    const detail = await fetchGrowthPageDetail(projectId, assetId, signal);
    return { kind, record: { ...record, ...detail.page }, content: detail.content, citations: detail.citations, revisions: detail.revisions, backlinks: detail.backlinks, detailAvailability: 'complete' };
  }
  if (kind === 'proposal') {
    const proposals = await request<{ proposals: GrowthRecord[] }>(`/knowledge/proposals?project_id=${encoded(projectId)}`, signal);
    const fullRecord = proposals.proposals.find((candidate) => candidate.id === record.id);
    if (!fullRecord) throw new GrowthRequestError('The selected proposal no longer exists in this project.', 'knowledge_growth_asset_not_found', 404);
    const merged = { ...record, ...fullRecord };
    const baselines = await fetchProposalBaselines(projectId, merged, signal);
    return { kind, record: merged, baselines, detailAvailability: 'complete' };
  }
  if (kind === 'method_proposal') {
    const detail = await request<{ proposal: GrowthRecord }>(
      `/knowledge/growth/${encoded(projectId)}/methods/proposals/${encoded(record.id)}`,
      signal,
    );
    return {
      kind,
      record: { ...record, ...detail.proposal },
      content: typeof detail.proposal.body === 'string' ? detail.proposal.body : undefined,
      detailAvailability: 'complete',
    };
  }
  if (kind === 'candidate') {
    const detail = await request<{ candidate: GrowthRecord }>(
      `/knowledge/growth/${encoded(projectId)}/candidates/${encoded(record.id)}`,
      signal,
    );
    return { kind, record: { ...record, ...detail.candidate }, detailAvailability: 'complete' };
  }
  if (kind === 'method') {
    const resolved = await request<{ method: GrowthRecord; revision: GrowthRecord | null; evolution_experiments?: GrowthRecord[]; resolution_status: string }>(
      `/knowledge/growth/${encoded(projectId)}/methods/${encoded(record.id)}/resolve`,
      signal,
    );
    if (resolved.revision && resolved.resolution_status === 'available') {
      return {
        kind,
        record: { ...record, ...resolved.method, active_revision: resolved.revision, evolution_experiments: resolved.evolution_experiments ?? [] },
        content: typeof resolved.revision.body === 'string' ? resolved.revision.body : undefined,
        revisions: [resolved.revision],
        detailAvailability: 'complete',
      };
    }
    return { kind, record: { ...record, ...resolved.method, evolution_experiments: resolved.evolution_experiments ?? [] }, detailAvailability: 'metadata_only', detailMessage: 'No published method revision is currently resolvable.' };
  }
  if (kind === 'output') {
    const [outputDetail, contentPayload] = await Promise.all([
      request<{ output: GrowthRecord; evidence?: GrowthOutputEvidence; evaluations: GrowthRecord[]; feedback: GrowthRecord[] }>(
        `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(record.id)}`,
        signal,
      ),
      request<{ content: GrowthOutputContent }>(
        `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(record.id)}/content`,
        signal,
      ),
    ]);
    const descriptor = contentPayload.content;
    const content = descriptor.render_mode === 'text' ? descriptor.content : undefined;
    const detailMessage = descriptor.render_mode === 'binary'
      ? 'This binary output is hash-verified; inline rendering is not available.'
      : descriptor.render_mode === 'oversized_text'
        ? 'This text output exceeds the bounded inline preview size.'
        : undefined;
    return {
      kind,
      record: { ...record, ...outputDetail.output },
      content,
      evaluations: outputDetail.evaluations,
      feedback: outputDetail.feedback,
      evidence: outputDetail.evidence ?? {
        source_ids: referenceIds(outputDetail.output.source_refs),
        page_ids: referenceIds(outputDetail.output.page_refs),
      },
      contentDescriptor: descriptor,
      detailAvailability: content === undefined ? 'metadata_only' : 'complete',
      detailMessage,
    };
  }
  const messages: Record<GrowthAssetKind, string> = {
    source: 'Raw evidence bodies are intentionally excluded from this API; provenance metadata remains available.',
    page: '',
    method: 'No published method revision is currently resolvable.',
    method_proposal: 'The method candidate is available for governed evaluation and publication review.',
    candidate: 'This extracted evidence candidate remains review-only and cannot publish a method or Wiki page.',
    output: 'The governed output descriptor is available, but no verified inline preview was returned.',
    feedback: 'Feedback metadata is complete for this review record.',
    proposal: 'This method proposal body is available in the persisted proposal record.',
    distillation: 'The stored distillation bundle is available in the managed Vault.',
  };
  return { kind, record, detailAvailability: kind === 'feedback' ? 'complete' : 'metadata_only', detailMessage: messages[kind] };
}

export async function triageGrowthSource(projectId: string, sourceId: string, signal?: AbortSignal): Promise<GrowthRecord> {
  const payload = await request<{ triage: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/sources/${encoded(sourceId)}/triage`,
    signal,
    { method: 'POST', body: '{}' },
  );
  return payload.triage;
}

export async function processGrowthFeedback(projectId: string, feedbackId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/knowledge/growth/${encoded(projectId)}/feedback/${encoded(feedbackId)}/process`,
    signal,
    { method: 'POST', body: '{}' },
  );
}

export async function addGrowthOutputFeedback(
  projectId: string,
  outputId: string,
  feedback: GrowthFeedbackInput,
  signal?: AbortSignal,
): Promise<GrowthRecord> {
  const payload = await request<{ feedback: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(outputId)}/feedback`,
    signal,
    { method: 'POST', body: JSON.stringify(feedback) },
  );
  return payload.feedback;
}

export async function evaluateGrowthOutput(
  projectId: string,
  outputId: string,
  evaluation: GrowthOutputEvaluationInput,
  signal?: AbortSignal,
): Promise<GrowthRecord> {
  const payload = await request<{ evaluation: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(outputId)}/evaluate`,
    signal,
    { method: 'POST', body: JSON.stringify(evaluation) },
  );
  return payload.evaluation;
}

export async function linkGrowthOutputEvidence(
  projectId: string,
  outputId: string,
  evidence: GrowthOutputEvidenceInput,
  signal?: AbortSignal,
): Promise<{ output: GrowthRecord; evidence: GrowthOutputEvidence }> {
  const payload = await request<{ output: GrowthRecord; evidence: GrowthOutputEvidence }>(
    `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(outputId)}/evidence`,
    signal,
    { method: 'POST', body: JSON.stringify(evidence) },
  );
  return payload;
}

export async function fileGrowthOutput(projectId: string, outputId: string, signal?: AbortSignal): Promise<GrowthRecord> {
  const payload = await request<{ output: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(outputId)}/file`,
    signal,
    { method: 'POST', body: JSON.stringify({ reason: 'Filed from the Growth workspace after accepted evaluation review.' }) },
  );
  return payload.output;
}

export async function distillGrowthSourceMethods(
  projectId: string,
  sourceId: string,
  candidateIds: string[] = [],
  signal?: AbortSignal,
): Promise<GrowthMethodDistillationSubmission> {
  return request<GrowthMethodDistillationSubmission>(
    `/knowledge/growth/${encoded(projectId)}/methods/distill`,
    signal,
    { method: 'POST', body: JSON.stringify({ source_id: sourceId, candidate_ids: candidateIds }) },
  );
}

export async function extractGrowthSourceCandidates(
  projectId: string,
  sourceId: string,
  signal?: AbortSignal,
): Promise<GrowthCandidateExtractionSubmission> {
  return request<GrowthCandidateExtractionSubmission>(
    `/knowledge/growth/${encoded(projectId)}/candidates/extract`,
    signal,
    { method: 'POST', body: JSON.stringify({ source_id: sourceId }) },
  );
}

export async function reviewGrowthCandidate(
  projectId: string,
  candidateId: string,
  review: GrowthCandidateReviewInput,
  signal?: AbortSignal,
): Promise<GrowthRecord> {
  const payload = await request<{ candidate: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/candidates/${encoded(candidateId)}/review`,
    signal,
    { method: 'POST', body: JSON.stringify(review) },
  );
  return payload.candidate;
}

export async function evaluateGrowthMethodProposal(
  projectId: string,
  proposalId: string,
  review: GrowthMethodReviewInput = {},
  signal?: AbortSignal,
): Promise<GrowthRecord> {
  const payload = await request<{ proposal_id: string; evaluation: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/methods/proposals/${encoded(proposalId)}/review`,
    signal,
    { method: 'POST', body: JSON.stringify(review) },
  );
  return payload.evaluation;
}

export async function publishGrowthMethodProposal(
  projectId: string,
  proposalId: string,
  expectedProfileRevision?: number,
  signal?: AbortSignal,
): Promise<GrowthRecord> {
  const payload = await request<{ method: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/methods/proposals/${encoded(proposalId)}/publish`,
    signal,
    { method: 'POST', body: JSON.stringify({ expected_profile_revision: expectedProfileRevision }) },
  );
  return payload.method;
}

// Kept for callers that still consume the pre-P8 aggregate API.
export async function fetchGrowthSnapshot(projectId: string, signal?: AbortSignal) {
  const [overview, assets, lineage] = await Promise.all([
    fetchGrowthOverview(projectId, signal),
    request<GrowthAssets>(`/knowledge/growth/${encoded(projectId)}/assets?limit=200`, signal),
    fetchGrowthLineage(projectId, '', 500, signal),
  ]);
  return { profile: overview.profile, summary: overview.summary, assets, lineage };
}
