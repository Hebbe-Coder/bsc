import type { AgentAnalysisResponse } from '../api/agentOsApi';
import type { DashboardData, RiskItem, RiskPayload, TrustedAudit, Evaluation, QualityDimension, CitationCoverage } from '../api/compilerDashboardApi';

function isTrustedAudit(value: unknown): value is TrustedAudit {
  if (!value || typeof value !== 'object') return false;
  const audit = value as Partial<TrustedAudit>;
  return typeof audit.chain_hash === 'string'
    && typeof audit.verified === 'boolean'
    && Array.isArray(audit.source_refs)
    && Array.isArray(audit.audit)
    && Boolean(audit.coverage && typeof audit.coverage === 'object');
}

function highestRiskSeverity(risks: RiskItem[]): string | null {
  const rank: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
  return risks.reduce<string | null>((highest, risk) => (
    !highest || (rank[risk.severity] ?? 0) > (rank[highest] ?? 0)
      ? risk.severity
      : highest
  ), null);
}

function sourceRefs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((ref): ref is string => typeof ref === 'string' && ref.trim().length > 0);
}

function gapImpact(severity: string): number {
  const impact: Record<string, number> = {
    critical: 24,
    high: 14,
    medium: 8,
    low: 3,
  };
  return impact[severity] ?? 8;
}

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
  const trustedAudit = isTrustedAudit(resp.trusted_audit)
    ? resp.trusted_audit
    : undefined;
  const auditedCoverage = trustedAudit?.coverage;
  const hasAuditedCoverage = typeof auditedCoverage?.coverage_pct === 'number'
    && typeof auditedCoverage.total === 'number'
    && typeof auditedCoverage.covered === 'number';
  const coverage = hasAuditedCoverage
    ? {
      total: auditedCoverage.total,
      covered: auditedCoverage.covered,
      coverage_pct: auditedCoverage.coverage_pct,
      uncovered_ids: auditedCoverage.uncovered_ids,
    }
    : {
      total: totalArtifacts,
      covered: Math.max(0, coveredCount),
      coverage_pct: totalArtifacts > 0 ? Math.round((coveredCount / totalArtifacts) * 100) : 0,
      uncovered_ids: Array.isArray(gaps)
        ? gaps.map((g: any) => g.id || g.description || JSON.stringify(g).slice(0, 32))
        : (resp.gap_details || []).map((g) => g.description),
    };

  const riskPayload: RiskPayload = {
    overall_score: resp.board_verdict || highestRiskSeverity(risks),
    gate: {
      decision: resp.board_verdict === 'PASS'
        ? 'APPROVED'
        : auditedCoverage?.gate_decision || 'REVIEW',
      reason: resp.board_consensus || (risks.length === 0 ? 'No risks identified' : risks.length + ' risks require review'),
    },
    coverage,
    risks,
  };

  const gapDetails = resp.gap_details || [];
  const gapDimensions: QualityDimension[] = gapDetails.map((gap, idx) => ({
    name: gap.category || 'Gap ' + (idx + 1),
    score: gap.severity === 'critical' ? 20 : gap.severity === 'high' ? 40 : gap.severity === 'medium' ? 60 : 80,
    max_score: 100,
    weight: 1,
    feedback: gap.description,
    details: 'Category: ' + gap.category + ', Severity: ' + gap.severity,
  }));

  const coveragePct = riskPayload.coverage.coverage_pct;
  const unresolvedImpact = gapDetails.reduce((total, gap) => total + gapImpact(gap.severity), 0);
  const evidenceHealth = Math.max(0, Math.min(100, coveragePct));
  const issueHealth = Math.max(0, 100 - unresolvedImpact);
  // This is decision readiness, not a claim that the generated prose is intrinsically bad.
  const overallScore = Math.max(0, Math.round(evidenceHealth * 0.7 + issueHealth * 0.3));
  const criticalGapCount = gapDetails.filter((gap) => gap.severity === 'critical').length;

  const rawSops = Array.isArray(report.sops) && report.sops.length > 0
    ? report.sops
    : (Array.isArray(artifactGraph.deliverables)
      ? artifactGraph.deliverables.flatMap((deliverable: any) => Array.isArray(deliverable.actions) ? deliverable.actions : [])
      : (report.objectives || []));
  const sops = rawSops.map((step: unknown, index: number) => {
    if (step && typeof step === 'object') {
      const item = step as Record<string, unknown>;
      return {
        ...item,
        id: typeof item.id === 'string' ? item.id : `agent-os-step-${index}`,
        title: typeof item.title === 'string'
          ? item.title
          : (typeof item.step === 'string' ? item.step : `Analysis item ${index + 1}`),
        source_ref: sourceRefs(item.source_ref ?? item.source_refs),
      };
    }
    return {
      id: `agent-os-step-${index}`,
      title: typeof step === 'string' ? step : `Analysis item ${index + 1}`,
      source_ref: [],
    };
  });
  const citedSteps = sops.filter((step: { source_ref: string[] }) => step.source_ref.length > 0);
  const citationCoverage: CitationCoverage = {
    coverage: sops.length > 0 ? Math.round((citedSteps.length / sops.length) * 100) : 0,
    covered: citedSteps.length,
    total: sops.length,
    flagged: sops
      .filter((step: { source_ref: string[] }) => step.source_ref.length === 0)
      .map((step: { title: string }) => step.title),
  };

  const evaluation: Evaluation = {
    overall_score: overallScore,
    dimensions: gapDimensions.length > 0 ? gapDimensions : [
      { name: 'Business Model', score: 85, max_score: 100, weight: 1, feedback: 'Model generated', details: 'Agent OS analysis complete' },
      { name: 'Risk Coverage', score: risks.length > 0 ? 70 : 95, max_score: 100, weight: 1, feedback: risks.length + ' risks identified', details: '' },
      { name: 'Gap Analysis', score: (resp.gaps || 0) === 0 ? 95 : 60, max_score: 100, weight: 1, feedback: (resp.gaps || 0) + ' gaps found', details: '' },
    ],
    summary: resp.board_consensus || 'Mission: ' + (resp.mission?.title || 'Agent OS Analysis'),
    suggestions: (resp.gap_details || []).map((g) => 'Address gap: ' + g.description),
    is_passed: overallScore >= 70 && criticalGapCount === 0,
    improvement_points: resp.gaps || 0,
  };

  return {
    session_id: 'agent-os-' + Date.now(),
    sop: {
      sops,
      _citation_coverage: citationCoverage,
    },
    risk: riskPayload,
    business_model: {
      domain: report.business_domain || '',
      objectives: report.objectives || [],
      artifacts: artifactGraph,
    },
    ...(trustedAudit ? { trusted_audit: trustedAudit } : {}),
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
