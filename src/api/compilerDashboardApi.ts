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
export interface DashboardData {
  session_id: string;
  sop: { sops: any[]; _citation_coverage: CitationCoverage };
  risk: RiskPayload;
  business_model: any;
  trusted_audit: TrustedAudit;
}

export async function fetchCompilerDashboard(sessionId: string): Promise<DashboardData> {
  const r = await fetch(`/api/orchestrate/dashboard/${encodeURIComponent(sessionId)}`);
  if (!r.ok) {
    if (r.status === 404) throw new Error("session not found");
    throw new Error(`dashboard request failed: ${r.status}`);
  }
  return r.json();
}
