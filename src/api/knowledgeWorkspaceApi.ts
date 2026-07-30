import { apiFetch, fetchWrapper } from './fetchWrapper';

export type KnowledgeSource = {
  id: string;
  project_id: string;
  source_type: string;
  origin: string;
  vault_path: string;
  content_hash: string;
  trust_level: string;
  status: string;
  metadata: Record<string, unknown>;
  supersedes_id: string | null;
  captured_at: string;
};

export type KnowledgeSourceTriage = {
  id: string;
  project_id: string;
  source_id: string;
  profile_revision: number;
  relevance: number;
  value: number;
  freshness: number;
  outputability: number;
  connectedness: number;
  priority: number;
  reliability_pass: number | boolean;
  disposition: string;
  reasons: string[];
  evaluator_revision: string;
  evaluator_status: 'completed' | 'unavailable' | 'failed';
  latency_ms: number;
  created_at: string;
};

export type KnowledgeWorkspaceData = {
  project_id: string;
  vault: {
    configured: boolean;
    status: string;
    vault_path?: string;
    connection?: {
      state: 'unconfigured' | 'unavailable' | 'mapped_uninitialized' | 'mapped_incomplete' | 'ready';
      message: string;
      missing_managed_files?: string[];
      missing_managed_directories?: string[];
    };
  };
  plugins: { configured: boolean; supported_adapters: string[]; plugins: Array<{ id: string; name: string; adapter: 'filesystem_drop' | 'filesystem_output' | 'filesystem_context'; input_paths: string[]; trust_state: 'trusted' | 'untrusted' | 'configuration_changed' | 'unavailable'; trusted_at: string; trust_actor: string; path_status: 'ready' | 'missing' | 'unavailable' | 'unverified'; runtime_configuration?: { state: 'configured' | 'interactive_destination' | 'declared_only' | 'mismatch' | 'unavailable' | 'unverified'; detail_code: string }; status: 'awaiting_export' | 'captured' | 'awaiting_output' | 'registered_output' | 'awaiting_trust' | 'trust_stale' | 'trust_unavailable'; capture_state?: 'awaiting_trust' | 'trust_stale' | 'trust_unavailable' | 'captured' | 'registered_output' | 'ready_for_first_export' | 'ready_for_first_output' | 'files_detected_pending_capture' | 'files_detected_pending_registration' | 'route_unavailable'; export_observation?: { state: 'empty' | 'files_detected' | 'file_limit_reached' | 'unavailable'; file_count: number; latest_modified_at: string }; captured_sources: number; registered_outputs: number; last_captured_at: string; last_registered_at: string }>; errors: string[] };
  sources: number;
  runs: number;
  schedules: number;
  access: { role: string; can_write: boolean };
  features: {
    wiki: boolean;
    obsidian_sync: boolean;
    schedules: boolean;
    mcp_write: boolean;
    horizon: boolean;
    automatic_publication: boolean;
  };
  sync: { status: string; last_run: KnowledgeRun | null };
  horizon?: {
    enabled: boolean;
    captured_sources: number;
    last_run: {
      id: string;
      status: string;
      updated_at: string;
      horizon_run_id: string;
      stage: string;
      source_mode: string;
      accepted: number;
      created: number;
      duplicates: number;
      rejected: number;
      skipped: boolean;
      outcome: 'processed' | 'empty_result' | 'no_new_artifact' | 'channel_error' | 'configuration_error' | 'producer_failure' | 'stale_artifact' | 'failed';
      items_observed: number;
      failure: { category: string; code: string; retryable: boolean } | null;
    } | null;
  };
  growth?: {
    status: string;
    last_run: KnowledgeRun | null;
    sync: {
      status: string;
      sources: { created: number; duplicates: number };
      outputs: { registered: number; duplicates: number };
      triage: { evaluated: number; eligible: number; pending_review: number };
    } | null;
  };
  scheduler: { available: boolean; mode: 'celery' | 'manual' };
};
export type KnowledgePluginBridge = { id: string; name: string; adapter?: 'filesystem_drop' | 'filesystem_output' | 'filesystem_context'; input_paths: string[] };
export type KnowledgeWorkspaceProject = { id: string; name: string; created_at: string };
export type FeishuKnowledgeExport = {
  document_id: string;
  revision_id: string;
  document_type: 'document' | 'minutes' | 'doc' | 'docx' | 'meeting' | 'meeting_minutes';
  source_url: string;
  title: string;
  content?: string;
  source_time?: string;
  attachments?: Array<Record<string, unknown>>;
};
export type FeishuKnowledgeImport = { source: KnowledgeSource; created: boolean; run_id: string };
export type PrimaryWebKnowledgeCapture = { source: KnowledgeSource; created: boolean; run_id: string };
export type KnowledgeEvaluationCaseInput = {
  case_id: string;
  case_type: 'retrieval' | 'citation' | 'sop' | 'content';
  expected: { constraints?: string[]; require_citations?: boolean; source_ids?: string[] };
};

export type KnowledgeProposal = {
  id: string;
  status: string;
  rationale: string;
  source_ids: string[];
  operations: Array<{ id: string; operation: string; path: string; destination_path?: string; content: string; source_ids: string[] }>;
  eval_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type KnowledgePage = { id: string; path: string; title: string; page_kind: string; version: number; status: string; metadata: Record<string, unknown> };
export type KnowledgePageRevision = { id: string; version: number; content_hash: string; proposal_id: string; created_at: string };
export type KnowledgePageDetail = { page: KnowledgePage; content: string; citations: Array<{ source_id: string; claim_text: string; anchor: string }>; revisions: KnowledgePageRevision[]; backlinks: KnowledgeGraphEdge[] };
export type WeeklyDistillation = {
  id: string;
  project_id: string;
  week: string;
  knowledge_path: string;
  content_path: string;
  context_path: string;
  source_cutoff: string;
  status: string;
  created_at: string;
  record_type?: 'legacy' | 'growth';
  kind?: 'daily' | 'weekly';
  period?: string;
  paths?: string[];
  current?: boolean;
  revision_count?: number;
  manifest?: Record<string, unknown>;
  generation?: Record<string, unknown>;
};
export type WeeklyDistillationDetail = { distillation: WeeklyDistillation; documents: Record<string, string> };
export type KnowledgeRun = { id: string; run_type: string; trigger: string; status: string; error: string; retry_of: string | null; input_refs: Record<string, unknown>; output_refs: Record<string, unknown>; created_at: string; updated_at: string };
export type KnowledgeSchedule = { id: string; job_type: string; cron: string; enabled: number | boolean; timezone: string; last_run_at: string; next_run_at: string; scheduler_available: boolean; last_result: KnowledgeRun | null };
export type KnowledgeGraphNode = { id: string; node_type: 'source' | 'page' | 'proposal'; label: string; status: string; created_at: string };
export type KnowledgeGraphEdge = { id: string; from_id: string; to_id: string; edge_type: string; created_at: string };
export type KnowledgeGraph = { nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[]; count: number; total: number; limit: number; offset: number; truncated: boolean };
export type KnowledgeHealth = {
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
export type KnowledgeHealthTrend = {
  source_throughput: Array<{ date: string; count: number }>;
  proposal_outcomes: Array<{ date: string; statuses: Record<string, number> }>;
  evaluations: Array<{ at: string; score: number | null; baseline_score: number | null; score_delta: number | null; latency_ms: number | null; status: string }>;
  current: KnowledgeHealth;
};
export type KnowledgeRunEvent = { id: string; project_id: string; run_id: string; sequence: number; event_type: string; payload: Record<string, unknown>; created_at: string };
export type KnowledgeEvidenceRecord = {
  id: string;
  record_type: 'source' | 'asset' | 'extraction' | 'table' | 'reference';
  source_id?: string;
  status?: string;
  access_state?: string;
  created_at?: string;
  captured_at?: string;
  [key: string]: unknown;
};
export type KnowledgeEvidenceData = {
  project_id: string;
  state: 'available' | 'no_sample';
  summary: { sources: number; assets: number; extractions: Record<string, number>; tables: number; references: number; source_statuses: Record<string, number>; denominator: number };
  capabilities: Record<string, { state: 'available' | 'unavailable'; detail: string }>;
  sources: KnowledgeEvidenceRecord[];
  assets: KnowledgeEvidenceRecord[];
  extractions: KnowledgeEvidenceRecord[];
  tables: KnowledgeEvidenceRecord[];
  references: KnowledgeEvidenceRecord[];
  timeline: Array<{ id: string; record_type: KnowledgeEvidenceRecord['record_type']; status: string; occurred_at: string }>;
  graph: { nodes: Array<{ id: string; type: string; status: string; label?: string; target_type?: string; target_id?: string }>; edges: Array<{ id: string; source: string; target: string; relation: string; resolution_state?: string }>; node_total: number; edge_total: number; omitted_edge_count: number; truncated: boolean };
  truncated: boolean;
};
export type KnowledgeTablePreview = {
  table_id: string;
  source_id: string;
  extraction_id: string;
  schema: string[];
  units: Record<string, string>;
  rows: string[][];
  page: number;
  page_size: number;
  total_rows: number;
  available_rows: number;
  total_pages: number;
  truncated: boolean;
  derived: true;
  state: 'available' | 'no_rows' | 'unavailable';
  reason: string;
  provenance: { extractor: string; extractor_revision: string; sheet: string; content_hash: string };
};
export type InformationRegistrySource = {
  id: string;
  project_id: string;
  name: string;
  connector_type: 'rss' | 'youtube_channel_rss' | 'x' | 'reddit' | 'youtube_data' | 'tiktok';
  feed_url: string;
  channel_id: string;
  topics: string[];
  languages: string[];
  freshness_hours: number;
  retention_days: number;
  authority_tier: 'primary' | 'trusted' | 'community' | 'untrusted';
  enabled: number | boolean;
  availability: 'available' | 'unavailable';
  unavailable_reason: string;
  created_at: string;
  updated_at: string;
};
export type InformationSignalReceipt = {
  id: string;
  project_id: string;
  batch_id: string;
  registry_id: string;
  external_id: string;
  canonical_url: string;
  source_id: string;
  disposition: 'captured' | 'lead_only' | 'rejected';
  reason: string;
  metadata: Record<string, unknown>;
  created_at: string;
};
export type KnowledgeInformationOverview = {
  state: 'ready' | 'no_sources';
  source_registry: InformationRegistrySource[];
  receipts: InformationSignalReceipt[];
  runs: KnowledgeRun[];
  counts: {
    sources: number;
    available_sources: number;
    unavailable_sources: number;
    captured: number;
    new_sources: number;
    duplicate_sources: number;
    lead_only: number;
    rejected: number;
  };
};

export class KnowledgeRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'KnowledgeRequestError';
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  const payload = await response.json() as {
    success?: boolean;
    data?: T;
    message?: string | { code?: string; message?: string };
    detail?: string | { code?: string; message?: string };
    error_code?: string;
  };
  if (!response.ok || !payload.success || payload.data === undefined) {
    const detail = typeof payload.detail === 'object' ? payload.detail : typeof payload.message === 'object' ? payload.message : null;
    const message = detail?.message || (typeof payload.message === 'string' ? payload.message : '') || (typeof payload.detail === 'string' ? payload.detail : '') || `Knowledge request failed (${response.status})`;
    throw new KnowledgeRequestError(message, detail?.code || payload.error_code || 'knowledge_request_failed', response.status);
  }
  return payload.data;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function setKnowledgeWorkspaceAccessKey(value: string) {
  fetchWrapper.setAuthToken(value.trim() || undefined);
}

export const fetchKnowledgeWorkspace = (projectId: string) => request<KnowledgeWorkspaceData>(`/knowledge/workspaces/${encodeURIComponent(projectId)}`);
export const fetchKnowledgeWorkspaceProjects = () => request<{ projects: KnowledgeWorkspaceProject[]; count: number }>('/knowledge/workspaces');
export const fetchKnowledgeEvidence = (projectId: string, limit = 100) => request<KnowledgeEvidenceData>(`/knowledge/evidence/projects/${encodeURIComponent(projectId)}?limit=${Math.max(1, Math.min(limit, 200))}`);
export const fetchKnowledgeEvidenceRecord = (projectId: string, recordType: string, recordId: string) => request<{ record: KnowledgeEvidenceRecord }>(`/knowledge/evidence/projects/${encodeURIComponent(projectId)}/records/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}`);
export const fetchKnowledgeTablePreview = (projectId: string, tableId: string, page = 1, pageSize = 25) => request<KnowledgeTablePreview>(`/knowledge/evidence/projects/${encodeURIComponent(projectId)}/tables/${encodeURIComponent(tableId)}/preview?page=${Math.max(1, page)}&page_size=${Math.max(1, Math.min(pageSize, 100))}`);
export async function fetchKnowledgeImageThumbnail(projectId: string, assetId: string): Promise<string> {
  const response = await fetchWrapper.request(`/knowledge/evidence/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/thumbnail`);
  if (!response.ok) throw new KnowledgeRequestError('An authorized image preview is unavailable.', 'evidence_image_preview_unavailable', response.status);
  return URL.createObjectURL(await response.blob());
}
export const fetchKnowledgeInformationOverview = (projectId: string) => request<KnowledgeInformationOverview>(`/knowledge/intelligence/projects/${encodeURIComponent(projectId)}`);
export const createKnowledgeInformationSource = (projectId: string, source: Omit<InformationRegistrySource, 'id' | 'created_at' | 'updated_at' | 'availability' | 'unavailable_reason'>) => post<{ source: InformationRegistrySource }>(`/knowledge/intelligence/projects/${encodeURIComponent(projectId)}/sources`, source);
export const configureKnowledgeVault = (projectId: string, vaultPath: string) => request<{ vault: KnowledgeWorkspaceData['vault'] }>(`/knowledge/workspaces/${encodeURIComponent(projectId)}/vault`, { method: 'PUT', body: JSON.stringify({ vault_path: vaultPath }) });
export const configureKnowledgePlugins = (projectId: string, plugins: KnowledgePluginBridge[]) => request<KnowledgeWorkspaceData['plugins']>(`/knowledge/workspaces/${encodeURIComponent(projectId)}/plugins`, { method: 'PUT', body: JSON.stringify({ plugins }) });
export const setKnowledgePluginTrust = (projectId: string, pluginIds: string[], trusted: boolean, reason = '') => request<KnowledgeWorkspaceData['plugins']>(`/knowledge/workspaces/${encodeURIComponent(projectId)}/plugins/trust`, { method: 'PUT', body: JSON.stringify({ plugin_ids: pluginIds, trusted, reason }) });
export const initializeKnowledgeWorkspace = (projectId: string) => post<{ created: string[]; created_directories?: string[]; indexing: Record<string, unknown>; run_id: string }>(`/knowledge/workspaces/${encodeURIComponent(projectId)}/initialize`, {});
export const fetchKnowledgeSources = (projectId: string) => request<{ sources: KnowledgeSource[]; count: number }>(`/knowledge/sources?project_id=${encodeURIComponent(projectId)}`);
export const captureKnowledgePrimaryWebSource = (projectId: string, url: string, discoveredFromSourceId: string) => post<PrimaryWebKnowledgeCapture>('/knowledge/sources/capture-web', {
  project_id: projectId,
  url,
  discovered_from_source_id: discoveredFromSourceId,
});
export const importFeishuKnowledgeExport = (projectId: string, exportPayload: FeishuKnowledgeExport) => post<FeishuKnowledgeImport>('/knowledge/sources/feishu/import', { project_id: projectId, export: exportPayload });
export const fetchKnowledgeSource = (projectId: string, sourceId: string) => request<{ source: KnowledgeSource }>(`/knowledge/sources/${encodeURIComponent(sourceId)}?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeSourceTriage = (projectId: string, sourceId: string) => request<{ triage: KnowledgeSourceTriage | null }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/triage?project_id=${encodeURIComponent(projectId)}`);
export const semanticTriageKnowledgeSource = (projectId: string, sourceId: string) => post<{ source: KnowledgeSource; triage: KnowledgeSourceTriage; admission: 'explicit_approval_required' }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/semantic-triage?project_id=${encodeURIComponent(projectId)}`, {});
export const fetchKnowledgeRuns = (projectId: string) => request<{ runs: KnowledgeRun[]; count: number }>(`/knowledge/runs?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeRunEvents = (projectId: string, runId: string, afterSequence = 0) => request<{ events: KnowledgeRunEvent[]; count: number }>(`/knowledge/runs/${encodeURIComponent(runId)}/events?project_id=${encodeURIComponent(projectId)}&after_sequence=${afterSequence}`);
export const fetchKnowledgeGraph = (projectId: string, edgeType = '') => request<KnowledgeGraph>(`/knowledge/wiki/graph?project_id=${encodeURIComponent(projectId)}${edgeType ? `&edge_type=${encodeURIComponent(edgeType)}` : ''}`);
export const fetchKnowledgeSchedules = (projectId: string) => request<{ schedules: KnowledgeSchedule[]; count: number }>(`/knowledge/schedules?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeHealth = (projectId: string) => request<KnowledgeHealth>(`/knowledge/health?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeHealthTrend = (projectId: string) => request<KnowledgeHealthTrend>(`/knowledge/health/trend?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeProposals = (projectId: string) => request<{ proposals: KnowledgeProposal[]; count: number }>(`/knowledge/proposals?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePages = (projectId: string) => request<{ pages: KnowledgePage[]; count: number }>(`/knowledge/wiki/pages?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePage = (projectId: string, pageId: string) => request<KnowledgePageDetail>(`/knowledge/wiki/pages/${encodeURIComponent(pageId)}?project_id=${encodeURIComponent(projectId)}`);
export const restoreKnowledgePageRevision = (projectId: string, pageId: string, revisionId: string) => post<{ proposal: KnowledgeProposal }>(`/knowledge/wiki/pages/${encodeURIComponent(pageId)}/revisions/${encodeURIComponent(revisionId)}/restore?project_id=${encodeURIComponent(projectId)}`, {});
export const fetchWeeklyDistillations = (projectId: string, includeHistory = false) => request<{ distillations: WeeklyDistillation[]; count: number }>(`/knowledge/distillations?project_id=${encodeURIComponent(projectId)}${includeHistory ? '&include_history=true' : ''}`);
export const fetchWeeklyDistillation = (projectId: string, distillationId: string) => request<WeeklyDistillationDetail>(`/knowledge/distillations/${encodeURIComponent(distillationId)}?project_id=${encodeURIComponent(projectId)}`);
export const configureKnowledgeSchedule = (projectId: string, jobType: string, cron: string, timezone = 'Asia/Shanghai') => post<{ schedule: KnowledgeSchedule }>('/knowledge/schedules', { project_id: projectId, job_type: jobType, cron, timezone });
export const lintKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; valid: boolean; findings: Array<{ code: string; message: string; path: string }> }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/lint?project_id=${encodeURIComponent(projectId)}`, {});
export const publishKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; status: string; paths: string[]; evaluation_score: number }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/publish?project_id=${encodeURIComponent(projectId)}`, {});
export const rejectKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal: KnowledgeProposal }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/reject?project_id=${encodeURIComponent(projectId)}`, {});
export const saveKnowledgeEvaluationCase = (projectId: string, evaluationCase: KnowledgeEvaluationCaseInput) => post<{ eval_case: { case_id: string; case_type: string; expected: Record<string, unknown> } }>('/knowledge/eval-cases', { project_id: projectId, ...evaluationCase });
export const runKnowledgeJob = (projectId: string, jobType: string) => post<{ status: string; run_id: string; execution?: string }>("/knowledge/runs", { project_id: projectId, job_type: jobType });
export const retryKnowledgeRun = (projectId: string, runId: string) => post<{ status: string; run_id: string; execution?: string }>(`/knowledge/runs/${encodeURIComponent(runId)}/retry?project_id=${encodeURIComponent(projectId)}`, {});
export const transitionKnowledgeSource = (projectId: string, sourceId: string, status: string) => post<{ source: KnowledgeSource }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/status`, { project_id: projectId, status });
export const setKnowledgeScheduleState = (projectId: string, scheduleId: string, enabled: boolean) => request<{ schedule: KnowledgeSchedule }>(`/knowledge/schedules/${encodeURIComponent(scheduleId)}`, { method: 'PATCH', body: JSON.stringify({ project_id: projectId, enabled }) });

export async function streamKnowledgeRunEvents(
  projectId: string,
  runId: string,
  afterSequence: number,
  signal: AbortSignal,
  onEvent: (event: KnowledgeRunEvent) => void,
): Promise<void> {
  const response = await apiFetch(`/knowledge/runs/${encodeURIComponent(runId)}/events/stream?project_id=${encodeURIComponent(projectId)}&after_sequence=${afterSequence}`, {
    headers: { Accept: 'text/event-stream' }, signal,
  });
  if (!response.ok || !response.body) throw new Error(`Knowledge event stream failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const messages = buffer.split('\n\n');
    buffer = messages.pop() || '';
    for (const message of messages) {
      const dataLine = message.split('\n').find((line) => line.startsWith('data:'));
      if (!dataLine) continue;
      try { onEvent(JSON.parse(dataLine.slice(5).trim()) as KnowledgeRunEvent); } catch { /* Ignore malformed transport frames. */ }
    }
  }
}
