import type { AgentAnalysisResponse } from '../api/agentOsApi';
import type { DashboardData, RiskItem, RiskPayload, TrustedAudit, Evaluation, QualityDimension, CitationCoverage } from '../api/compilerDashboardApi';

export function adaptAgentOsToDashboard(resp: AgentAnalysisResponse): DashboardData {
  // Artifact exports are intentionally extensible; normalize them at the UI boundary.
  const report = (resp.report || {}) as Record<string, any>;
  const risks: RiskItem[] = (report.risks || []).map((r: any, idx: number) => ({
    id: r.id || 'agent-os-risk-' + idx,
    title: r.risk || r.risk_statement || r.title || 'Risk ' + (idx + 1),
    severity: r.severity || 'medium',
    linked_constraints: Array.isArray(r.linked_constraints) ? r.linked_constraints : (r.probability ? [r.probability] : []),
    detail: r.mitigation || r.detail || r.description || '',
  }));

  const artifactGraph = (report._artifact_graph || {}) as Record<string, any>;
  const totalArtifacts = artifactGraph.total_artifacts || resp.artifacts || 0;
  const gaps = report.gaps || artifactGraph.gaps || [];
  const coveredCount = totalArtifacts - (Array.isArray(gaps) ? gaps.length : (resp.gaps || 0));

  const riskPayload: RiskPayload = {
    overall_score: resp.board_verdict || null,
    gate: {
      decision: resp.board_verdict === 'PASS' ? 'APPROVED' : 'REVIEW',
      reason: resp.board_consensus || (risks.length === 0 ? 'No risks identified' : risks.length + ' risks require review'),
    },
    coverage: {
      total: totalArtifacts,
      covered: Math.max(0, coveredCount),
      coverage_pct: totalArtifacts > 0 ? Math.round((coveredCount / totalArtifacts) * 100) : 0,
      uncovered_ids: Array.isArray(gaps)
        ? gaps.map((g: any) => g.id || g.description || JSON.stringify(g).slice(0, 32))
        : (resp.gap_details || []).map((g) => g.description),
    },
    risks,
  };

  const gapDimensions: QualityDimension[] = (resp.gap_details || []).map((gap, idx) => ({
    name: gap.category || 'Gap ' + (idx + 1),
    score: gap.severity === 'critical' ? 20 : gap.severity === 'high' ? 40 : gap.severity === 'medium' ? 60 : 80,
    max_score: 100,
    weight: 1,
    feedback: gap.description,
    details: 'Category: ' + gap.category + ', Severity: ' + gap.severity,
  }));

  const evaluation: Evaluation = {
    overall_score: resp.gaps === 0 ? 90 : Math.max(30, 100 - (resp.gaps || 0) * 15),
    dimensions: gapDimensions.length > 0 ? gapDimensions : [
      { name: 'Business Model', score: 85, max_score: 100, weight: 1, feedback: 'Model generated', details: 'Agent OS analysis complete' },
      { name: 'Risk Coverage', score: risks.length > 0 ? 70 : 95, max_score: 100, weight: 1, feedback: risks.length + ' risks identified', details: '' },
      { name: 'Gap Analysis', score: (resp.gaps || 0) === 0 ? 95 : 60, max_score: 100, weight: 1, feedback: (resp.gaps || 0) + ' gaps found', details: '' },
    ],
    summary: resp.board_consensus || 'Mission: ' + (resp.mission?.title || 'Agent OS Analysis'),
    suggestions: (resp.gap_details || []).map((g) => 'Address gap: ' + g.description),
    is_passed: resp.board_verdict !== 'FAIL',
    improvement_points: resp.gaps || 0,
  };

  const trustedAudit: TrustedAudit = {
    source_refs: ['agent-os:' + (resp.mission?.title || 'analysis'), 'mode:' + (resp.mission?.mode || 'llm')],
    coverage: {
      coverage_pct: riskPayload.coverage.coverage_pct,
      covered: riskPayload.coverage.covered,
      total: riskPayload.coverage.total,
      uncovered_ids: riskPayload.coverage.uncovered_ids,
      gate_decision: resp.board_verdict || 'PENDING',
    },
    audit: [{
      seq: 1,
      agent: 'Business Agent OS',
      action: resp.mission?.title || 'Business Analysis',
      input_hash: 'mission-' + (resp.mission?.steps || 0) + '-steps',
      output_hash: (resp.artifacts || 0) + '-artifacts-' + (resp.gaps || 0) + '-gaps',
      hash: 'agent-os-' + Date.now(),
      prev_hash: 'genesis',
      timestamp: new Date().toISOString(),
    }],
    chain_hash: 'agent-os-chain-' + Date.now(),
    verified: resp.status === 'completed',
  };

  const citationCoverage: CitationCoverage = {
    coverage: riskPayload.coverage.coverage_pct,
    covered: riskPayload.coverage.covered,
    total: riskPayload.coverage.total,
    flagged: riskPayload.coverage.uncovered_ids,
  };

  return {
    session_id: 'agent-os-' + Date.now(),
    sop: {
      sops: (report.objectives || []).map((o: string) => ({ step: o, detail: '' })),
      _citation_coverage: citationCoverage,
    },
    risk: riskPayload,
    business_model: {
      domain: report.business_domain || '',
      objectives: report.objectives || [],
      artifacts: artifactGraph,
    },
    trusted_audit: trustedAudit,
    evaluation,
    evolution: {
      recent_feedback: [],
      stats: {
        total: 0,
        by_type: { thumbs_up: 0, thumbs_down: 0, correction: 0, comment: 0 },
        by_user: {},
        positive_rate: 0,
      },
    },
  };
}
