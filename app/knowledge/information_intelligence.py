"""Governed information-discovery ingress service.

n8n is intentionally treated as an untrusted producer. This service turns a
signed project-scoped batch into durable BSC receipts and reviewable source
records. It never promotes a discovery score or an LLM derivative to evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo

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


_SHANGHAI = ZoneInfo("Asia/Shanghai")


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

    def daily_brief(self, project_id: str, *, day: str = "") -> dict[str, Any]:
        """Build a redacted brief from completed BSC batches only.

        The brief is a deterministic read projection. It deliberately does not
        persist a second copy of source text or model output: the BSC receipt
        and source IDs are the lineage, while the revision hash makes a brief
        change observable to downstream delivery and distillation jobs.
        """
        window = self._brief_window(day)
        batches = [
            batch for batch in self.repository.list_signal_batches(project_id, limit=1_000)
            # Producer collection time is the information-day authority. Older
            # rows without it retain the legacy persisted-time fallback.
            if self._timestamp_in_window(
                str(batch.get("collected_at") or batch.get("created_at") or ""),
                window["start_at"],
                window["end_at"],
            )
        ]
        runs = {
            run["id"]: run
            for run in self.repository.list_runs(project_id, limit=1_000)
            if run.get("run_type") == "information_signal_ingress"
        }
        completed_batches = [batch for batch in batches if batch.get("status") == "completed"]
        incomplete_batches = [batch for batch in batches if batch.get("status") != "completed"]
        receipts = [
            receipt
            for batch in completed_batches
            for receipt in self.repository.list_signal_receipts(project_id, batch_id=batch["batch_id"], limit=500)
        ]

        def item(receipt: dict[str, Any]) -> dict[str, Any]:
            metadata = receipt.get("metadata") if isinstance(receipt.get("metadata"), dict) else {}
            return {
                "receipt_id": str(receipt.get("id") or ""),
                "batch_id": str(receipt.get("batch_id") or ""),
                "registry_id": str(receipt.get("registry_id") or ""),
                "source_id": str(receipt.get("source_id") or ""),
                "disposition": str(receipt.get("disposition") or ""),
                "reason": str(receipt.get("reason") or ""),
                "canonical_url": str(receipt.get("canonical_url") or ""),
                "title": str(metadata.get("title") or ""),
                "published_at": str(metadata.get("published_at") or ""),
                "source_created": metadata.get("source_created"),
                "created_at": str(receipt.get("created_at") or ""),
            }

        captured = [item(receipt) for receipt in receipts if receipt.get("disposition") == "captured" and receipt.get("reason") != "duplicate_source"]
        duplicates = [item(receipt) for receipt in receipts if receipt.get("disposition") == "captured" and receipt.get("reason") == "duplicate_source"]
        confirmation_required = [item(receipt) for receipt in receipts if receipt.get("disposition") == "lead_only"]
        rejected = [item(receipt) for receipt in receipts if receipt.get("disposition") == "rejected"]
        failure_items = [
            {
                "batch_id": str(batch.get("batch_id") or ""),
                "run_id": str(batch.get("run_id") or ""),
                "status": str(batch.get("status") or ""),
                "failure_count": int((batch.get("output_refs") or {}).get("failure_count") or 0),
                "reason": str((runs.get(batch.get("run_id")) or {}).get("error") or "batch_not_completed"),
            }
            for batch in incomplete_batches
        ]

        lineage = {
            "batch_ids": [str(batch.get("batch_id") or "") for batch in completed_batches],
            "run_ids": [str(batch.get("run_id") or "") for batch in completed_batches],
            "receipt_ids": [str(receipt.get("id") or "") for receipt in receipts],
            "source_ids": sorted({str(receipt.get("source_id") or "") for receipt in receipts if receipt.get("source_id")}),
        }
        revision_payload = {
            "project_id": project_id,
            "window": window,
            "lineage": lineage,
            "failure_items": failure_items,
        }
        revision = hashlib.sha256(
            json.dumps(revision_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        lineage["revision"] = revision
        state = "available" if receipts else "no_sample"
        coverage = "partial" if failure_items else ("complete" if receipts else "no_sample")
        sections = {
            "captured": {"count": len(captured), "items": captured},
            "repeat_discoveries": {"count": len(duplicates), "items": duplicates},
            "confirmation_required": {"count": len(confirmation_required), "items": confirmation_required},
            "rejected": {"count": len(rejected), "items": rejected},
            "failures": {"count": len(failure_items), "items": failure_items},
        }
        return {
            "project_id": project_id,
            "state": state,
            "coverage": coverage,
            "window": window,
            "denominator": len(receipts),
            "summary": {name: section["count"] for name, section in sections.items()},
            "sections": sections,
            "confirmation_queue": [
                {**entry, "next_action": "capture_original_source"}
                for entry in confirmation_required
            ],
            "lineage": lineage,
            "delivery": {
                "provider": "feishu",
                "state": "unavailable",
                "reason": "delivery_not_configured",
                "attempts": [],
            },
        }

    def overview(self, project_id: str) -> dict[str, Any]:
        sources = self.list_sources(project_id)
        receipts = self.list_receipts(project_id, limit=500)
        runs = [run for run in self.repository.list_runs(project_id, limit=100) if run["run_type"] == "information_signal_ingress"]
        captured_receipts = [receipt for receipt in receipts if receipt["disposition"] == "captured"]
        duplicate_sources = sum(
            1
            for receipt in captured_receipts
            if receipt["reason"] == "duplicate_source"
            or (isinstance(receipt.get("metadata"), dict) and receipt["metadata"].get("source_created") is False)
        )
        return {
            "state": "ready" if sources else "no_sources",
            "source_registry": sources,
            "receipts": receipts,
            "runs": runs,
            "daily_brief": self.daily_brief(project_id),
            "horizon_review_queue": self.horizon_review_queue(project_id),
            "confirmation_queue": [
                receipt for receipt in receipts if receipt.get("disposition") == "lead_only"
            ],
            "counts": {
                "sources": len(sources),
                "available_sources": sum(1 for source in sources if source["availability"] == "available" and source["enabled"]),
                "unavailable_sources": sum(1 for source in sources if source["availability"] == "unavailable"),
                "captured": len(captured_receipts),
                "new_sources": len(captured_receipts) - duplicate_sources,
                "duplicate_sources": duplicate_sources,
                "lead_only": sum(1 for receipt in receipts if receipt["disposition"] == "lead_only"),
                "rejected": sum(1 for receipt in receipts if receipt["disposition"] == "rejected"),
            },
        }

    def horizon_review_queue(self, project_id: str, *, limit: int = 100) -> dict[str, Any]:
        """Expose unresolved Horizon metadata without reading immutable bodies.

        A linked primary capture is not a published Wiki claim, so the signal
        remains visible until review. Its next action changes, however, so an
        operator does not repeatedly fetch the same external page.
        """
        bounded_limit = max(1, min(int(limit), 100))
        citations = self.repository.list_evidence_citation_metadata(project_id)
        cited_source_ids = {
            str(item.get("source_id") or "")
            for item in citations
            if str(item.get("status") or "active") == "active"
        }
        source_metadata = self.repository.list_evidence_source_metadata(project_id)
        primary_captures: dict[str, dict[str, str]] = {}
        for candidate in source_metadata:
            metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
            if metadata.get("evidence_role") != "primary_capture":
                continue
            supported = metadata.get("supports_horizon_signal_ids")
            supported_ids = (
                [str(value).strip() for value in supported if str(value).strip()]
                if isinstance(supported, list)
                else []
            )
            legacy_signal_id = str(metadata.get("discovered_from_source_id") or "").strip()
            if legacy_signal_id and legacy_signal_id not in supported_ids:
                supported_ids.append(legacy_signal_id)
            for signal_id in supported_ids:
                existing = primary_captures.get(signal_id)
                candidate_capture = {
                    "source_id": str(candidate.get("id") or ""),
                    "status": str(candidate.get("status") or ""),
                    "origin": str(candidate.get("origin") or "")[:500],
                    "trust_level": str(candidate.get("trust_level") or ""),
                    "captured_at": str(candidate.get("captured_at") or candidate.get("updated_at") or ""),
                }
                if candidate_capture["source_id"] and (
                    existing is None or candidate_capture["captured_at"] > existing["captured_at"]
                ):
                    primary_captures[signal_id] = candidate_capture

        candidates: list[dict[str, Any]] = []
        for source in source_metadata:
            source_id = str(source.get("id") or "")
            if (
                str(source.get("source_type") or "") != "horizon_signal"
                or str(source.get("status") or "") != "eligible"
                or not source_id
                or source_id in cited_source_ids
            ):
                continue
            metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
            intelligence = metadata.get("intelligence") if isinstance(metadata.get("intelligence"), dict) else {}
            title = str(metadata.get("title") or intelligence.get("title") or source.get("origin") or source_id).strip()[:240]
            score_value = metadata.get("ai_score", intelligence.get("ai_score"))
            try:
                ai_score = float(score_value) if score_value is not None else None
            except (TypeError, ValueError):
                ai_score = None
            task_values = metadata.get("task_families") or intelligence.get("task_families") or metadata.get("ai_tags") or []
            task_families = [str(value).strip()[:80] for value in task_values if str(value).strip()][:8] if isinstance(task_values, list) else []
            primary_capture = primary_captures.get(source_id)
            item = {
                "source_id": source_id,
                "title": title,
                "origin": str(source.get("origin") or "")[:500],
                "status": str(source.get("status") or ""),
                "trust_level": str(source.get("trust_level") or ""),
                "ai_score": ai_score,
                "task_families": task_families,
                "next_action": "review_primary_capture" if primary_capture else "capture_primary_source",
            }
            if primary_capture:
                item["primary_capture"] = {
                    key: value for key, value in primary_capture.items() if key != "captured_at"
                }
            candidates.append(item)
        candidates.sort(
            key=lambda item: (
                -(item["ai_score"] if item["ai_score"] is not None else -1.0),
                item["title"].casefold(),
                item["source_id"],
            )
        )
        items = candidates[:bounded_limit]
        return {
            "project_id": project_id,
            "state": "available" if items else "no_sample",
            "count": len(items),
            "items": items,
        }

    @staticmethod
    def _brief_window(day: str) -> dict[str, str]:
        if day:
            try:
                local_start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=_SHANGHAI)
            except ValueError as exc:
                raise InformationIntelligenceError("day must use YYYY-MM-DD") from exc
        else:
            local_start = datetime.now(_SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_start + timedelta(days=1)
        return {
            "date": local_start.date().isoformat(),
            "timezone": "Asia/Shanghai",
            "start_at": local_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end_at": local_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _timestamp_in_window(value: str, start_at: str, end_at: str) -> bool:
        if not value:
            return False
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                # Legacy repository rows use the host-local wall-clock format.
                # Treat an offset-free information-ingress timestamp as the
                # product timezone instead of silently shifting it by 8 hours.
                timestamp = timestamp.replace(tzinfo=_SHANGHAI)
            start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
            return start <= timestamp.astimezone(timezone.utc) < end
        except ValueError:
            return False

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
                "title": item.title,
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
