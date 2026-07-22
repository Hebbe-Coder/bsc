"""Route output feedback into governed proposals or regression cases."""

from __future__ import annotations

from typing import Any

from app.knowledge.growth_contracts import (
    FeedbackStatus,
    FeedbackType,
    KnowledgeLineageEdge,
    MethodProposal,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import WikiOperation, WikiProposal


_WRITE_ROLES = {"project_writer", "project_admin", "admin", "system"}
_ADMIN_ROLES = {"project_admin", "admin", "system"}
_GENERATED_SOURCE_TYPES = {"generated_output", "output", "synthetic"}


class FeedbackRouter:
    def __init__(self, repository: GrowthRepository) -> None:
        self.repository = repository

    def process(
        self,
        project_id: str,
        feedback_id: str,
        *,
        actor_id: str = "",
        actor_role: str = "system",
    ) -> dict[str, Any]:
        feedback = self.repository.get_feedback(project_id, feedback_id)
        if not feedback:
            raise KeyError("feedback not found in project")
        self._authorize(feedback, actor_id=actor_id, actor_role=actor_role)
        if feedback.get("status") == FeedbackStatus.PROCESSED.value:
            reference = str(feedback.get("processed_ref") or "")
            return {
                "route": "already_processed",
                "feedback_id": feedback_id,
                "case_id": reference,
                "reference_id": reference,
            }

        output = self.repository.get_output(project_id, feedback["output_id"])
        if not output:
            raise KeyError("feedback output not found in project")
        try:
            self._link_feedback(feedback, output)
            route, reference = self._route(feedback, output, actor_role=actor_role)
            self.repository.mark_feedback_processed(project_id, feedback_id, reference)
            return {
                "route": route,
                "feedback_id": feedback_id,
                "case_id": reference,
                "reference_id": reference,
            }
        except Exception as exc:
            self._mark_failed(project_id, feedback_id, str(exc))
            raise

    @staticmethod
    def _authorize(feedback: dict[str, Any], *, actor_id: str, actor_role: str) -> None:
        if actor_role not in _WRITE_ROLES:
            raise PermissionError("feedback processing requires project write permission")
        owner = str(feedback.get("actor_id") or "")
        if actor_role not in _ADMIN_ROLES and owner and actor_id != owner:
            raise PermissionError("feedback can only be processed by its actor or an administrator")

    def _route(
        self,
        feedback: dict[str, Any],
        output: dict[str, Any],
        *,
        actor_role: str,
    ) -> tuple[str, str]:
        try:
            feedback_type = FeedbackType(feedback["feedback_type"])
        except ValueError as exc:
            raise ValueError("unsupported feedback route") from exc

        if feedback_type is FeedbackType.CORRECTED:
            correction = str(feedback.get("correction") or "").strip()
            if not correction:
                raise ValueError("corrected feedback requires correction content")
            case = self.repository.upsert_eval_case(
                output["project_id"],
                f"feedback:{feedback['id']}",
                "output_correction",
                {
                    "correction": correction,
                    "output_id": output["id"],
                    "method_revision_id": output.get("method_revision_id", ""),
                    "context_revision": output.get("context_revision", ""),
                },
            )
            return "regression_case", case["id"]

        if feedback_type is FeedbackType.REJECTED:
            case = self.repository.upsert_eval_case(
                output["project_id"],
                f"feedback:{feedback['id']}",
                "output_failure",
                {
                    "output_id": output["id"],
                    "comment": feedback.get("comment", ""),
                    "method_revision_id": output.get("method_revision_id", ""),
                    "context_revision": output.get("context_revision", ""),
                    "evaluation": output.get("quality") or {},
                },
            )
            return "failure_pattern", case["id"]

        if feedback_type is FeedbackType.ACCEPTED:
            return self._route_accepted(feedback, output)

        if feedback_type is FeedbackType.REUSED:
            return self._route_reused(output)

        if feedback_type is FeedbackType.RATED:
            if feedback.get("rating") is None:
                raise ValueError("rated feedback requires a rating")
            return "observation", output["id"]

        raise ValueError("unsupported feedback route")

    def _route_accepted(
        self, feedback: dict[str, Any], output: dict[str, Any]
    ) -> tuple[str, str]:
        if output.get("status") != "accepted":
            raise ValueError("accepted feedback cannot promote an output that has not passed evaluation")
        proposal_config = (output.get("metadata") or {}).get("wiki_proposal") or {}
        raw_operations = proposal_config.get("operations") or []
        if not raw_operations:
            return "accepted_output", output["id"]

        external_sources = self._external_sources(output)
        if not external_sources:
            raise ValueError("Wiki routing requires external A-layer evidence")
        operations = [WikiOperation.model_validate(item) for item in raw_operations]
        claimed_sources = {
            source_id for operation in operations for source_id in operation.source_ids
        }
        if not claimed_sources or not claimed_sources.issubset(external_sources):
            raise ValueError("Wiki proposal operations must cite registered external A-layer evidence")
        proposal = WikiProposal(
            project_id=output["project_id"],
            source_ids=sorted(external_sources),
            operations=operations,
            rationale=f"Accepted output feedback for {output['id']}",
        )
        saved = self.repository.create_proposal(
            proposal, actor_id=str(feedback.get("actor_id") or "")
        )
        self.repository.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=output["project_id"],
                from_type="output",
                from_id=output["id"],
                to_type="proposal",
                to_id=saved["id"],
                relation="output_proposes_page",
            )
        )
        return "wiki_proposal", saved["id"]

    def _route_reused(self, output: dict[str, Any]) -> tuple[str, str]:
        quality = float((output.get("quality") or {}).get("quality", 0))
        if output.get("status") != "accepted" or quality < 85:
            raise ValueError("method routing requires an accepted output with quality >= 85")
        config = (output.get("metadata") or {}).get("method_candidate") or {}
        body = str(config.get("body") or "").strip()
        if not body:
            return "accepted_reuse", output["id"]
        proposal = MethodProposal(
            project_id=output["project_id"],
            operation="create",
            body=body,
            manifest=config.get("manifest") or {},
            source_output_ids=[output["id"]],
            rationale="Accepted workflow was explicitly reused",
        )
        saved = self.repository.save_method_proposal(proposal)
        self.repository.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=output["project_id"],
                from_type="output",
                from_id=output["id"],
                to_type="method_proposal",
                to_id=saved["id"],
                relation="output_proposes_method",
            )
        )
        return "method_proposal", saved["id"]

    def _external_sources(self, output: dict[str, Any]) -> set[str]:
        sources: set[str] = set()
        for source_id in output.get("source_refs") or []:
            source = self.repository.get_source(output["project_id"], source_id)
            if (
                source
                and str(source.get("source_type") or "") not in _GENERATED_SOURCE_TYPES
                and str(source.get("status") or "") in {"eligible", "processed"}
            ):
                sources.add(source_id)
        return sources

    def _link_feedback(self, feedback: dict[str, Any], output: dict[str, Any]) -> None:
        self.repository.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=output["project_id"],
                from_type="feedback",
                from_id=feedback["id"],
                to_type="output",
                to_id=output["id"],
                relation="feedback_evaluates_output",
            )
        )

    def _mark_failed(self, project_id: str, feedback_id: str, reason: str) -> None:
        self.repository._execute(
            "UPDATE knowledge_output_feedback SET status='failed',processed_at=?,processed_ref=? "
            "WHERE project_id=? AND id=? AND status!='processed'",
            (self.repository._now(), f"error:{reason}"[:1000], project_id, feedback_id),
        )
        self.repository._commit()
