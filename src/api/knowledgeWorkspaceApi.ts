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

export type KnowledgeWorkspaceData = {
  project_id: string;
  vault: { configured: boolean; status: string; vault_path?: string };
  sources: number;
  runs: number;
  schedules: number;
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
export type KnowledgePageDetail = { page: KnowledgePage; content: string; citations: Array<{ source_id: string; claim_text: string; anchor: string }>; revisions: Array<Record<string, unknown>> };
export type WeeklyDistillation = { id: string; week: string; knowledge_path: string; content_path: string; context_path: string; source_cutoff: string; status: string; created_at: string };
export type WeeklyDistillationDetail = { distillation: WeeklyDistillation; documents: Record<string, string> };
export type KnowledgeRun = { id: string; run_type: string; trigger: string; status: string; error: string; retry_of: string | null; input_refs: Record<string, unknown>; output_refs: Record<string, unknown>; created_at: string; updated_at: string };
export type KnowledgeSchedule = { id: string; job_type: string; cron: string; enabled: number | boolean; timezone: string; last_run_at: string; next_run_at: string };
export type KnowledgeGraphNode = { id: string; node_type: 'source' | 'page' | 'proposal'; label: string; status: string; created_at: string };
export type KnowledgeGraphEdge = { id: string; from_id: string; to_id: string; edge_type: string; created_at: string };
export type KnowledgeGraph = { nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[]; count: number };
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
  evaluations: Array<{ at: string; score: number | null; status: string }>;
  current: KnowledgeHealth;
};
export type KnowledgeRunEvent = { id: string; run_id: string; sequence: number; event_type: string; payload: Record<string, unknown>; created_at: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  const payload = await response.json() as { success?: boolean; data?: T; message?: string; detail?: string };
  if (!response.ok || !payload.success || payload.data === undefined) throw new Error(payload.message || payload.detail || `Knowledge request failed (${response.status})`);
  return payload.data;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function setKnowledgeWorkspaceAccessKey(value: string) {
  fetchWrapper.setAuthToken(value.trim() || undefined);
}

export const fetchKnowledgeWorkspace = (projectId: string) => request<KnowledgeWorkspaceData>(`/knowledge/workspaces/${encodeURIComponent(projectId)}`);
export const fetchKnowledgeSources = (projectId: string) => request<{ sources: KnowledgeSource[]; count: number }>(`/knowledge/sources?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeSource = (projectId: string, sourceId: string) => request<{ source: KnowledgeSource }>(`/knowledge/sources/${encodeURIComponent(sourceId)}?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeRuns = (projectId: string) => request<{ runs: KnowledgeRun[]; count: number }>(`/knowledge/runs?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeRunEvents = (projectId: string, runId: string, afterSequence = 0) => request<{ events: KnowledgeRunEvent[]; count: number }>(`/knowledge/runs/${encodeURIComponent(runId)}/events?project_id=${encodeURIComponent(projectId)}&after_sequence=${afterSequence}`);
export const fetchKnowledgeGraph = (projectId: string, edgeType = '') => request<KnowledgeGraph>(`/knowledge/wiki/graph?project_id=${encodeURIComponent(projectId)}${edgeType ? `&edge_type=${encodeURIComponent(edgeType)}` : ''}`);
export const fetchKnowledgeSchedules = (projectId: string) => request<{ schedules: KnowledgeSchedule[]; count: number }>(`/knowledge/schedules?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeHealth = (projectId: string) => request<KnowledgeHealth>(`/knowledge/health?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeHealthTrend = (projectId: string) => request<KnowledgeHealthTrend>(`/knowledge/health/trend?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeProposals = (projectId: string) => request<{ proposals: KnowledgeProposal[]; count: number }>(`/knowledge/proposals?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePages = (projectId: string) => request<{ pages: KnowledgePage[]; count: number }>(`/knowledge/wiki/pages?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePage = (projectId: string, pageId: string) => request<KnowledgePageDetail>(`/knowledge/wiki/pages/${encodeURIComponent(pageId)}?project_id=${encodeURIComponent(projectId)}`);
export const fetchWeeklyDistillations = (projectId: string) => request<{ distillations: WeeklyDistillation[]; count: number }>(`/knowledge/distillations?project_id=${encodeURIComponent(projectId)}`);
export const fetchWeeklyDistillation = (projectId: string, distillationId: string) => request<WeeklyDistillationDetail>(`/knowledge/distillations/${encodeURIComponent(distillationId)}?project_id=${encodeURIComponent(projectId)}`);
export const configureKnowledgeSchedule = (projectId: string, jobType: string, cron: string, timezone = 'Asia/Shanghai') => post<{ schedule: KnowledgeSchedule }>('/knowledge/schedules', { project_id: projectId, job_type: jobType, cron, timezone });
export const lintKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; valid: boolean; findings: Array<{ code: string; message: string; path: string }> }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/lint?project_id=${encodeURIComponent(projectId)}`, {});
export const publishKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; status: string; paths: string[]; evaluation_score: number }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/publish?project_id=${encodeURIComponent(projectId)}`, {});
export const rejectKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal: KnowledgeProposal }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/reject?project_id=${encodeURIComponent(projectId)}`, {});
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
