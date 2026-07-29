"""Governed information-discovery ingress service.

n8n is intentionally treated as an untrusted producer. This service turns a
signed project-scoped batch into durable BSC receipts and reviewable source
records. It never promotes a discovery score or an LLM derivative to evidence.
"""

from __future__ import annotations

import hashlib
from typing import Any
from pathlib import Path

from app.knowledge.information_intelligence_contracts import (
    AVAILABLE_CONNECTORS,
    SignalBatch,
    SignalItem,
    SourceRegistryEntry,
    connector_availability,
)
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService, canonicalize_origin, sha256_content
from app.knowledge.obsidian_source_projection import ObsidianSourceProjection
from app.knowledge.proposal_gate import ProposalGateError
from app.core.config import settings


class InformationIntelligenceError(ValueError):
    """Raised for a governed intake contract violation."""


class InformationIntelligenceService:
    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository
        self.capture = SourceCaptureService(repository)

    def register_source(self, entry: SourceRegistryEntry | dict[str, Any]) -> dict[str, Any]:
        model = entry if isinstance(entry, SourceRegistryEntry) else SourceRegistryEntry.model_validate(entry)
        availability, reason = connector_availability(model.connector_type)
        return self.repository.upsert_information_source_registry(
            model,
            availability=availability,
            unavailable_reason=reason,
        )

    def list_sources(self, project_id: str) -> list[dict[str, Any]]:
        return self.repository.list_information_source_registry(project_id)

    def n8n_source_manifest(self, project_id: str, connector_type: str = "") -> dict[str, Any]:
        """Return the minimum scoped source configuration a producer needs.

        This is intentionally narrower than the operator overview: a
        ``project_ingress`` credential can discover only its own enabled,
        first-release feed configuration. It cannot inspect receipts, evidence,
        other projects, derivatives, or unsupported connector configuration.
        """
        connector = connector_type.strip().lower()
        if connector and connector not in AVAILABLE_CONNECTORS:
            raise InformationIntelligenceError("connector is unavailable for the governed n8n manifest")

        sources = []
        for source in self.list_sources(project_id):
            if not source.get("enabled") or source.get("availability") != "available":
                continue
            source_connector = str(source.get("connector_type") or "").strip().lower()
            if source_connector not in AVAILABLE_CONNECTORS:
                continue
            if connector and source_connector != connector:
                continue
            sources.append(
                {
                    "id": str(source["id"]),
                    "name": str(source["name"]),
                    "connector_type": source_connector,
                    "feed_url": str(source["feed_url"]),
                    "channel_id": str(source.get("channel_id") or ""),
                    "topics": list(source.get("topics") or []),
                    "languages": list(source.get("languages") or []),
                    "freshness_hours": int(source["freshness_hours"]),
                    "retention_days": int(source["retention_days"]),
                    "authority_tier": str(source["authority_tier"]),
                }
            )
        return {
            "project_id": project_id,
            "connector_type": connector or "all_first_release",
            "state": "ready" if sources else "no_available_sources",
            "sources": sources,
        }

    def ingest(self, batch: SignalBatch) -> dict[str, Any]:
        payload_hash = batch.payload_hash()
        existing = self.repository.get_signal_batch(batch.project_id, batch.batch_id)
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise InformationIntelligenceError("batch_id was replayed with a different payload")
            return self._batch_response(existing, replayed=True)

        existing_execution = self.repository.get_signal_batch_by_execution(batch.project_id, batch.execution_id)
        if existing_execution:
            if existing_execution["payload_hash"] != payload_hash:
                raise InformationIntelligenceError("execution_id was replayed with a different payload")
            return self._batch_response(existing_execution, replayed=True)

        # Registry ownership and connector compatibility are authorization
        # boundaries, not recoverable item-level errors. Reject the full batch
        # before creating a run or receipt when a producer crosses projects.
        self._validate_batch_registries(batch)

        run = KnowledgeRun(
            project_id=batch.project_id,
            run_type="information_signal_ingress",
            trigger="n8n",
            status=RunStatus.QUEUED,
            input_refs={
                "schema_version": batch.schema_version,
                "batch_id": batch.batch_id,
                "execution_id": batch.execution_id,
                "connector_type": batch.connector_type,
                "workflow_id": batch.workflow_id,
                "payload_hash": payload_hash,
                "item_count": len(batch.items),
            },
        )
        self.repository.create_run(run)
        self.repository.claim_run_execution(project_id=batch.project_id, run_id=run.id)
        created = self.repository.create_signal_batch(
            project_id=batch.project_id,
            batch_id=batch.batch_id,
            execution_id=batch.execution_id,
            schema_version=batch.schema_version,
            connector_type=batch.connector_type,
            workflow_id=batch.workflow_id,
            collected_at=batch.collected_at,
            payload_hash=payload_hash,
            run_id=run.id,
        )

        failures = 0
        for item in batch.items:
            try:
                self._ingest_item(batch, created, item)
            except Exception as exc:  # Keep one malformed entry from hiding valid evidence.
                failures += 1
                self.repository.create_signal_receipt(
                    project_id=batch.project_id,
                    batch_id=batch.batch_id,
                    item_key=self._item_key(item),
                    registry_id=item.registry_id,
                    external_id=item.external_id,
                    canonical_url=canonicalize_origin(item.url),
                    source_id="",
                    disposition="rejected",
                    reason=self._bounded_error(exc),
                    metadata={"lead_only": item.lead_only},
                )

        status = "partial" if failures else "completed"
        receipts = self.repository.list_signal_receipts(batch.project_id, batch.batch_id)
        output_refs = {
            "signal_batch_id": created["id"],
            "batch_id": batch.batch_id,
            "receipt_count": len(receipts),
            "failure_count": failures,
        }
        self.repository.update_signal_batch_status(batch.project_id, batch.batch_id, status, output_refs=output_refs)
        self.repository.update_run_status(
            batch.project_id,
            run.id,
            RunStatus.COMPLETED if not failures else RunStatus.FAILED,
            error="" if not failures else f"{failures} signal item(s) rejected",
            output_refs=output_refs,
        )
        return self._batch_response(self.repository.get_signal_batch(batch.project_id, batch.batch_id) or created, replayed=False)

    def list_receipts(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.repository.list_signal_receipts(project_id, limit=limit)

    def list_derivatives(self, project_id: str, source_id: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
        return self.repository.list_signal_derivatives(project_id, source_id=source_id, limit=limit)

    def overview(self, project_id: str) -> dict[str, Any]:
        sources = self.list_sources(project_id)
        receipts = self.list_receipts(project_id, limit=500)
        runs = [run for run in self.repository.list_runs(project_id, limit=100) if run["run_type"] == "information_signal_ingress"]
        return {
            "state": "ready" if sources else "no_sources",
            "source_registry": sources,
            "receipts": receipts,
            "runs": runs,
            "counts": {
                "sources": len(sources),
                "available_sources": sum(1 for source in sources if source["availability"] == "available" and source["enabled"]),
                "unavailable_sources": sum(1 for source in sources if source["availability"] == "unavailable"),
                "captured": sum(1 for receipt in receipts if receipt["disposition"] == "captured"),
                "lead_only": sum(1 for receipt in receipts if receipt["disposition"] == "lead_only"),
                "rejected": sum(1 for receipt in receipts if receipt["disposition"] == "rejected"),
            },
        }

    def _ingest_item(self, batch: SignalBatch, created_batch: dict[str, Any], item: SignalItem) -> dict[str, Any]:
        registry = self.repository.get_information_source_registry(batch.project_id, item.registry_id)
        if not registry:
            raise PermissionError("source registry is missing or belongs to another project")
        if not registry["enabled"]:
            raise InformationIntelligenceError("source registry is disabled")
        if registry["connector_type"] != batch.connector_type:
            raise InformationIntelligenceError("batch connector does not match source registry")
        if registry["availability"] != "available":
            raise InformationIntelligenceError(registry["unavailable_reason"] or "connector unavailable")

        canonical_url = canonicalize_origin(item.url)
        item_key = self._item_key(item, canonical_url=canonical_url)
        existing = self.repository.get_signal_receipt(batch.project_id, batch.batch_id, item_key)
        if existing:
            return existing

        metadata = {
            "intelligence": {
                "registry_id": registry["id"],
                "registry_name": registry["name"],
                "connector_type": batch.connector_type,
                "batch_id": batch.batch_id,
                "execution_id": batch.execution_id,
                "workflow_id": batch.workflow_id,
                "evidence_state": "lead_only" if item.lead_only else "captured",
                "raw_evidence_captured": not item.lead_only,
                "published_at": item.published_at,
                "language": item.language,
                "discovery_metrics": dict(item.discovery_metrics),
                "authority_tier_claim": registry["authority_tier"],
            },
            **dict(item.metadata),
        }
        if item.lead_only:
            raw_content = f"# {item.title}\n\nDiscovered URL: {canonical_url}\n\nNo original body was captured; this record is a discovery lead only."
            source_type = "intelligence_lead"
        else:
            raw_content = item.raw_content
            source_type = batch.connector_type

        capture_result = self.capture.capture(
            CapturedSourceInput(
                project_id=batch.project_id,
                source_type=source_type,
                origin=canonical_url,
                raw_content=raw_content,
                trust_level="untrusted",
                metadata={**metadata, "admission_gate": "project_triage"},
                capture_run_id=created_batch["run_id"],
            )
        )
        captured = capture_result.source
        mirror = self._sync_obsidian_projection(batch.project_id, captured["id"])
        if mirror["status"] != "unavailable":
            captured_metadata = dict(captured.get("metadata") or {})
            intelligence_metadata = dict(captured_metadata.get("intelligence") or {})
            intelligence_metadata["obsidian_projection"] = mirror
            captured = self.repository.update_source_metadata(
                batch.project_id,
                captured["id"],
                {**captured_metadata, "intelligence": intelligence_metadata},
            )
        for derivative in item.derivatives:
            self.repository.create_signal_derivative(
                project_id=batch.project_id,
                source_id=captured["id"],
                kind=derivative.kind,
                provider=derivative.provider,
                model=derivative.model,
                revision=derivative.revision,
                input_hash=sha256_content(raw_content),
                content=derivative.content,
                metadata=dict(derivative.metadata),
            )

        return self.repository.create_signal_receipt(
            project_id=batch.project_id,
            batch_id=batch.batch_id,
            item_key=item_key,
            registry_id=registry["id"],
            external_id=item.external_id,
            canonical_url=canonical_url,
            source_id=captured["id"],
            disposition="lead_only" if item.lead_only else "captured",
            reason="duplicate_source" if not capture_result.created else "",
            metadata={
                "source_created": capture_result.created,
                "source_status": captured.get("status", ""),
                "derivative_count": len(item.derivatives),
                "raw_content_hash": sha256_content(raw_content) if not item.lead_only else "",
            },
        )

    def _validate_batch_registries(self, batch: SignalBatch) -> None:
        for item in batch.items:
            registry = self.repository.get_information_source_registry(batch.project_id, item.registry_id)
            if not registry:
                raise PermissionError("source registry is missing or belongs to another project")
            if not registry["enabled"]:
                raise InformationIntelligenceError("source registry is disabled")
            if registry["connector_type"] != batch.connector_type:
                raise InformationIntelligenceError("batch connector does not match source registry")
            if registry["availability"] != "available":
                raise InformationIntelligenceError(registry["unavailable_reason"] or "connector unavailable")

    def _sync_obsidian_projection(self, project_id: str, source_id: str) -> dict[str, Any]:
        """Mirror a BSC record only when the managed Vault boundary exists."""
        if not settings.OBSIDIAN_VAULT_ROOT or not self.repository.get_vault(project_id):
            return {"status": "unavailable", "reason": "vault_not_configured"}
        try:
            report = ObsidianSourceProjection(
                self.repository, Path(settings.OBSIDIAN_VAULT_ROOT)
            ).sync(project_id=project_id, source_ids=[source_id])
            return {"status": "completed", **report}
        except (OSError, ValueError, ProposalGateError):
            return {"status": "failed", "reason": "vault_projection_failed"}

    def _batch_response(self, batch: dict[str, Any], *, replayed: bool) -> dict[str, Any]:
        receipts = self.repository.list_signal_receipts(batch["project_id"], batch["batch_id"])
        return {
            "batch_id": batch["batch_id"],
            "execution_id": batch["execution_id"],
            "run_id": batch["run_id"],
            "status": batch["status"],
            "receipt_count": len(receipts),
            "receipts": receipts,
            "replayed": replayed,
        }

    @staticmethod
    def _item_key(item: SignalItem, *, canonical_url: str = "") -> str:
        url = canonical_url or canonicalize_origin(item.url)
        digest = item.raw_content_hash or (sha256_content(item.raw_content) if item.raw_content else "lead")
        return hashlib.sha256(f"{item.registry_id}|{item.external_id}|{url}|{digest}|{item.lead_only}".encode("utf-8")).hexdigest()

    @staticmethod
    def _bounded_error(exc: Exception) -> str:
        return str(exc).replace("\n", " ")[:512] or exc.__class__.__name__
