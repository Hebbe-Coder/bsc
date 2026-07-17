export interface CitationCoverage { coverage: number; covered: number; total: number; flagged: string[] }
export interface RiskItem { id: string; title: string; severity: string; linked_constraints: string[]; detail: string }
export interface RiskPayload {
  overall_score: string | null;
  gate: { decision: string; reason: string };
  coverage: { total: number; covered: number; coverage_pct: number; uncovered_ids: string[] };
  risks: RiskItem[];
}
export interface DashboardData {
  session_id: string;
  sop: { sops: any[]; _citation_coverage: CitationCoverage };
  risk: RiskPayload;
  business_model: any;
}

export async function fetchCompilerDashboard(sessionId: string): Promise<DashboardData> {
  const r = await fetch(`/api/orchestrate/dashboard/${encodeURIComponent(sessionId)}`);
  if (!r.ok) {
    if (r.status === 404) throw new Error("session not found");
    throw new Error(`dashboard request failed: ${r.status}`);
  }
  return r.json();
}
