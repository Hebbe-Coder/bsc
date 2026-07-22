"""Evidence-derived quality and regression gates for method proposals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.knowledge.growth_repository import GrowthRepository


CaseRunner = Callable[[dict[str, Any], dict[str, Any]], bool | dict[str, Any]]
_REQUIRED_MANIFEST_FIELDS = (
    "task_family",
    "applicability",
    "exclusions",
    "inputs",
    "outputs",
    "steps",
    "evidence_rules",
    "failure_handling",
    "eval_cases",
)


class MethodEvaluator:
    def __init__(self, repository: GrowthRepository) -> None:
        self.repository = repository

    def evaluate(
        self,
        proposal: dict[str, Any],
        *,
        case_runner: CaseRunner | None = None,
        evaluator_revision: str = "method-evaluator-v2",
        model_revision: str = "deterministic",
        latency_ms: int = 0,
        comparable_uses: int | None = None,
        average_quality: float | None = None,
        groundedness: float | None = None,
        security_failures: int = 0,
        regression_failures: int = 0,
    ) -> dict[str, Any]:
        project_id = str(proposal.get("project_id") or "")
        proposal_id = str(proposal.get("id") or "")
        persisted = self.repository.get_method_proposal(project_id, proposal_id)
        if not persisted:
            raise KeyError("method proposal not found in project")
        manifest = proposal.get("manifest") or {}
        self._validate_manifest(manifest)

        outputs = self._source_outputs(project_id, persisted.get("source_output_ids") or [])
        actual_uses = self._comparable_uses(project_id, outputs)
        evaluations = self._latest_evaluations(project_id, outputs)
        qualities = [float(item["quality"]) for item in evaluations]
        groundings = [float(item["groundedness"]) for item in evaluations]
        actual_quality = sum(qualities) / len(qualities) if qualities else 0.0
        actual_groundedness = sum(groundings) / len(groundings) if groundings else 0.0

        accepted_or_reused = any(output.get("status") == "accepted" for output in outputs)
        if not accepted_or_reused:
            accepted_or_reused = any(
                feedback.get("feedback_type") in {"accepted", "reused"}
                for output in outputs
                for feedback in self.repository.list_feedback(
                    project_id, output_id=output["id"], limit=500
                )
            )
        actual_security_failures = sum(
            bool((output.get("metadata") or {}).get("security_failure"))
            or bool((output.get("metadata") or {}).get("permission_failure"))
            for output in outputs
        )
        actual_security_failures = max(actual_security_failures, int(security_failures))

        cases = self._cases(project_id, manifest, {item["id"] for item in outputs})
        case_results: list[dict[str, Any]] = []
        evaluator_status = "completed"
        actual_regression_failures = max(0, int(regression_failures))
        if cases and case_runner is None:
            evaluator_status = "unavailable"
            actual_regression_failures += len(cases)
            case_results = [
                {"id": case["id"], "passed": False, "status": "unavailable"}
                for case in cases
            ]
        else:
            for case in cases:
                try:
                    raw = case_runner(case, persisted) if case_runner else True
                    if isinstance(raw, dict):
                        passed = bool(raw.get("passed"))
                        result = {**raw, "id": case["id"], "passed": passed}
                    else:
                        passed = bool(raw)
                        result = {"id": case["id"], "passed": passed}
                except Exception as exc:
                    passed = False
                    result = {
                        "id": case["id"],
                        "passed": False,
                        "status": "runner_failed",
                        "error": str(exc),
                    }
                if not passed:
                    actual_regression_failures += 1
                if case.get("type") in {"security", "permission"} and not passed:
                    actual_security_failures += 1
                case_results.append(result)

        baseline = self._baseline(project_id, persisted)
        baseline_regression = bool(
            baseline
            and (
                actual_quality < float(baseline.get("average_quality") or 0)
                or actual_groundedness < float(baseline.get("groundedness") or 0)
            )
        )
        eligible = (
            evaluator_status == "completed"
            and actual_uses >= 3
            and actual_quality >= 85
            and actual_groundedness >= 0.90
            and accepted_or_reused
            and actual_security_failures == 0
            and actual_regression_failures == 0
            and not baseline_regression
            and len(evaluations) == len(outputs)
        )
        findings: list[str] = []
        if actual_uses < 3:
            findings.append("fewer than three comparable successful uses")
        if len(evaluations) != len(outputs):
            findings.append("one or more supporting outputs lack an immutable evaluation")
        if actual_quality < 85:
            findings.append("average output quality is below 85")
        if actual_groundedness < 0.90:
            findings.append("average groundedness is below 0.90")
        if not accepted_or_reused:
            findings.append("no supporting output was accepted or reused")
        if actual_security_failures:
            findings.append("security or permission regression detected")
        if actual_regression_failures:
            findings.append("one or more evaluation cases failed")
        if baseline_regression:
            findings.append("candidate regresses the active published baseline")
        if evaluator_status != "completed":
            findings.append("evaluation replay is unavailable")

        summary = {
            "comparable_uses": actual_uses,
            "average_quality": round(actual_quality, 4),
            "groundedness": round(actual_groundedness, 6),
            "accepted_or_reused": accepted_or_reused,
            "security_failures": actual_security_failures,
            "regression_failures": actual_regression_failures,
            "baseline_regression": baseline_regression,
            "baseline": baseline,
            "case_results": case_results,
            "supporting_output_ids": [item["id"] for item in outputs],
            "evaluator_revision": evaluator_revision,
            "model_revision": model_revision,
            "latency_ms": max(0, int(latency_ms)),
            "evaluator_status": evaluator_status,
            "reported_metrics": {
                "comparable_uses": comparable_uses,
                "average_quality": average_quality,
                "groundedness": groundedness,
            },
            "findings": findings,
            "eligible": eligible,
        }
        self.repository.update_method_proposal_evaluation(
            project_id,
            proposal_id,
            summary,
            "approved" if eligible else "rejected",
        )
        self.repository.record_eval_run(
            project_id=project_id,
            proposal_id=proposal_id,
            wiki_revision=evaluator_revision,
            status="passed" if eligible else evaluator_status if evaluator_status != "completed" else "failed",
            summary=summary,
        )
        return summary

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        missing = [field for field in _REQUIRED_MANIFEST_FIELDS if field not in manifest]
        if missing:
            raise ValueError(f"method manifest is missing required fields: {', '.join(missing)}")
        list_fields = _REQUIRED_MANIFEST_FIELDS[1:]
        invalid = [field for field in list_fields if not isinstance(manifest.get(field), list)]
        if invalid:
            raise ValueError(f"method manifest fields must be lists: {', '.join(invalid)}")
        required_nonempty = ("applicability", "inputs", "outputs", "steps", "evidence_rules", "failure_handling")
        empty = [field for field in required_nonempty if not manifest.get(field)]
        if empty:
            raise ValueError(f"method manifest fields must not be empty: {', '.join(empty)}")

    def _source_outputs(
        self, project_id: str, output_ids: list[str]
    ) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for output_id in dict.fromkeys(output_ids):
            output = self.repository.get_output(project_id, output_id)
            if not output:
                raise ValueError("method proposal references a missing or cross-project output")
            outputs.append(output)
        return outputs

    def _comparable_uses(
        self, project_id: str, outputs: list[dict[str, Any]]
    ) -> int:
        identities: set[str] = set()
        for output in outputs:
            run_id = str(output.get("run_id") or "")
            if not run_id:
                identities.add(f"output:{output['id']}")
                continue
            visited: set[str] = set()
            current = run_id
            while current and current not in visited:
                visited.add(current)
                run = self.repository.get_run(project_id, current)
                retry_of = str((run or {}).get("retry_of") or "")
                if not retry_of:
                    break
                current = retry_of
            identities.add(f"run:{current or run_id}")
        return len(identities)

    def _latest_evaluations(
        self, project_id: str, outputs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        latest: list[dict[str, Any]] = []
        for output in outputs:
            rows = [
                row
                for row in self.repository.list_output_evaluations(
                    project_id, output["id"], limit=500
                )
                if row.get("status") == "completed"
            ]
            if rows:
                latest.append(rows[0])
        return latest

    def _cases(
        self,
        project_id: str,
        manifest: dict[str, Any],
        output_ids: set[str],
    ) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for index, case in enumerate(manifest.get("eval_cases") or [], 1):
            if not isinstance(case, dict):
                raise ValueError("method eval cases must be mappings")
            cases.append({**case, "id": str(case.get("id") or f"manifest-{index}"), "type": str(case.get("type") or "functional")})
        for row in self.repository.list_eval_cases(project_id):
            case_type = str(row.get("case_type") or "")
            if case_type not in {
                "output_correction",
                "output_failure",
                "method_regression",
                "security",
                "permission",
            }:
                continue
            expected = row.get("expected") or {}
            related_output = str(expected.get("output_id") or "")
            if related_output and related_output not in output_ids:
                continue
            related_method = str(expected.get("method_id") or "")
            if not related_output and not related_method and case_type not in {"security", "permission"}:
                continue
            cases.append(
                {
                    **expected,
                    "id": str(row.get("case_id") or row.get("id")),
                    "type": case_type,
                }
            )
        unique: dict[str, dict[str, Any]] = {}
        for case in cases:
            unique[case["id"]] = case
        return list(unique.values())

    def _baseline(
        self, project_id: str, proposal: dict[str, Any]
    ) -> dict[str, Any]:
        method_id = str(proposal.get("method_id") or "")
        if not method_id:
            return {}
        method = self.repository.get_method(project_id, method_id)
        active_id = str((method or {}).get("active_revision_id") or "")
        if not active_id:
            return {}
        revision = self.repository.get_method_revision(project_id, active_id) or {}
        summary = revision.get("eval_summary") or {}
        return {
            "revision_id": active_id,
            "average_quality": float(summary.get("average_quality") or 0),
            "groundedness": float(summary.get("groundedness") or 0),
        }
