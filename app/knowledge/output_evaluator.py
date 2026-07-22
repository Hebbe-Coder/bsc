"""Deterministic output quality evaluation with persisted component findings."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Callable

from app.knowledge.growth_contracts import OutputEvaluation
from app.knowledge.growth_repository import GrowthRepository


ComponentEvaluator = Callable[[dict[str, Any]], dict[str, float]]
_COMPONENTS = ("groundedness", "task_fit", "usefulness", "coherence", "format_quality")


class OutputEvaluator:
    def __init__(
        self,
        repository: GrowthRepository,
        *,
        type_evaluators: dict[str, ComponentEvaluator] | None = None,
    ) -> None:
        self.repository = repository
        self.type_evaluators = type_evaluators or {}

    def evaluate(
        self,
        *,
        project_id: str,
        output_id: str,
        components: dict[str, float] | None = None,
        findings: list[str] | None = None,
        evaluator_revision: str = "deterministic-v1",
        latency_ms: int = 0,
        evaluator_available: bool = True,
    ) -> dict[str, Any]:
        output = self.repository.get_output(project_id, output_id)
        if not output:
            raise KeyError("output not found in project")
        if not evaluator_revision.strip():
            raise ValueError("evaluator_revision is required")

        if not evaluator_available:
            return self._record_unavailable(
                project_id=project_id,
                output_id=output_id,
                evaluator_revision=evaluator_revision,
                findings=findings or ["evaluator unavailable"],
                latency_ms=latency_ms,
            )

        if components is None:
            evaluator = self.type_evaluators.get(str(output.get("kind") or ""))
            if evaluator is None:
                return self._record_unavailable(
                    project_id=project_id,
                    output_id=output_id,
                    evaluator_revision=evaluator_revision,
                    findings=findings or ["no evaluator is configured for this output type"],
                    latency_ms=latency_ms,
                )
            components = evaluator(output)

        normalized = self._validate_components(components)
        self._enforce_evidence_ancestry(output, normalized["groundedness"])
        evaluation = OutputEvaluation(
            project_id=project_id,
            output_id=output_id,
            evaluator_revision=evaluator_revision,
            latency_ms=latency_ms,
            findings=findings or [],
            **normalized,
        )
        existing = self._existing(project_id, output_id, evaluator_revision)
        if existing:
            self._assert_immutable(existing, evaluation)
            return existing

        self._transition_to_evaluating(project_id, output_id, str(output.get("status") or ""))
        return self.repository.save_output_evaluation(evaluation)

    @staticmethod
    def _validate_components(components: dict[str, float]) -> dict[str, float]:
        if set(components) != set(_COMPONENTS):
            raise ValueError(f"evaluation components must be exactly: {', '.join(_COMPONENTS)}")
        normalized: dict[str, float] = {}
        for key in _COMPONENTS:
            value = float(components[key])
            if not math.isfinite(value) or value < 0 or value > 1:
                raise ValueError(f"evaluation component {key} must be a finite value between 0 and 1")
            normalized[key] = value
        return normalized

    def _enforce_evidence_ancestry(self, output: dict[str, Any], groundedness: float) -> None:
        if not bool((output.get("metadata") or {}).get("requires_evidence", True)):
            return
        external_sources: set[str] = set()
        for source_id in output.get("source_refs") or []:
            source = self.repository.get_source(output["project_id"], source_id)
            if self._is_external_evidence(source):
                external_sources.add(source_id)
        for page_id in output.get("page_refs") or []:
            for citation in self.repository.list_citations(output["project_id"], page_id):
                source_id = str(citation.get("source_id") or "")
                source = self.repository.get_source(output["project_id"], source_id)
                if self._is_external_evidence(source):
                    external_sources.add(source_id)
        if groundedness > 0 and not external_sources:
            raise ValueError("groundedness above zero requires external evidence ancestry")

    @staticmethod
    def _is_external_evidence(source: dict[str, Any] | None) -> bool:
        return bool(
            source
            and str(source.get("source_type") or "")
            not in {"generated_output", "output", "synthetic"}
            and str(source.get("status") or "") in {"eligible", "processed"}
        )

    def _existing(self, project_id: str, output_id: str, revision: str) -> dict[str, Any] | None:
        row = self.repository._execute(
            "SELECT * FROM knowledge_output_evaluations WHERE project_id=? AND output_id=? AND evaluator_revision=?",
            (project_id, output_id, revision),
        ).fetchone()
        return self.repository._decode_growth(row, ("findings_json",))

    @staticmethod
    def _assert_immutable(existing: dict[str, Any], evaluation: OutputEvaluation) -> None:
        expected = evaluation.model_dump(mode="json")
        fields = (*_COMPONENTS, "quality", "status", "latency_ms")
        conflicts = [field for field in fields if existing.get(field) != expected.get(field)]
        if list(existing.get("findings") or []) != list(expected.get("findings") or []):
            conflicts.append("findings")
        if conflicts:
            raise ValueError(f"evaluation revision is immutable; conflicting fields: {', '.join(conflicts)}")

    def _transition_to_evaluating(self, project_id: str, output_id: str, current_status: str) -> None:
        if current_status in {"filed", "archived", "superseded"}:
            raise ValueError(f"output in {current_status} state cannot be evaluated")
        self.repository._execute(
            "UPDATE knowledge_outputs SET status='evaluating',updated_at=? WHERE project_id=? AND id=?",
            (self.repository._now(), project_id, output_id),
        )
        self.repository._commit()

    def _record_unavailable(
        self,
        *,
        project_id: str,
        output_id: str,
        evaluator_revision: str,
        findings: list[str],
        latency_ms: int,
    ) -> dict[str, Any]:
        existing = self._existing(project_id, output_id, evaluator_revision)
        if existing:
            if existing.get("status") != "unavailable":
                raise ValueError("evaluation revision is immutable")
            return {**existing, "quality": None, "score_available": False}
        evaluation_id = hashlib.sha256(
            f"{project_id}|{output_id}|{evaluator_revision}".encode("utf-8")
        ).hexdigest()[:24]
        self.repository._execute(
            "INSERT INTO knowledge_output_evaluations "
            "(id,project_id,output_id,groundedness,task_fit,usefulness,coherence,format_quality,quality,status,evaluator_revision,findings_json,latency_ms,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                evaluation_id,
                project_id,
                output_id,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0,
                "unavailable",
                evaluator_revision,
                self.repository._json_dumps(findings),
                max(0, int(latency_ms)),
                self.repository._now(),
            ),
        )
        self.repository._commit()
        row = self._existing(project_id, output_id, evaluator_revision) or {}
        return {**row, "quality": None, "score_available": False}
