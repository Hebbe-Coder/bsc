"""Evidence-backed recommendations and approved Vault handoffs for DBOS Intake."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.artifacts import ArtifactGraphStore, DeliverableArtifact, IntakeSessionArtifact
from app.core.config import settings
from app.knowledge.vault import FilesystemWikiVault

from .intake import IntakeError, IntakeService


class IntakeEvidenceService:
    """Read admitted knowledge evidence without claiming a live Horizon lookup."""

    ADMITTED_STATUSES = {"eligible", "processed"}

    def __init__(self, store: ArtifactGraphStore, repository: Any | None = None) -> None:
        self.store = store
        self.repository = repository

    def recommend(self, session: IntakeSessionArtifact) -> IntakeSessionArtifact:
        IntakeService._ensure_enabled()
        if not session.tier:
            raise IntakeError("select an intake tier before generating recommendations")
        if self.repository is None or not hasattr(self.repository, "list_sources"):
            return self._set_unavailable(session, "knowledge repository is unavailable")

        candidates = [
            recommendation
            for source in self.repository.list_sources(session.project_id)
            if (recommendation := self._recommendation(source, session)) is not None
        ]
        session.recommendations = candidates[: {"lite": 2, "standard": 4, "full": 6}[session.tier]]
        session.recommendation_state = "available" if session.recommendations else "unavailable"
        if not session.recommendations:
            session.recommendations = [{
                "state": "unavailable",
                "reason": "no admitted source with a URL, capture time, and allowed lifecycle status",
            }]
        self.store.update(session)
        return session

    def export_handoff(self, session: IntakeSessionArtifact, *, actor_id: str, approved: bool) -> DeliverableArtifact:
        IntakeService._ensure_enabled()
        if not approved:
            raise IntakeError("Vault handoff requires an explicit approval")
        if not session.linked_mission_id:
            raise IntakeError("Vault handoff requires a converted Mission")
        if self.repository is None or not hasattr(self.repository, "get_vault"):
            raise IntakeError("knowledge repository is unavailable")
        mapping = self.repository.get_vault(session.project_id)
        root_value = str(settings.OBSIDIAN_VAULT_ROOT or "").strip()
        root = Path(root_value).resolve() if root_value else None
        if not mapping or root is None or not root.is_dir():
            raise IntakeError("managed Obsidian Vault is unavailable")

        relative_path = f"outputs/handoffs/{session.artifact_id}.md"
        content = self._handoff_content(session)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self._existing_handoff(session, content_hash)
        if existing is not None:
            return existing

        vault = FilesystemWikiVault(root, session.project_id, str(mapping.get("vault_path") or ""))
        staged = vault.contents
        staged[relative_path] = content
        vault.commit(staged, directories=("outputs/handoffs",))

        deliverable = DeliverableArtifact(
            project_id=session.project_id,
            label=f"Approved Intake handoff: {session.artifact_id}",
            kind="blindspot_intake_handoff",
            title=f"Intake handoff: {session.original_request[:120]}",
            summary="Explicitly approved DBOS Intake handoff exported to the managed Vault.",
            parent_ids=[session.artifact_id, session.linked_mission_id],
            source_agent="dbos_blindspot_intake",
            tags=["dbos", "blindspot_intake", "vault_handoff"],
            metadata={
                "vault_path": relative_path,
                "content_sha256": content_hash,
                "approved_by": actor_id.strip(),
                "approval_required": True,
                "source_reingestion": "prohibited",
            },
        )
        self.store.add(deliverable)
        session.handoff_path = relative_path
        session.handoff_sha256 = content_hash
        self.store.update(session)
        return deliverable

    def _set_unavailable(self, session: IntakeSessionArtifact, reason: str) -> IntakeSessionArtifact:
        session.recommendation_state = "unavailable"
        session.recommendations = [{"state": "unavailable", "reason": reason}]
        self.store.update(session)
        return session

    @classmethod
    def _recommendation(cls, source: dict[str, Any], session: IntakeSessionArtifact) -> dict[str, Any] | None:
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        origin = str(metadata.get("canonical_url") or metadata.get("source_url") or source.get("origin") or "").strip()
        captured_at = str(source.get("captured_at") or "").strip()
        if (
            str(source.get("status") or "") not in cls.ADMITTED_STATUSES
            or not origin.startswith(("https://", "http://"))
            or not captured_at
        ):
            return None
        summary = str(metadata.get("summary") or source.get("raw_content") or "").strip().replace("\n", " ")
        if not summary:
            return None
        return {
            "source_id": str(source.get("id") or ""),
            "source_url": origin,
            "captured_at": captured_at,
            "trust_level": str(source.get("trust_level") or "untrusted"),
            "status": str(source.get("status") or ""),
            "applicability": f"{session.domain} intake at {session.tier} tier",
            "summary": summary[:500],
        }

    def _existing_handoff(self, session: IntakeSessionArtifact, content_hash: str) -> DeliverableArtifact | None:
        for artifact in self.store.get_by_project(session.project_id):
            if (
                isinstance(artifact, DeliverableArtifact)
                and artifact.kind == "blindspot_intake_handoff"
                and session.artifact_id in artifact.parent_ids
                and artifact.metadata.get("content_sha256") == content_hash
            ):
                return artifact
        return None

    @staticmethod
    def _handoff_content(session: IntakeSessionArtifact) -> str:
        lines = [
            "---",
            "bsc_managed: true",
            "kind: dbos_intake_handoff",
            f"intake_session_id: {session.artifact_id}",
            f"mission_id: {session.linked_mission_id}",
            "---",
            "",
            "# Approved DBOS Intake Handoff",
            "",
            "## Request",
            session.original_request,
            "",
            "## Declared Context",
        ]
        for field, value in sorted(session.declared_context.items()):
            lines.append(f"- {field}: {value}")
        lines.extend(["", "## Explicit Gaps"])
        if session.unresolved_fields:
            lines.extend(f"- {field}" for field in session.unresolved_fields)
        else:
            lines.append("- None declared")
        lines.extend(["", "## Evidence-backed Recommendations"])
        for recommendation in session.recommendations:
            if recommendation.get("state") == "unavailable":
                lines.append(f"- Unavailable: {recommendation.get('reason', '')}")
            else:
                lines.append(
                    f"- [{recommendation.get('source_id', '')}] {recommendation.get('summary', '')} "
                    f"({recommendation.get('source_url', '')}; captured {recommendation.get('captured_at', '')})"
                )
        lines.extend(["", "This handoff is an approved output, not source evidence and must not be re-ingested as a source.", ""])
        return "\n".join(lines)
