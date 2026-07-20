export interface CitationCoverage { coverage: number; covered: number; total: number; flagged: string[] }
export interface RiskItem { id: string; title: string; severity: string; linked_constraints: string[]; detail: string }
export interface RiskPayload {
  overall_score: string | null;
  gate: { decision: string; reason: string };
  coverage: { total: number; covered: number; coverage_pct: number; uncovered_ids: string[] };
  risks: RiskItem[];
}
export interface AuditEntry {
  seq: number;
  agent: string;
  action: string;
  input_hash: string;
  output_hash: string;
  hash: string;
  prev_hash: string;
  timestamp: string;
}
export interface TrustedAudit {
  source_refs: string[];
  coverage: {
    coverage_pct: number | null;
    covered: number | null;
    total: number | null;
    uncovered_ids: string[];
    gate_decision: string | null;
  };
  audit: AuditEntry[];
  chain_hash: string;
  verified: boolean;
}
export interface QualityDimension {
  name: string;
  score: number;
  max_score: number;
  weight: number;
  feedback: string;
  details: string;
}
export interface Evaluation {
  overall_score: number;
  dimensions: QualityDimension[];
  summary: string;
  suggestions: string[];
  is_passed: boolean;
  improvement_points: number;
}
export interface EvolutionFeedback {
  trace_id: string;
  user_id: string;
  feedback_type: string;
  query: string;
  answer: string;
  comment: string | null;
  timestamp: number;
  processed: boolean;
}
export interface EvolutionStats {
  total: number;
  by_type: { thumbs_up: number; thumbs_down: number; correction: number; comment: number };
  by_user: Record<string, number>;
  positive_rate: number;
}
export interface Evolution {
  recent_feedback: EvolutionFeedback[];
  stats: EvolutionStats;
}
export interface CapabilityExecutionAttempt {
  attempt: number;
  outcome: string;
  elapsed_ms: number;
  error_code: string;
  error: string;
  retryable: boolean;
}

export interface PromptContextUsage {
  max_tokens: number;
  estimated_tokens: number;
  template_tokens: number;
  input_tokens: number;
  artifact_tokens: number;
  artifacts_available: number;
  artifacts_included: number;
  artifacts_omitted: number;
  artifacts_truncated: number;
  input_truncated: boolean;
}

export interface ModelUsage {
  provider: string;
  model: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cached_tokens: number | null;
  reasoning_tokens: number | null;
  reported: boolean;
  complete: boolean;
}

export interface CapabilityExecutionMetadata {
  capability_name: string;
  status: string;
  artifacts_produced: string[];
  error: string;
  error_code: string;
  elapsed_ms: number;
  backend: string;
  mode: string;
  retries: number;
  attempts: CapabilityExecutionAttempt[];
  prompt_context: PromptContextUsage | null;
  model_usage: ModelUsage | null;
}

export interface ExecutionMetadata {
  status: string;
  degraded: boolean;
  stage_modes: Record<string, string>;
  capability_executions: CapabilityExecutionMetadata[];
}
export interface DashboardData {
  session_id: string;
  execution?: ExecutionMetadata;
  sop: { sops: any[]; _citation_coverage: CitationCoverage };
  risk: RiskPayload;
  business_model: any;
  trusted_audit: TrustedAudit;
  evaluation: Evaluation;
  evolution: Evolution;
}

export async function fetchCompilerDashboard(sessionId: string): Promise<DashboardData> {
  const r = await apiFetch(`/api/orchestrate/dashboard/${encodeURIComponent(sessionId)}`);
  if (!r.ok) {
    if (r.status === 404) throw new Error("session not found");
    throw new Error(`dashboard request failed: ${r.status}`);
  }
  return r.json();
}
import { apiFetch } from './fetchWrapper';
