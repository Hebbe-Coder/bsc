import { apiFetch, fetchWrapper } from './fetchWrapper';

export type GrowthStage = 'A' | 'B' | 'C' | 'D' | 'review';
export type GrowthAssetKind = 'source' | 'page' | 'method' | 'output' | 'feedback' | 'proposal';
export type GrowthRequestState = 'idle' | 'loading' | 'success' | 'empty' | 'permission' | 'offline' | 'unavailable' | 'error';

export type GrowthProfile = {
  project_id: string;
  revision?: number;
  user_role?: string;
  research_domains?: string[];
  content_voice?: string;
  evidence_threshold?: number;
  automatic_publication_policy?: string;
  method_promotion_policy?: string;
  [key: string]: unknown;
};

export type GrowthCounts = {
  sources: number;
  eligible_sources: number;
  pages: number;
  methods: number;
  published_methods: number;
  outputs: number;
  accepted_outputs: number;
  rejected_outputs: number;
  feedback: number;
  wiki_proposals?: number;
  review_records?: number;
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

export type GrowthLineage = {
  project_id: string;
  edges: GrowthLineageEdge[];
  limit: number;
  truncated: boolean;
};

export type GrowthAccess = {
  role: string;
  can_write: boolean;
  features: Record<string, boolean>;
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

export type GrowthFeedbackInput = {
  feedback_type: 'accepted' | 'rejected' | 'corrected' | 'rated' | 'reused';
  rating?: number;
  correction?: string;
  comment?: string;
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
  return [...(payload.feedback ?? []), ...(payload.proposals ?? [])];
}

export function growthRecordKind(record: GrowthRecord, stage: GrowthStage): GrowthAssetKind {
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

export async function fetchGrowthAccess(projectId: string, signal?: AbortSignal): Promise<GrowthAccess> {
  const workspace = await request<{ access: { role: string; can_write: boolean }; features: Record<string, boolean> }>(
    `/knowledge/workspaces/${encoded(projectId)}`,
    signal,
  );
  return { role: workspace.access.role, can_write: workspace.access.can_write, features: workspace.features };
}

export async function fetchGrowthStage(projectId: string, stage: GrowthStage, limit = 40, signal?: AbortSignal): Promise<GrowthStageResult> {
  const boundedLimit = Math.max(1, Math.min(limit, 500));
  const payload = await request<GrowthAssets>(
    `/knowledge/growth/${encoded(projectId)}/assets?stage=${encoded(stage)}&limit=${boundedLimit}`,
    signal,
  );
  const records = stageRecords(payload, stage);
  const truncated = Array.isArray(payload.items)
    ? Boolean(payload.pagination?.next_cursor)
    : stage === 'review'
      ? (payload.feedback?.length ?? 0) >= boundedLimit || (payload.proposals?.length ?? 0) >= boundedLimit
      : records.length >= boundedLimit;
  return { project_id: payload.project_id, stage, records, limit: boundedLimit, truncated };
}

export async function fetchGrowthLineage(projectId: string, relation = '', limit = 200, signal?: AbortSignal): Promise<GrowthLineage> {
  const boundedLimit = Math.max(1, Math.min(limit, 500));
  const suffix = relation ? `&relation=${encoded(relation)}` : '';
  const payload = await request<{ project_id: string; edges: GrowthLineageEdge[] }>(
    `/knowledge/growth/${encoded(projectId)}/lineage?limit=${boundedLimit}${suffix}`,
    signal,
  );
  return { ...payload, limit: boundedLimit, truncated: payload.edges.length >= boundedLimit };
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
  if (kind === 'method') {
    const resolved = await request<{ method: GrowthRecord; revision: GrowthRecord | null; resolution_status: string }>(
      `/knowledge/growth/${encoded(projectId)}/methods/${encoded(record.id)}/resolve`,
      signal,
    );
    if (resolved.revision && resolved.resolution_status === 'available') {
      return {
        kind,
        record: { ...record, ...resolved.method, active_revision: resolved.revision },
        content: typeof resolved.revision.body === 'string' ? resolved.revision.body : undefined,
        revisions: [resolved.revision],
        detailAvailability: 'complete',
      };
    }
    return { kind, record: { ...record, ...resolved.method }, detailAvailability: 'metadata_only', detailMessage: 'No published method revision is currently resolvable.' };
  }
  if (kind === 'output') {
    const [outputDetail, contentPayload] = await Promise.all([
      request<{ output: GrowthRecord; evaluations: GrowthRecord[]; feedback: GrowthRecord[] }>(
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
      contentDescriptor: descriptor,
      detailAvailability: content === undefined ? 'metadata_only' : 'complete',
      detailMessage,
    };
  }
  const messages: Record<GrowthAssetKind, string> = {
    source: 'Raw evidence bodies are intentionally excluded from this API; provenance metadata remains available.',
    page: '',
    method: 'No published method revision is currently resolvable.',
    output: 'The governed output descriptor is available, but no verified inline preview was returned.',
    feedback: 'Feedback metadata is complete for this review record.',
    proposal: 'This method proposal body is available in the persisted proposal record.',
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

export async function fileGrowthOutput(projectId: string, outputId: string, signal?: AbortSignal): Promise<GrowthRecord> {
  const payload = await request<{ output: GrowthRecord }>(
    `/knowledge/growth/${encoded(projectId)}/outputs/${encoded(outputId)}/file`,
    signal,
    { method: 'POST', body: JSON.stringify({ reason: 'Filed from the Growth workspace after accepted evaluation review.' }) },
  );
  return payload.output;
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
