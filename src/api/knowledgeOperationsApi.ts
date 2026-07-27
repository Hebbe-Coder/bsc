import { apiFetch } from './fetchWrapper';

export type OperationsMetricState = 'available' | 'insufficient_sample' | 'unavailable';

export type OperationsMetric = {
  key: string;
  state: OperationsMetricState;
  value: number | null;
  unit: string;
  record_count: number;
  reason: string;
};

export type OperationsCoverage = {
  state: OperationsMetricState;
  record_count: number;
  reason: string;
};

export type OperationsAction = {
  id: string;
  project_id: string;
  kind: string;
  severity: string;
  source_refs: string[];
  recommendation: string;
  created_at: string;
  drilldown: { surface: 'knowledge' | 'growth' | 'dbos' | 'operations'; entity_id: string; mission_id: string };
};

export type OperationsFreshness = {
  state: OperationsMetricState;
  latest_activity_at: string | null;
  record_count: number;
  reason: string;
};

export type OperationsProjectSummary = {
  project_id: string;
  project_name: string;
  coverage: OperationsCoverage;
  freshness: OperationsFreshness;
  metrics: {
    asset_count: OperationsMetric;
    verified: OperationsMetric;
    pending_validation: OperationsMetric;
    risk_debt: OperationsMetric;
    durable_references: OperationsMetric;
  };
  highest_priority_action: OperationsAction | null;
};

export type OperationsOverview = {
  generated_at: string;
  state: OperationsMetricState;
  coverage: OperationsCoverage;
  scope: { tenant_id: string; role: string; project_ids: string[]; selected_project_id: string; mode: 'portfolio' | 'project' };
  project_count: number;
  metrics: {
    assets: Record<string, OperationsMetric>;
    quality: Record<string, OperationsMetric>;
    reuse: Record<string, OperationsMetric>;
    agent_evolution: Record<string, OperationsMetric>;
  };
  project_summaries: OperationsProjectSummary[];
  trends: {
    asset_growth: Array<{ date: string; sources: number; methods: number; outputs: number }>;
    agent_evolution: Array<{
      date: string;
      verification_pass_rate: number | null;
      verification_sample_count: number;
      median_execution_attempt: number | null;
      execution_sample_count: number;
      routing_holdout_pass_rate: number | null;
      routing_sample_count: number;
    }>;
  };
  actions: OperationsAction[];
};

export type OperationsGraphNode = {
  id: string;
  domain: 'dbos' | 'growth';
  type: string;
  lane: string;
  label: string;
  status: string;
  created_at: string;
  confidence: number | null;
  drilldown: OperationsAction['drilldown'];
};

export type OperationsGraphEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  domain: 'dbos' | 'growth' | 'cross_domain';
  source_ref: string;
};

export type OperationsGraph = {
  generated_at: string;
  state: OperationsMetricState;
  coverage: OperationsCoverage;
  scope: OperationsOverview['scope'];
  project_id: string;
  mission_id: string;
  lanes: Array<{ id: string; label: string; order: number }>;
  nodes: OperationsGraphNode[];
  edges: OperationsGraphEdge[];
  pagination: { limit: number; next_cursor: string | null; truncated: boolean; omitted_node_count: number; omitted_endpoint_count: number };
  lifecycle_audit: {
    scope: 'filtered_graph' | 'visible_page';
    risk_node_count: number;
    complete_risk_lineage_count: number;
    missing_lanes: string[];
    reason: string;
  };
};

export type OperationsQuery = {
  from?: string;
  to?: string;
  missionId?: string;
  nodeTypes?: string[];
  statuses?: string[];
  relations?: string[];
  limit?: number;
  cursor?: string;
};

export class OperationsRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'OperationsRequestError';
    this.code = code;
    this.status = status;
  }
}

function queryString(query: OperationsQuery): string {
  const params = new URLSearchParams();
  if (query.from) params.set('from', query.from);
  if (query.to) params.set('to', query.to);
  if (query.missionId) params.set('mission_id', query.missionId);
  for (const value of query.nodeTypes ?? []) params.append('node_type', value);
  for (const value of query.statuses ?? []) params.append('status', value);
  for (const value of query.relations ?? []) params.append('relation', value);
  if (query.limit) params.set('limit', String(query.limit));
  if (query.cursor) params.set('cursor', query.cursor);
  const text = params.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string): Promise<T> {
  const response = await apiFetch(path, { method: 'GET', skipRetry: true });
  const payload = await response.json() as {
    success?: boolean;
    data?: T;
    message?: string | { code?: string; message?: string };
    detail?: string | { code?: string; message?: string };
    error_code?: string;
  };
  if (!response.ok || !payload.success || payload.data === undefined) {
    const detail = typeof payload.detail === 'object' ? payload.detail : typeof payload.message === 'object' ? payload.message : null;
    const message = detail?.message || (typeof payload.message === 'string' ? payload.message : '') || (typeof payload.detail === 'string' ? payload.detail : '') || `Operations request failed (${response.status})`;
    throw new OperationsRequestError(message, detail?.code || payload.error_code || 'operations_request_failed', response.status);
  }
  return payload.data;
}

export function fetchOperationsPortfolio(query: Pick<OperationsQuery, 'from' | 'to'> = {}) {
  return request<OperationsOverview>(`/knowledge/operations/portfolio${queryString(query)}`);
}

export function fetchOperationsProject(projectId: string, query: Pick<OperationsQuery, 'from' | 'to'> = {}) {
  return request<OperationsOverview>(`/knowledge/operations/projects/${encodeURIComponent(projectId)}${queryString(query)}`);
}

export function fetchOperationsGraph(projectId: string, query: OperationsQuery = {}) {
  return request<OperationsGraph>(`/knowledge/operations/projects/${encodeURIComponent(projectId)}/graph${queryString(query)}`);
}
