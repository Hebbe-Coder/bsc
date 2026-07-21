import { apiFetch, fetchWrapper } from './fetchWrapper';

export type KnowledgeSource = {
  id: string;
  source_type: string;
  origin: string;
  trust_level: string;
  status: string;
  metadata: Record<string, unknown>;
  captured_at: string;
};

export type KnowledgeWorkspaceData = {
  project_id: string;
  vault: { configured: boolean; status: string };
  sources: number;
  runs: number;
  schedules: number;
};

export type KnowledgeProposal = {
  id: string;
  status: string;
  rationale: string;
  source_ids: string[];
  operations: Array<{ id: string; operation: string; path: string; content: string; source_ids: string[] }>;
  created_at: string;
};

export type KnowledgePage = { id: string; path: string; title: string; page_kind: string; version: number; metadata: Record<string, unknown> };
export type KnowledgePageDetail = { page: KnowledgePage; content: string; citations: Array<{ source_id: string; claim_text: string }>; revisions: Array<Record<string, unknown>> };
export type WeeklyDistillation = { id: string; week: string; knowledge_path: string; content_path: string; context_path: string; source_cutoff: string; status: string };
export type KnowledgeHealth = {
  status: string;
  citation_coverage: number | null;
  orphan_page_ids: string[];
  stale_page_ids: string[];
  uncited_eligible_source_ids: string[];
  pending_proposal_ids: string[];
  dangling_citation_count: number;
};
export type KnowledgeRunEvent = {
  id: string;
  run_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

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
export const fetchKnowledgeRuns = (projectId: string) => request<{ runs: Array<Record<string, unknown>>; count: number }>(`/knowledge/runs?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeRunEvents = (projectId: string, runId: string) => request<{ events: KnowledgeRunEvent[]; count: number }>(`/knowledge/runs/${encodeURIComponent(runId)}/events?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeGraph = (projectId: string) => request<{ edges: Array<{ from_id: string; to_id: string; edge_type: string }>; count: number }>(`/knowledge/wiki/graph?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeSchedules = (projectId: string) => request<{ schedules: Array<Record<string, unknown>>; count: number }>(`/knowledge/schedules?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeHealth = (projectId: string) => request<KnowledgeHealth>(`/knowledge/health?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgeProposals = (projectId: string) => request<{ proposals: KnowledgeProposal[]; count: number }>(`/knowledge/proposals?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePages = (projectId: string) => request<{ pages: KnowledgePage[]; count: number }>(`/knowledge/wiki/pages?project_id=${encodeURIComponent(projectId)}`);
export const fetchKnowledgePage = (projectId: string, pageId: string) => request<KnowledgePageDetail>(`/knowledge/wiki/pages/${encodeURIComponent(pageId)}?project_id=${encodeURIComponent(projectId)}`);
export const fetchWeeklyDistillations = (projectId: string) => request<{ distillations: WeeklyDistillation[]; count: number }>(`/knowledge/distillations?project_id=${encodeURIComponent(projectId)}`);
export const lintKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; valid: boolean; findings: Array<{ code: string; message: string; path: string }> }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/lint?project_id=${encodeURIComponent(projectId)}`, {});
export const publishKnowledgeProposal = (projectId: string, proposalId: string) => post<{ proposal_id: string; status: string; paths: string[]; evaluation_score: number }>(`/knowledge/proposals/${encodeURIComponent(proposalId)}/publish?project_id=${encodeURIComponent(projectId)}`, {});
export const runKnowledgeJob = (projectId: string, jobType: string) => post<{ status: string; run_id: string; execution?: string }>("/knowledge/runs", { project_id: projectId, job_type: jobType });
export const transitionKnowledgeSource = (projectId: string, sourceId: string, status: string) => post<{ source: KnowledgeSource }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/status`, { project_id: projectId, status });
