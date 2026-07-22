"""Detect repeatable methods from accepted, project-scoped output history."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any

from app.knowledge.growth_contracts import MethodProposal
from app.knowledge.growth_repository import GrowthRepository


_EXCLUDED_FEEDBACK = {"corrected", "rejected"}
_DETECTOR_REVISION = "method-detector-v2"


class MethodDetector:
    def __init__(self, repository: GrowthRepository) -> None:
        self.repository = repository

    def detect(
        self, project_id: str, *, minimum_uses: int = 3
    ) -> list[dict[str, Any]]:
        if minimum_uses < 3:
            raise ValueError("automatic method detection requires at least three uses")
        groups: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
        for output in self.repository.list_outputs(
            project_id, status="accepted", limit=500
        ):
            metadata = output.get("metadata") or {}
            candidate = metadata.get("method_candidate") or {}
            family = str(metadata.get("task_family") or "").strip()
            if not family or not str(candidate.get("body") or "").strip():
                continue
            if metadata.get("security_failure") or metadata.get("permission_failure"):
                continue
            feedback_types = {
                str(item.get("feedback_type") or "")
                for item in self.repository.list_feedback(
                    project_id, output_id=output["id"], limit=500
                )
            }
            if feedback_types & _EXCLUDED_FEEDBACK:
                continue
            key = (
                family,
                self._contract_key(metadata.get("input_contract")),
                self._contract_key(metadata.get("output_contract")),
                str(metadata.get("method_lineage") or output.get("method_revision_id") or "none"),
            )
            execution_identity = self._root_execution_identity(project_id, output)
            current = groups[key].get(execution_identity)
            if current is None or str(output.get("created_at") or "") < str(
                current.get("created_at") or ""
            ):
                groups[key][execution_identity] = output

        proposals: list[dict[str, Any]] = []
        for key, unique_uses in sorted(groups.items(), key=lambda item: item[0]):
            if len(unique_uses) < minimum_uses:
                continue
            outputs = sorted(unique_uses.values(), key=lambda item: (str(item.get("created_at") or ""), item["id"]))
            selected = outputs[:minimum_uses]
            candidate = (selected[0].get("metadata") or {}).get("method_candidate") or {}
            candidate_manifest = dict(candidate.get("manifest") or {})
            observed_steps = self._observed_steps(str(candidate.get("body") or ""))
            manifest = {
                **candidate_manifest,
                "task_family": key[0],
                "prompt_only": bool(candidate_manifest.get("prompt_only", True)),
                "applicability": list(candidate_manifest.get("applicability") or [key[0]]),
                "exclusions": list(candidate_manifest.get("exclusions") or []),
                "inputs": list(candidate_manifest.get("inputs") or [{"name": "task_input"}]),
                "outputs": list(candidate_manifest.get("outputs") or [{"name": "task_output"}]),
                "steps": list(candidate_manifest.get("steps") or observed_steps or ["Execute the observed workflow"]),
                "evidence_rules": list(candidate_manifest.get("evidence_rules") or ["Use registered project evidence"]),
                "failure_handling": list(candidate_manifest.get("failure_handling") or ["Stop and report missing evidence"]),
                "eval_cases": list(candidate_manifest.get("eval_cases") or []),
                "detector_revision": _DETECTOR_REVISION,
                "comparable_contract": {
                    "input": key[1],
                    "output": key[2],
                    "method_lineage": key[3],
                },
                "inferred_fields_require_review": True,
            }
            proposals.append(
                self.create_proposal(
                    project_id,
                    key[0],
                    str(candidate["body"]),
                    [item["id"] for item in selected],
                    manifest,
                )
            )
        return proposals

    def create_proposal(
        self,
        project_id: str,
        slug: str,
        body: str,
        output_ids: list[str],
        manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(output_ids))
        if len(unique_ids) < 3:
            raise ValueError("method proposal requires at least three comparable outputs")
        for output_id in unique_ids:
            output = self.repository.get_output(project_id, output_id)
            if not output or output.get("status") != "accepted":
                raise ValueError("automatic method proposal outputs must be accepted in one project")
        normalized_manifest = self._normalized_manifest(slug, body, manifest or {})
        return self._save_proposal(
            project_id=project_id,
            slug=slug,
            body=body,
            output_ids=unique_ids,
            manifest=normalized_manifest,
            rationale="Detected from comparable accepted outputs",
        )

    def create_user_proposal(
        self,
        project_id: str,
        slug: str,
        body: str,
        output_ids: list[str],
        manifest: dict[str, Any] | None = None,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        if not actor_id:
            raise ValueError("actor_id is required for a user proposal")
        unique_ids = list(dict.fromkeys(output_ids))
        for output_id in unique_ids:
            if not self.repository.get_output(project_id, output_id):
                raise ValueError("user proposal output belongs to another project or is missing")
        return self._save_proposal(
            project_id=project_id,
            slug=slug,
            body=body,
            output_ids=unique_ids,
            manifest={
                **(manifest or {}),
                "task_family": slug,
                "prompt_only": bool((manifest or {}).get("prompt_only", True)),
                "user_created": True,
                "created_by": actor_id,
            },
            rationale=f"User-created proposal by {actor_id}",
        )

    def _save_proposal(
        self,
        *,
        project_id: str,
        slug: str,
        body: str,
        output_ids: list[str],
        manifest: dict[str, Any],
        rationale: str,
    ) -> dict[str, Any]:
        if not slug.strip() or not body.strip():
            raise ValueError("method slug and body are required")
        fingerprint = json.dumps(
            {
                "project_id": project_id,
                "slug": slug,
                "body": body,
                "outputs": output_ids,
                "manifest": manifest,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        proposal_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        existing = self.repository.get_method_proposal(project_id, proposal_id)
        if existing:
            return existing
        proposal = MethodProposal(
            id=proposal_id,
            project_id=project_id,
            operation="create",
            body=body,
            manifest=manifest,
            source_output_ids=output_ids,
            rationale=rationale,
        )
        return self.repository.save_method_proposal(proposal)

    def _root_execution_identity(
        self, project_id: str, output: dict[str, Any]
    ) -> str:
        run_id = str(output.get("run_id") or "")
        if not run_id:
            return f"output:{output['id']}"
        visited: set[str] = set()
        current = run_id
        while current and current not in visited:
            visited.add(current)
            run = self.repository.get_run(project_id, current)
            retry_of = str((run or {}).get("retry_of") or "")
            if not retry_of:
                break
            current = retry_of
        return f"run:{current or run_id}"

    @staticmethod
    def _contract_key(value: Any) -> str:
        if value in (None, ""):
            return "unspecified"
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _observed_steps(body: str) -> list[str]:
        steps: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in {".", ")"}:
                steps.append(stripped[2:].strip())
        return [step for step in steps if step]

    @classmethod
    def _normalized_manifest(
        cls, slug: str, body: str, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **manifest,
            "task_family": slug,
            "prompt_only": bool(manifest.get("prompt_only", True)),
            "applicability": list(manifest.get("applicability") or [slug]),
            "exclusions": list(manifest.get("exclusions") or []),
            "inputs": list(manifest.get("inputs") or [{"name": "task_input"}]),
            "outputs": list(manifest.get("outputs") or [{"name": "task_output"}]),
            "steps": list(manifest.get("steps") or cls._observed_steps(body) or ["Execute the observed workflow"]),
            "evidence_rules": list(manifest.get("evidence_rules") or ["Use registered project evidence"]),
            "failure_handling": list(manifest.get("failure_handling") or ["Stop and report missing evidence"]),
            "eval_cases": list(manifest.get("eval_cases") or []),
            "detector_revision": manifest.get("detector_revision", _DETECTOR_REVISION),
            "inferred_fields_require_review": bool(manifest.get("inferred_fields_require_review", True)),
        }
