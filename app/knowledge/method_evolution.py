"""Governed, durable experiments for improving published knowledge methods."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.knowledge.growth_contracts import (
    KnowledgeLineageEdge,
    MethodEvolutionDecision,
    MethodEvolutionRun,
    MethodEvolutionStatus,
    MethodProposal,
    is_verified_output_status,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


METHOD_EVOLUTION_RUN_TYPE = "method_evolution"
METHOD_EVOLUTION_PROTOCOL = "method-evolution-v1"
SUPPORTED_MUTATION_DIMENSIONS = frozenset(
    {
        "body",
        "trigger_contract",
        "applicability",
        "exclusions",
        "steps",
        "evidence_rules",
        "failure_handling",
    }
)
_ALLOWED_MANIFEST_VARIATIONS = {"evaluation_protocol", "eval_cases"}


class MethodEvolutionError(ValueError):
    """Raised when an experiment cannot prove its baseline or isolation."""


class MethodEvolutionService:
    """Run one mutation against immutable evidence without publishing it.

    This is intentionally not an autonomous writer. A caller supplies the
    candidate revision and its isolated routing suite. The service proves the
    active baseline, constrains the candidate to one domain change, delegates
    scoring to the existing evaluator, and leaves every passing proposal for
    the existing MethodGate to review and publish.
    """

    def __init__(self, repository: GrowthRepository) -> None:
        self.repository = repository

    def start(
        self,
        *,
        project_id: str,
        method_id: str,
        candidate_body: str,
        candidate_manifest: dict[str, Any],
        supporting_output_ids: list[str],
        mutation_dimension: str,
        rationale: str,
        idempotency_key: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        actor = actor_id.strip()
        key = idempotency_key.strip()
        dimension = mutation_dimension.strip()
        if not actor:
            raise MethodEvolutionError("actor_id is required for a method evolution experiment")
        if not key:
            raise MethodEvolutionError("idempotency_key is required for a method evolution experiment")
        if dimension not in SUPPORTED_MUTATION_DIMENSIONS:
            raise MethodEvolutionError("unsupported method evolution mutation dimension")
        if len(rationale.strip()) < 24:
            raise MethodEvolutionError("method evolution rationale must explain the change in at least 24 characters")

        method = self.repository.get_method(project_id, method_id)
        if not method:
            raise KeyError("method not found in project")
        if str(method.get("status") or "") != "published":
            raise MethodEvolutionError("method evolution requires a published method")
        baseline_revision_id = str(method.get("active_revision_id") or "")
        baseline = (
            self.repository.get_method_revision(project_id, baseline_revision_id)
            if baseline_revision_id
            else None
        )
        if not baseline or str(baseline.get("status") or "") != "published":
            raise MethodEvolutionError("method evolution requires the active published baseline revision")

        output_ids = self._verified_supporting_outputs(
            project_id=project_id,
            baseline_revision_id=baseline_revision_id,
            supporting_output_ids=supporting_output_ids,
        )
        manifest = self._prepare_manifest(
            method_slug=str(method.get("slug") or ""),
            baseline_manifest=baseline.get("manifest") or {},
            candidate_manifest=candidate_manifest,
            baseline_revision_id=baseline_revision_id,
            mutation_dimension=dimension,
            rationale=rationale,
        )
        self._assert_single_production_mutation(
            baseline_body=str(baseline.get("body") or ""),
            baseline_manifest=baseline.get("manifest") or {},
            candidate_body=candidate_body,
            candidate_manifest=manifest,
            mutation_dimension=dimension,
        )

        fingerprint = self._fingerprint(
            project_id=project_id,
            method_id=method_id,
            baseline_revision_id=baseline_revision_id,
            candidate_body=candidate_body,
            candidate_manifest=manifest,
            supporting_output_ids=output_ids,
            mutation_dimension=dimension,
            rationale=rationale,
        )
        existing = self.repository.get_method_evolution_run_by_idempotency(
            project_id, key
        )
        if existing:
            if str(existing.get("input_fingerprint") or "") != fingerprint:
                raise MethodEvolutionError("method evolution idempotency key is bound to different input")
            return existing, True

        proposal = self._create_candidate_proposal(
            project_id=project_id,
            method_id=method_id,
            candidate_body=candidate_body,
            candidate_manifest=manifest,
            supporting_output_ids=output_ids,
            rationale=rationale,
        )
        experiment_id = hashlib.sha256(
            f"{project_id}|{method_id}|{key}".encode("utf-8")
        ).hexdigest()[:24]
        run = MethodEvolutionRun(
            id=experiment_id,
            project_id=project_id,
            method_id=method_id,
            baseline_revision_id=baseline_revision_id,
            mutation_dimension=dimension,
            rationale=rationale.strip(),
            supporting_output_ids=output_ids,
            candidate_proposal_id=str(proposal["id"]),
            input_fingerprint=fingerprint,
            rollback_revision_id=baseline_revision_id,
            idempotency_key=key,
            actor_id=actor,
        )
        persisted, created = self.repository.create_method_evolution_run(run)
        if not created:
            return persisted, True

        try:
            self.repository.create_run(
                KnowledgeRun(
                    id=experiment_id,
                    project_id=project_id,
                    run_type=METHOD_EVOLUTION_RUN_TYPE,
                    trigger="manual",
                    status=RunStatus.RUNNING,
                    actor_id=actor,
                    input_refs={
                        "method_id": method_id,
                        "baseline_revision_id": baseline_revision_id,
                        "mutation_dimension": dimension,
                        "rationale": rationale.strip(),
                        "supporting_output_ids": output_ids,
                        "candidate_proposal_id": proposal["id"],
                        "idempotency_key": key,
                        "input_fingerprint": fingerprint,
                    },
                )
            )
            self._add_lineage(
                project_id=project_id,
                experiment_id=experiment_id,
                baseline_revision_id=baseline_revision_id,
                candidate_proposal_id=str(proposal["id"]),
                supporting_output_ids=output_ids,
            )
            self.repository.append_run_event(
                project_id=project_id,
                run_id=experiment_id,
                event_type="knowledge.method_evolution.candidate_proposed",
                payload={
                    "candidate_proposal_id": proposal["id"],
                    "baseline_revision_id": baseline_revision_id,
                    "mutation_dimension": dimension,
                },
            )
        except Exception as exc:
            return self._finish_failed(
                project_id=project_id,
                experiment_id=experiment_id,
                error=exc,
            ), False

        try:
            evaluation = MethodEvaluator(self.repository).evaluate(proposal)
        except Exception as exc:
            return self._finish_failed(
                project_id=project_id,
                experiment_id=experiment_id,
                error=exc,
            ), False

        evaluator_status = str(evaluation.get("evaluator_status") or "failed")
        eligible = bool(evaluation.get("eligible"))
        if evaluator_status == "unavailable":
            status = MethodEvolutionStatus.UNAVAILABLE
            decision = MethodEvolutionDecision.UNAVAILABLE
            runtime_status = RunStatus.UNAVAILABLE
        elif eligible:
            status = MethodEvolutionStatus.ELIGIBLE_FOR_REVIEW
            decision = MethodEvolutionDecision.RETAIN
            runtime_status = RunStatus.COMPLETED
        else:
            status = MethodEvolutionStatus.DISCARDED
            decision = MethodEvolutionDecision.DISCARD
            runtime_status = RunStatus.COMPLETED

        evaluation_projection = self._evaluation_projection(evaluation)
        persisted = self.repository.update_method_evolution_run(
            project_id,
            experiment_id,
            evaluation_summary=evaluation,
            decision=decision.value,
            status=status.value,
        )
        self.repository.append_run_event(
            project_id=project_id,
            run_id=experiment_id,
            event_type="knowledge.method_evolution.evaluated",
            payload={
                "decision": decision.value,
                "status": status.value,
                "evaluation": evaluation_projection,
            },
        )
        self.repository.update_run_status(
            project_id,
            experiment_id,
            runtime_status,
            error="" if runtime_status == RunStatus.COMPLETED else "method evaluation replay is unavailable",
            output_refs={
                "experiment_id": experiment_id,
                "baseline_revision_id": baseline_revision_id,
                "candidate_proposal_id": proposal["id"],
                "decision": decision.value,
                "rollback_revision_id": baseline_revision_id,
                "evaluation": evaluation_projection,
                "publication_status": "review_required" if eligible else "not_publishable",
            },
        )
        return persisted, False

    def _verified_supporting_outputs(
        self,
        *,
        project_id: str,
        baseline_revision_id: str,
        supporting_output_ids: list[str],
    ) -> list[str]:
        output_ids = list(dict.fromkeys(str(value).strip() for value in supporting_output_ids if str(value).strip()))
        if len(output_ids) < 3:
            raise MethodEvolutionError("method evolution requires at least three distinct supporting outputs")
        for output_id in output_ids:
            output = self.repository.get_output(project_id, output_id)
            if not output:
                raise MethodEvolutionError("method evolution supporting output is missing or belongs to another project")
            if not is_verified_output_status(output.get("status")):
                raise MethodEvolutionError("method evolution supporting outputs must be verified")
            if str(output.get("method_revision_id") or "") != baseline_revision_id:
                raise MethodEvolutionError("method evolution supporting outputs must be produced by the active baseline revision")
            evaluations = self.repository.list_output_evaluations(project_id, output_id, limit=500)
            if not any(str(item.get("status") or "") == "completed" for item in evaluations):
                raise MethodEvolutionError("method evolution supporting outputs require immutable completed evaluations")
        return output_ids

    @staticmethod
    def _prepare_manifest(
        *,
        method_slug: str,
        baseline_manifest: dict[str, Any],
        candidate_manifest: dict[str, Any],
        baseline_revision_id: str,
        mutation_dimension: str,
        rationale: str,
    ) -> dict[str, Any]:
        try:
            manifest = json.loads(json.dumps(candidate_manifest, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise MethodEvolutionError("candidate method manifest must be JSON-compatible") from exc
        if not isinstance(manifest, dict):
            raise MethodEvolutionError("candidate method manifest must be an object")
        if str(manifest.get("task_family") or "") != method_slug:
            raise MethodEvolutionError("candidate task_family must remain bound to the published method slug")
        # The service owns the protocol identity and baseline binding. Callers
        # cannot substitute another baseline or claim a different mutation.
        manifest["evaluation_protocol"] = {
            "revision": METHOD_EVOLUTION_PROTOCOL,
            "baseline_revision_id": baseline_revision_id,
            "mutation": {
                "dimensions": [mutation_dimension],
                "rationale": rationale.strip(),
            },
        }
        return manifest

    @staticmethod
    def _assert_single_production_mutation(
        *,
        baseline_body: str,
        baseline_manifest: dict[str, Any],
        candidate_body: str,
        candidate_manifest: dict[str, Any],
        mutation_dimension: str,
    ) -> None:
        baseline = dict(baseline_manifest)
        candidate = dict(candidate_manifest)
        for key in _ALLOWED_MANIFEST_VARIATIONS:
            baseline.pop(key, None)
            candidate.pop(key, None)
        changed_manifest_keys = {
            key
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        observed = set(changed_manifest_keys)
        if baseline_body != candidate_body:
            observed.add("body")
        if observed != {mutation_dimension}:
            names = ", ".join(sorted(observed)) or "none"
            raise MethodEvolutionError(
                f"candidate must change exactly the declared production dimension; observed: {names}"
            )

    def _create_candidate_proposal(
        self,
        *,
        project_id: str,
        method_id: str,
        candidate_body: str,
        candidate_manifest: dict[str, Any],
        supporting_output_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        if not candidate_body.strip():
            raise MethodEvolutionError("candidate method body is required")
        fingerprint = json.dumps(
            {
                "project_id": project_id,
                "method_id": method_id,
                "operation": "update",
                "body": candidate_body,
                "manifest": candidate_manifest,
                "source_output_ids": supporting_output_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        proposal_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        existing = self.repository.get_method_proposal(project_id, proposal_id)
        if existing:
            return existing
        return self.repository.save_method_proposal(
            MethodProposal(
                id=proposal_id,
                project_id=project_id,
                method_id=method_id,
                operation="update",
                body=candidate_body,
                manifest=candidate_manifest,
                source_output_ids=supporting_output_ids,
                rationale=f"Single-variable method evolution: {rationale.strip()}",
            )
        )

    def _add_lineage(
        self,
        *,
        project_id: str,
        experiment_id: str,
        baseline_revision_id: str,
        candidate_proposal_id: str,
        supporting_output_ids: list[str],
    ) -> None:
        edges = [
            ("method_revision", baseline_revision_id, "method_proposal", candidate_proposal_id, "method_revision_baselines_method_proposal"),
            ("run", experiment_id, "method_proposal", candidate_proposal_id, "run_evaluates_method_proposal"),
            *[
                ("output", output_id, "method_proposal", candidate_proposal_id, "output_supports_method_proposal")
                for output_id in supporting_output_ids
            ],
        ]
        for from_type, from_id, to_type, to_id, relation in edges:
            self.repository.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id=project_id,
                    from_type=from_type,
                    from_id=from_id,
                    to_type=to_type,
                    to_id=to_id,
                    relation=relation,
                )
            )

    @staticmethod
    def _fingerprint(**values: Any) -> str:
        encoded = json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _evaluation_projection(evaluation: dict[str, Any]) -> dict[str, Any]:
        evolution = evaluation.get("evolution") if isinstance(evaluation.get("evolution"), dict) else {}
        return {
            "eligible": bool(evaluation.get("eligible")),
            "evaluator_status": str(evaluation.get("evaluator_status") or "failed"),
            "average_quality": evaluation.get("average_quality"),
            "groundedness": evaluation.get("groundedness"),
            "regression_failures": evaluation.get("regression_failures"),
            "evolution_passed": bool(evolution.get("passed")),
            "holdout": evolution.get("holdout") if isinstance(evolution.get("holdout"), dict) else {},
            "findings": list(evaluation.get("findings") or []),
        }

    def _finish_failed(
        self,
        *,
        project_id: str,
        experiment_id: str,
        error: Exception,
    ) -> dict[str, Any]:
        summary = {
            "eligible": False,
            "evaluator_status": "failed",
            "findings": [str(error)[:2_000] or error.__class__.__name__],
        }
        persisted = self.repository.update_method_evolution_run(
            project_id,
            experiment_id,
            evaluation_summary=summary,
            decision=MethodEvolutionDecision.DISCARD.value,
            status=MethodEvolutionStatus.FAILED.value,
        )
        try:
            self.repository.update_run_status(
                project_id,
                experiment_id,
                RunStatus.FAILED,
                error=summary["findings"][0],
                output_refs={
                    "experiment_id": experiment_id,
                    "decision": MethodEvolutionDecision.DISCARD.value,
                    "publication_status": "not_publishable",
                    "evaluation": self._evaluation_projection(summary),
                },
            )
        except Exception:
            # Preserve the primary exception path; the experiment row remains
            # durable and is enough for later recovery/audit.
            pass
        return persisted
