"""Deterministic project baselines for Wiki citation and SOP quality gates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.wiki_repository import WikiRepository


class WikiEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    status: str
    score: float = Field(ge=0.0, le=1.0)
    findings: tuple[dict[str, str], ...] = ()
    skipped_reason: str = ""


class WikiEvaluator:
    """Evaluate structured candidates against persisted, project-local baselines."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def save_case(self, *, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict:
        if case_type not in {"citation", "sop", "content"}:
            raise ValueError("case_type must be citation, sop, or content")
        return self.repository.upsert_eval_case(project_id, case_id, case_type, expected)

    def evaluate(
        self, *, project_id: str, candidate: dict[str, Any], proposal_id: str = "", wiki_revision: str = ""
    ) -> WikiEvaluationReport:
        cases = self.repository.list_eval_cases(project_id)
        if not cases:
            report = WikiEvaluationReport(
                project_id=project_id,
                status="unavailable",
                score=0.0,
                skipped_reason="missing evaluation baseline",
            )
            self._record(report, proposal_id=proposal_id, wiki_revision=wiki_revision)
            return report
        findings: list[dict[str, str]] = []
        candidate_sources = set(candidate.get("source_ids") or [])
        content = str(candidate.get("content") or "").lower()
        for case in cases:
            expected = case["expected"]
            if case["case_type"] == "citation":
                for source_id in expected.get("source_ids") or []:
                    if source_id not in candidate_sources:
                        findings.append({"case_id": case["case_id"], "code": "missing_expected_source", "detail": source_id})
            else:
                for constraint in expected.get("constraints") or []:
                    if str(constraint).lower() not in content:
                        findings.append({"case_id": case["case_id"], "code": "missing_required_constraint", "detail": str(constraint)})
        passed_cases = len(cases) - len({finding["case_id"] for finding in findings})
        score = passed_cases / len(cases)
        report = WikiEvaluationReport(
            project_id=project_id,
            status="passed" if not findings else "failed",
            score=score,
            findings=tuple(findings),
        )
        self._record(report, proposal_id=proposal_id, wiki_revision=wiki_revision)
        return report

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
            },
        )
