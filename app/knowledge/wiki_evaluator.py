"""Deterministic project baselines for Wiki citation and SOP quality gates."""

from __future__ import annotations

from typing import Any
import time

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.wiki_repository import WikiRepository


class WikiEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    status: str
    score: float = Field(ge=0.0, le=1.0)
    findings: tuple[dict[str, str], ...] = ()
    skipped_reason: str = ""
    baseline_score: float | None = None
    score_delta: float | None = None
    coverage: float = Field(ge=0.0, le=1.0)
    latency_ms: float = Field(ge=0.0)


class WikiEvaluator:
    """Evaluate structured candidates against persisted, project-local baselines."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def save_case(self, *, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict:
        if case_type not in {"retrieval", "citation", "sop", "content"}:
            raise ValueError("case_type must be retrieval, citation, sop, or content")
        return self.repository.upsert_eval_case(project_id, case_id, case_type, expected)

    def evaluate(
        self, *, project_id: str, candidate: dict[str, Any], proposal_id: str = "", wiki_revision: str = ""
    ) -> WikiEvaluationReport:
        started = time.perf_counter()
        prior_runs = self.repository.list_eval_runs(project_id, limit=1)
        baseline_score = prior_runs[0]["summary"].get("score") if prior_runs else None
        cases = self.repository.list_eval_cases(project_id)
        if not cases:
            report = WikiEvaluationReport(
                project_id=project_id,
                status="unavailable",
                score=0.0,
                skipped_reason="missing evaluation baseline",
                baseline_score=baseline_score,
                score_delta=None if baseline_score is None else -float(baseline_score),
                coverage=0.0,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._record(report, proposal_id=proposal_id, wiki_revision=wiki_revision)
            return report
        applicable_cases = [case for case in cases if self._applies_to_candidate(case, candidate)]
        if not applicable_cases:
            report = WikiEvaluationReport(
                project_id=project_id,
                status="not_applicable",
                score=1.0,
                skipped_reason="no applicable evaluation cases",
                baseline_score=baseline_score,
                score_delta=None,
                coverage=0.0,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._record(report, proposal_id=proposal_id, wiki_revision=wiki_revision)
            return report
        findings: list[dict[str, str]] = []
        candidate_sources = set(candidate.get("source_ids") or [])
        retrieved_sources = set(candidate.get("retrieved_source_ids") or candidate_sources)
        content = str(candidate.get("content") or "").lower()
        for case in applicable_cases:
            expected = case["expected"]
            if case["case_type"] in {"retrieval", "citation"}:
                for source_id in expected.get("source_ids") or []:
                    selected = retrieved_sources if case["case_type"] == "retrieval" else candidate_sources
                    if source_id not in selected:
                        code = "missing_expected_retrieval" if case["case_type"] == "retrieval" else "missing_expected_source"
                        findings.append({"case_id": case["case_id"], "code": code, "detail": source_id})
            else:
                for constraint in expected.get("constraints") or []:
                    if str(constraint).lower() not in content:
                        findings.append({"case_id": case["case_id"], "code": "missing_required_constraint", "detail": str(constraint)})
                if case["case_type"] == "content" and expected.get("require_citations") and "[source:" not in content:
                    findings.append({"case_id": case["case_id"], "code": "unsupported_content_claim", "detail": "citation required"})
        passed_cases = len(applicable_cases) - len({finding["case_id"] for finding in findings})
        score = passed_cases / len(applicable_cases)
        latency_ms = (time.perf_counter() - started) * 1000.0
        report = WikiEvaluationReport(
            project_id=project_id,
            status="passed" if not findings else "failed",
            score=score,
            findings=tuple(findings),
            baseline_score=baseline_score,
            score_delta=None if baseline_score is None else score - float(baseline_score),
            coverage=score,
            latency_ms=latency_ms,
        )
        self._record(report, proposal_id=proposal_id, wiki_revision=wiki_revision)
        return report

    @staticmethod
    def _applies_to_candidate(case: dict[str, Any], candidate: dict[str, Any]) -> bool:
        expected = case.get("expected") if isinstance(case, dict) else {}
        scope_paths = expected.get("scope_paths") if isinstance(expected, dict) else None
        if not scope_paths:
            return True
        if not isinstance(scope_paths, list):
            return False
        candidate_paths = {str(path) for path in candidate.get("paths") or [] if str(path)}
        return bool(candidate_paths.intersection(str(path) for path in scope_paths if str(path)))

    def _record(self, report: WikiEvaluationReport, *, proposal_id: str, wiki_revision: str) -> None:
        self.repository.record_eval_run(
            project_id=report.project_id,
            proposal_id=proposal_id,
            wiki_revision=wiki_revision,
            status=report.status,
            summary={
                "score": report.score,
                "findings": list(report.findings),
                "skipped_reason": report.skipped_reason,
                "baseline_score": report.baseline_score,
                "score_delta": report.score_delta,
                "coverage": report.coverage,
                "latency_ms": report.latency_ms,
            },
        )
