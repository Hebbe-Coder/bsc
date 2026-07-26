"""Evidence-derived quality and regression gates for method proposals."""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from app.knowledge.growth_contracts import is_verified_output_status
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_routing import MethodRouter
from app.knowledge.method_package_audit import MethodPackageAuditor
from app.knowledge.source_triage import current_project_triage_decisions, source_admission_reason


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
_EVOLUTION_PROTOCOL_REVISION = "method-evolution-v1"
_MUTATION_DIMENSIONS = (
    "body",
    "trigger_contract",
    "applicability",
    "exclusions",
    "steps",
    "evidence_rules",
    "failure_handling",
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
        # The repository record is the candidate being evaluated.  Callers can
        # provide an ID, but must not be able to substitute a different package
        # manifest for the persisted proposal during evaluation.
        manifest = persisted.get("manifest") or {}
        package_audit = MethodPackageAuditor().audit(
            body=str(persisted.get("body") or ""),
            manifest=dict(manifest),
        )
        self.repository.update_method_proposal_package_audit(project_id, proposal_id, package_audit)
        if package_audit["blocking"]:
            findings = [item["message"] for item in package_audit["findings"] if item["severity"] in {"critical", "error"}]
            summary = {
                "eligible": False,
                "evaluator_status": "blocked",
                "package_audit": package_audit,
                "findings": ["static method package audit blocked evaluation", *findings],
                "evaluator_revision": evaluator_revision,
                "model_revision": model_revision,
                "latency_ms": max(0, int(latency_ms)),
            }
            self.repository.update_method_proposal_evaluation(project_id, proposal_id, summary, "rejected")
            self.repository.record_eval_run(
                project_id=project_id,
                proposal_id=proposal_id,
                wiki_revision=evaluator_revision,
                status="blocked",
                summary=summary,
            )
            return summary
        self._validate_manifest(manifest)
        if self._is_source_distillation(manifest):
            return self._evaluate_source_distillation(
                persisted,
                evaluator_revision=evaluator_revision,
                model_revision=model_revision,
                latency_ms=latency_ms,
            )

        outputs = self._source_outputs(project_id, persisted.get("source_output_ids") or [])
        actual_uses = self._comparable_uses(project_id, outputs)
        evaluations = self._latest_evaluations(project_id, outputs)
        qualities = [float(item["quality"]) for item in evaluations]
        groundings = [float(item["groundedness"]) for item in evaluations]
        actual_quality = sum(qualities) / len(qualities) if qualities else 0.0
        actual_groundedness = sum(groundings) / len(groundings) if groundings else 0.0

        accepted_or_reused = any(is_verified_output_status(output.get("status")) for output in outputs)
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

        baseline = self._baseline(project_id, persisted)
        cases = self._cases(project_id, manifest, {item["id"] for item in outputs})
        routing_results, routing_complete = self._route_cases(project_id, persisted)
        routing_case_ids = {str(item["id"]) for item in routing_results}
        execution_cases = [case for case in cases if str(case["id"]) not in routing_case_ids]
        case_results: list[dict[str, Any]] = list(routing_results)
        evaluator_status = "completed"
        actual_regression_failures = max(0, int(regression_failures))
        failed_routes = [item for item in routing_results if not item["passed"]]
        if not routing_complete:
            actual_regression_failures += 1
        actual_regression_failures += len(failed_routes)
        evolution = self._evaluate_update_evolution(
            project_id,
            persisted,
            routing_results=routing_results,
            baseline=baseline,
        )
        if not evolution["passed"]:
            actual_regression_failures += 1
        if execution_cases and case_runner is None:
            evaluator_status = "unavailable"
            actual_regression_failures += len(execution_cases)
            case_results.extend(
                {"id": case["id"], "passed": False, "status": "unavailable"}
                for case in execution_cases
            )
        else:
            for case in execution_cases:
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

        baseline_regression = bool(
            baseline
            and (
                actual_quality + 1e-6 < float(baseline.get("average_quality") or 0)
                or actual_groundedness + 1e-6 < float(baseline.get("groundedness") or 0)
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
            findings.append("no supporting output was verified or reused")
        if actual_security_failures:
            findings.append("security or permission regression detected")
        if not routing_complete:
            findings.append("routing contract needs three positive, two negative, one edge case, and a sibling confusion case when a competing method exists")
        if failed_routes:
            findings.append("one or more deterministic method routing cases failed")
        if actual_regression_failures:
            findings.append("one or more evaluation cases failed")
        if baseline_regression:
            findings.append("candidate regresses the active published baseline")
        findings.extend(evolution["findings"])
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
            "evolution": evolution,
            "case_results": case_results,
            "routing": {
                "complete": routing_complete,
                "cases": routing_results,
                "competing_method_slugs": sorted({
                    slug
                    for item in routing_results
                    for slug in item.get("matches", [])
                    if slug != str(manifest.get("task_family") or "")
                }),
            },
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

    def _evaluate_source_distillation(
        self,
        proposal: dict[str, Any],
        *,
        evaluator_revision: str,
        model_revision: str,
        latency_ms: int,
    ) -> dict[str, Any]:
        """Gate a source-derived method without allowing client-supplied pass flags."""
        project_id = str(proposal["project_id"])
        proposal_id = str(proposal["id"])
        manifest = proposal.get("manifest") or {}
        contract = manifest.get("distillation") or {}
        findings: list[str] = []
        evidence_results: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        anchors: set[tuple[str, str]] = set()
        decisions = current_project_triage_decisions(self.repository, project_id)
        for index, evidence in enumerate(contract.get("evidence") or [], 1):
            if not isinstance(evidence, dict):
                findings.append(f"evidence {index} is not a mapping")
                continue
            source_id = str(evidence.get("source_id") or "")
            expected_hash = str(evidence.get("content_hash") or "")
            quote = self._normalized_quote(evidence.get("quote"))
            source = self.repository.get_source(project_id, source_id) if source_id else None
            if not source:
                findings.append(f"evidence {index} source is missing or cross-project")
                continue
            admitted_reason = source_admission_reason(
                self.repository,
                project_id,
                source,
                current_decisions=decisions,
            )
            valid = (
                source.get("status") in {"eligible", "processed"}
                and expected_hash == str(source.get("content_hash") or "")
                and len(quote) >= 12
                and quote in self._normalized_quote(source.get("raw_content"))
                and not admitted_reason
            )
            evidence_results.append({"index": index, "source_id": source_id, "valid": valid})
            if not valid:
                findings.append(f"evidence {index} does not resolve to admitted immutable source content")
                continue
            source_ids.add(source_id)
            anchors.add((source_id, quote))

        v1_passed = len(anchors) >= 2
        if not v1_passed:
            findings.append("V1 requires two distinct admitted evidence anchors")

        body = str(proposal.get("body") or "")
        missing_sections = [
            heading
            for heading in ("R", "I", "A1", "A2", "E", "B")
            if not re.search(rf"^##\s+{heading}(?:\s|$|[—-])", body, flags=re.MULTILINE)
        ]
        ria_passed = len(body) >= 280 and not missing_sections
        if not ria_passed:
            findings.append(f"RIA++ body is incomplete: {', '.join(missing_sections) or 'body too short'}")

        review = contract.get("critical_review") if isinstance(contract.get("critical_review"), dict) else {}
        non_triviality = str(contract.get("non_triviality") or "").strip()
        v3_passed = (
            len(non_triviality) >= 24
            and bool(review.get("failure_modes"))
            and bool(review.get("validity_limits"))
        )
        if not v3_passed:
            findings.append("V3 requires a non-triviality rationale, failure modes, and validity limits")

        route_results, routing_complete = self._route_cases(project_id, proposal)
        failed_routes = [item for item in route_results if not item["passed"]]
        if not routing_complete:
            findings.append("routing contract is incomplete")
        if failed_routes:
            findings.append("one or more trigger, negative, sibling, or edge routing cases failed")
        v2_passed = routing_complete and not failed_routes

        eligible = v1_passed and ria_passed and v2_passed and v3_passed
        summary = {
            "evaluation_mode": "source_distillation",
            "contract_revision": str(contract.get("contract_revision") or ""),
            "eligible": eligible,
            "v1_evidence_diversity": {"passed": v1_passed, "anchors": len(anchors), "source_ids": sorted(source_ids), "results": evidence_results},
            "v2_transfer_and_routing": {"passed": v2_passed, "cases": route_results},
            "v3_non_triviality": {"passed": v3_passed, "semantic_proof": "not_claimed"},
            "ria_complete": ria_passed,
            "findings": findings,
            "evaluator_revision": evaluator_revision,
            "model_revision": model_revision,
            "latency_ms": max(0, int(latency_ms)),
            "evaluator_status": "completed",
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
            status="passed" if eligible else "failed",
            summary=summary,
        )
        return summary

    @staticmethod
    def _is_source_distillation(manifest: dict[str, Any]) -> bool:
        contract = manifest.get("distillation")
        return isinstance(contract, dict) and str(contract.get("contract_revision") or "") == "ria-tvpp-v1"

    def _route_cases(self, project_id: str, proposal: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        manifest = proposal.get("manifest") or {}
        contract = manifest.get("distillation") or {}
        batch_id = str(contract.get("batch_id") or "")
        proposals = [proposal]
        if batch_id:
            proposals = [
                item
                for item in self.repository.list_method_proposals(project_id, limit=500)
                if isinstance(item.get("manifest"), dict)
                and str((item["manifest"].get("distillation") or {}).get("batch_id") or "") == batch_id
            ]
        methods = [self._routing_method(item) for item in proposals]
        # Published methods are the actual competitors at generation time.
        # Batch siblings remain in the candidate set so a source distillation
        # proves that its new proposals do not silently route into one another.
        methods.extend(self._published_routing_methods(project_id))
        deduplicated: dict[str, dict[str, Any]] = {}
        for item in methods:
            slug = str(item.get("slug") or "")
            if slug and slug not in deduplicated:
                deduplicated[slug] = item
        methods = list(deduplicated.values())
        available = {str(item.get("slug") or "") for item in methods}
        cases = [item for item in manifest.get("eval_cases") or [] if isinstance(item, dict)]
        type_counts = {kind: sum(str(case.get("type") or "") == kind for case in cases) for kind in ("should_trigger", "should_not_trigger", "edge_case")}
        current_slug = str(manifest.get("task_family") or "")
        trigger = manifest.get("trigger_contract")
        if not isinstance(trigger, dict):
            trigger = contract.get("trigger_contract") if isinstance(contract, dict) else None
        explicit_contract = (
            isinstance(trigger, dict)
            and bool(trigger.get("positive_signals"))
            and isinstance(trigger.get("negative_signals"), list)
        )
        competing = any(slug != current_slug for slug in available)
        has_sibling = any(
            str(case.get("type") or "") == "should_not_trigger"
            and str(case.get("expected_method") or "")
            and str(case.get("expected_method") or "") != current_slug
            for case in cases
        )
        complete = (
            explicit_contract
            and
            type_counts["should_trigger"] >= 3
            and type_counts["should_not_trigger"] >= 2
            and type_counts["edge_case"] >= 1
            and (not competing or has_sibling)
        )
        router = MethodRouter()
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases, 1):
            expected = str(case.get("expected_method") or "")
            prompt = str(case.get("prompt") or "")
            decision = router.select(methods, prompt)
            valid_expected = not expected or expected in available
            passed = bool(prompt.strip()) and valid_expected and decision.selected_slug == (expected or None)
            results.append({
                "id": str(case.get("id") or f"routing-{index}"),
                "type": str(case.get("type") or ""),
                "expected_method": expected or None,
                "selected_method": decision.selected_slug,
                "passed": passed,
                "matches": [match.slug for match in decision.matches],
            })
        return results, complete

    def _published_routing_methods(self, project_id: str) -> list[dict[str, Any]]:
        methods: list[dict[str, Any]] = []
        for published in self.repository.list_methods(project_id, status="published", limit=500):
            revision_id = str(published.get("active_revision_id") or "")
            revision = self.repository.get_method_revision(project_id, revision_id) if revision_id else None
            if not revision or revision.get("status") != "published":
                continue
            methods.append(
                {
                    "slug": str(published.get("slug") or ""),
                    "manifest": revision.get("manifest") or {},
                    "applicability": published.get("applicability") or [],
                    "exclusions": published.get("exclusions") or [],
                }
            )
        return methods

    def _evaluate_update_evolution(
        self,
        project_id: str,
        proposal: dict[str, Any],
        *,
        routing_results: list[dict[str, Any]],
        baseline: dict[str, Any],
    ) -> dict[str, Any]:
        """Require isolated routing holdouts before replacing an active method."""
        if str(proposal.get("operation") or "") != "update":
            return {
                "required": False,
                "passed": True,
                "status": "not_applicable",
                "findings": [],
                "holdout": {"candidate_passed": None, "baseline_passed": None, "regressed_case_ids": []},
            }

        manifest = proposal.get("manifest") if isinstance(proposal.get("manifest"), dict) else {}
        current_slug = str(manifest.get("task_family") or "")
        protocol = manifest.get("evaluation_protocol")
        findings: list[str] = []
        baseline_revision_id = str(baseline.get("revision_id") or "")
        baseline_revision = (
            self.repository.get_method_revision(project_id, baseline_revision_id)
            if baseline_revision_id
            else None
        )
        cases = [case for case in manifest.get("eval_cases") or [] if isinstance(case, dict)]
        splits = {
            "positive": [case for case in cases if str(case.get("split") or "") == "positive"],
            "near_negative": [case for case in cases if str(case.get("split") or "") == "near_negative"],
            "holdout": [case for case in cases if str(case.get("split") or "") == "holdout"],
        }
        protocol_valid = (
            isinstance(protocol, dict)
            and str(protocol.get("revision") or "") == _EVOLUTION_PROTOCOL_REVISION
        )
        if not protocol_valid:
            findings.append("update proposals require the method-evolution-v1 evaluation protocol")
        if not baseline_revision:
            findings.append("update proposals require an active published baseline")
        elif str((protocol or {}).get("baseline_revision_id") or "") != baseline_revision_id:
            findings.append("evaluation protocol must name the active baseline revision")
        if len(splits["positive"]) < 3:
            findings.append("update proposals require three positive routing cases")
        if len(splits["near_negative"]) < 2:
            findings.append("update proposals require two near-negative routing cases")
        if len(splits["holdout"]) < 2:
            findings.append("update proposals require two isolated holdout routing cases")
        if any(
            str(case.get("type") or "") != "should_trigger"
            or str(case.get("expected_method") or "") != current_slug
            for case in splits["positive"]
        ):
            findings.append("positive cases must trigger the candidate method")
        if any(
            str(case.get("type") or "") != "should_not_trigger"
            or str(case.get("expected_method") or "") == current_slug
            for case in splits["near_negative"]
        ):
            findings.append("near-negative cases must not select the candidate method")
        if any(
            str(case.get("type") or "") not in {"should_trigger", "should_not_trigger", "edge_case"}
            for case in splits["holdout"]
        ):
            findings.append("holdout cases use an unsupported routing type")

        seen_prompts: dict[str, str] = {}
        for split, split_cases in splits.items():
            for case in split_cases:
                prompt = " ".join(str(case.get("prompt") or "").lower().split())
                if not prompt:
                    findings.append(f"{split} case is missing a prompt")
                    continue
                existing = seen_prompts.get(prompt)
                if existing and existing != split:
                    findings.append("evaluation splits must not reuse prompts")
                seen_prompts[prompt] = split

        candidate_by_id = {str(result.get("id") or ""): result for result in routing_results}
        holdout_results = [
            candidate_by_id.get(str(case.get("id") or ""), {"id": str(case.get("id") or ""), "passed": False})
            for case in splits["holdout"]
        ]
        candidate_passed = bool(holdout_results) and all(bool(item.get("passed")) for item in holdout_results)
        if splits["holdout"] and not candidate_passed:
            findings.append("candidate failed one or more isolated holdout cases")

        baseline_results: list[dict[str, Any]] = []
        baseline_passed: bool | None = None
        if baseline.get("revision_id"):
            methods = self._published_routing_methods(project_id)
            available = {str(method.get("slug") or "") for method in methods}
            router = MethodRouter()
            for case in splits["holdout"]:
                expected = str(case.get("expected_method") or "")
                decision = router.select(methods, str(case.get("prompt") or ""))
                passed = bool(case.get("prompt")) and (not expected or expected in available) and decision.selected_slug == (expected or None)
                baseline_results.append({"id": str(case.get("id") or ""), "passed": passed, "selected_method": decision.selected_slug})
            baseline_passed = bool(baseline_results) and all(item["passed"] for item in baseline_results)

        baseline_by_id = {item["id"]: item for item in baseline_results}
        regressed_case_ids = [
            str(item.get("id") or "")
            for item in holdout_results
            if baseline_by_id.get(str(item.get("id") or ""), {}).get("passed") and not item.get("passed")
        ]
        if regressed_case_ids:
            findings.append("candidate regresses one or more baseline holdout cases")

        mutation = self._evaluate_single_mutation(
            proposal,
            baseline_revision or {},
            protocol=protocol if isinstance(protocol, dict) else {},
        )
        findings.extend(mutation["findings"])
        cost = {
            "status": "not_metered",
            "baseline_body_bytes": len(str((baseline_revision or {}).get("body") or "").encode("utf-8")),
            "candidate_body_bytes": len(str(proposal.get("body") or "").encode("utf-8")),
        }

        passed = (
            protocol_valid
            and bool(baseline_revision)
            and len(splits["positive"]) >= 3
            and len(splits["near_negative"]) >= 2
            and len(splits["holdout"]) >= 2
            and not findings
            and candidate_passed
            and not regressed_case_ids
        )
        return {
            "required": True,
            "passed": passed,
            "status": "passed" if passed else "failed",
            "protocol_revision": str((protocol or {}).get("revision") or ""),
            "positive_case_count": len(splits["positive"]),
            "near_negative_case_count": len(splits["near_negative"]),
            "holdout": {
                "case_count": len(splits["holdout"]),
                "candidate_passed": candidate_passed,
                "baseline_passed": baseline_passed,
                "candidate_results": holdout_results,
                "baseline_results": baseline_results,
                "regressed_case_ids": regressed_case_ids,
            },
            "mutation": mutation,
            "cost": cost,
            "findings": findings,
        }

    @staticmethod
    def _evaluate_single_mutation(
        proposal: dict[str, Any],
        baseline_revision: dict[str, Any],
        *,
        protocol: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify that a self-improvement names and changes one method dimension."""
        mutation = protocol.get("mutation") if isinstance(protocol.get("mutation"), dict) else {}
        declared = mutation.get("dimensions") if isinstance(mutation.get("dimensions"), list) else []
        declared = [str(value) for value in declared if str(value)]
        findings: list[str] = []
        if len(declared) != 1 or declared[0] not in _MUTATION_DIMENSIONS:
            findings.append("evaluation protocol must declare exactly one supported mutation dimension")
        if len(str(mutation.get("rationale") or "").strip()) < 24:
            findings.append("evaluation protocol requires a non-trivial mutation rationale")

        baseline_manifest = baseline_revision.get("manifest") if isinstance(baseline_revision.get("manifest"), dict) else {}
        candidate_manifest = proposal.get("manifest") if isinstance(proposal.get("manifest"), dict) else {}
        observed: list[str] = []
        for dimension in _MUTATION_DIMENSIONS:
            baseline_value: Any = baseline_revision.get("body") if dimension == "body" else baseline_manifest.get(dimension)
            candidate_value: Any = proposal.get("body") if dimension == "body" else candidate_manifest.get(dimension)
            if baseline_value != candidate_value:
                observed.append(dimension)
        if len(observed) != 1:
            findings.append("candidate must change exactly one supported method dimension")
        elif declared and observed[0] != declared[0]:
            findings.append("declared mutation dimension does not match the candidate diff")

        return {
            "passed": not findings,
            "declared_dimensions": declared,
            "observed_dimensions": observed,
            "rationale": str(mutation.get("rationale") or ""),
            "findings": findings,
        }

    @staticmethod
    def _routing_method(proposal: dict[str, Any]) -> dict[str, Any]:
        manifest = proposal.get("manifest") if isinstance(proposal.get("manifest"), dict) else {}
        routing_manifest = dict(manifest)
        distillation = manifest.get("distillation")
        if (
            not isinstance(routing_manifest.get("trigger_contract"), dict)
            and isinstance(distillation, dict)
            and isinstance(distillation.get("trigger_contract"), dict)
        ):
            # Source-derived methods keep their authoritative contract inside
            # distillation; expose it in the router's stable manifest slot.
            routing_manifest["trigger_contract"] = distillation["trigger_contract"]
        return {
            "slug": str(manifest.get("task_family") or ""),
            "manifest": routing_manifest,
            "applicability": manifest.get("applicability") or [],
            "exclusions": manifest.get("exclusions") or [],
        }

    @staticmethod
    def _normalized_quote(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

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
