"""Persistence facade for the project-scoped LLM Wiki domain."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_contracts import (
    ExtractionArtifact,
    KnowledgeGraphEdge,
    KnowledgeRun,
    MediaAsset,
    ProposalStatus,
    ReferenceLink,
    RunStatus,
    SourceCaptureAttempt,
    SourceRecord,
    SourceStatus,
    TableArtifact,
    WikiProposal,
)
from app.knowledge.information_intelligence_contracts import SourceRegistryEntry
from app.knowledge.ecosystem_release_gate import ReleaseEvidence
from app.repositories.base_repository import BaseRepository


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _run_event_advisory_lock_key(project_id: str, run_id: str) -> int:
    """Return a stable PostgreSQL transaction lock key for one run ledger."""
    digest = hashlib.sha256(f"knowledge-run-event|{project_id}|{run_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _horizon_import_claim_id(
    project_id: str,
    horizon_run_id: str,
    horizon_stage: str,
    horizon_item_id: str,
) -> str:
    """Produce the stable primary key for one external Horizon signal import."""
    payload = "|".join((project_id, horizon_run_id, horizon_stage, horizon_item_id))
    return hashlib.sha256(f"horizon-import-claim|{payload}".encode("utf-8")).hexdigest()[:24]


class PublicationConflictError(ValueError):
    """Raised when the persisted Wiki changed after a proposal snapshot was built."""


class WikiRepository(BaseRepository):
    """Repository that keeps every query explicitly project scoped."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        ensure_schema(self)

    def _decode(self, row: Any, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
        if not row:
            return None
        value = self._row_to_dict(row)
        for field in json_fields:
            value[field.removesuffix("_json")] = self._json_loads(value.pop(field, "{}"))
        return value

    def list_workspace_projects_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        """Return the bounded project picker projection for one tenant."""
        tenant = str(tenant_id or "").strip()
        if not tenant:
            return []
        rows = self._execute(
            "SELECT id,name,created_at FROM knowledge_projects "
            "WHERE tenant_id=? ORDER BY created_at DESC,id DESC",
            (tenant,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_workspace_project_for_tenant(self, project_id: str, tenant_id: str) -> dict[str, Any] | None:
        tenant = str(tenant_id or "").strip()
        if not tenant:
            return None
        row = self._execute(
            "SELECT id,name,created_at FROM knowledge_projects WHERE id=? AND tenant_id=?",
            (project_id, tenant),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def configure_vault(self, project_id: str, vault_path: str, actor_id: str = "", metadata: dict | None = None) -> dict:
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_vaults (project_id,vault_path,status,configured_by,metadata_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
            "vault_path=excluded.vault_path,status=excluded.status,configured_by=excluded.configured_by,"
            "metadata_json=excluded.metadata_json,updated_at=excluded.updated_at",
            (project_id, vault_path, "configured", actor_id, self._json_dumps(metadata or {}), now, now),
        )
        self._commit()
        return self.get_vault(project_id) or {}

    def get_vault(self, project_id: str) -> dict | None:
        row = self._execute("SELECT * FROM knowledge_vaults WHERE project_id=?", (project_id,)).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_vaults(self) -> list[dict]:
        rows = self._execute("SELECT * FROM knowledge_vaults ORDER BY project_id").fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def append_release_evidence(
        self,
        project_id: str,
        evidence: ReleaseEvidence,
        *,
        recorded_by: str,
    ) -> dict[str, Any]:
        """Append one metadata-only release-evidence revision for a project."""
        existing = self.get_latest_release_evidence(project_id, evidence.evidence_id)
        revision = int((existing or {}).get("revision") or 0) + 1
        now = self._now()
        record_id = hashlib.sha256(
            f"release-evidence|{project_id}|{evidence.evidence_id}|{revision}|{now}".encode("utf-8")
        ).hexdigest()[:24]
        self._execute(
            "INSERT INTO knowledge_release_evidence "
            "(id,project_id,evidence_id,revision,state,proof_class,observed_at,durable_ids_json,detail_code,recorded_by,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                record_id,
                project_id,
                evidence.evidence_id,
                revision,
                evidence.state,
                evidence.proof_class,
                evidence.observed_at,
                self._json_dumps(list(evidence.durable_ids)),
                evidence.detail_code,
                recorded_by,
                now,
            ),
        )
        self._commit()
        return self.get_latest_release_evidence(project_id, evidence.evidence_id) or {}

    def get_latest_release_evidence(self, project_id: str, evidence_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_release_evidence WHERE project_id=? AND evidence_id=? "
            "ORDER BY revision DESC LIMIT 1",
            (project_id, evidence_id),
        ).fetchone()
        return self._decode(row, ("durable_ids_json",))

    def list_current_release_evidence(self, project_id: str) -> list[dict[str, Any]]:
        """Return only the latest revision for each release-evidence category."""
        rows = self._execute(
            "SELECT current.* FROM knowledge_release_evidence AS current "
            "JOIN (SELECT evidence_id,MAX(revision) AS revision FROM knowledge_release_evidence "
            "WHERE project_id=? GROUP BY evidence_id) AS latest "
            "ON current.evidence_id=latest.evidence_id AND current.revision=latest.revision "
            "WHERE current.project_id=? ORDER BY current.evidence_id ASC",
            (project_id, project_id),
        ).fetchall()
        return [self._decode(row, ("durable_ids_json",)) or {} for row in rows]

    def create_source(self, source: SourceRecord) -> dict:
        self._execute(
            "INSERT INTO knowledge_sources "
            "(id,project_id,source_type,origin,vault_path,content_hash,raw_content,trust_level,status,metadata_json,supersedes_id,captured_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                source.id, source.project_id, source.source_type, source.origin, source.vault_path,
                source.content_hash, source.raw_content, source.trust_level, source.status.value,
                self._json_dumps(source.metadata), source.supersedes_id,
                _iso(source.captured_at), _iso(source.updated_at),
            ),
        )
        self._commit()
        return self.get_source(source.project_id, source.id) or {}

    def get_source(self, project_id: str, source_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_sources WHERE project_id=? AND id=?", (project_id, source_id)
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def update_source_metadata(self, project_id: str, source_id: str, metadata: dict[str, Any]) -> dict:
        self._execute(
            "UPDATE knowledge_sources SET metadata_json=?,updated_at=? WHERE project_id=? AND id=?",
            (self._json_dumps(metadata), self._now(), project_id, source_id),
        )
        self._commit()
        return self.get_source(project_id, source_id) or {}

    def reclassify_legacy_manual_vault_source(
        self,
        project_id: str,
        source_id: str,
        *,
        metadata: dict[str, Any],
    ) -> dict:
        """Repair one legacy raw-Vault classification without changing its body.

        Older syncs labelled direct files in a project's ``01_Sources`` lane as
        permanently unsupported before a local extractor had a chance to run.
        This narrow correction keeps the original hash/body and only permits the
        known legacy rejected classification to become a user-curated intake.
        """
        self._execute(
            "UPDATE knowledge_sources SET source_type=?,trust_level=?,status=?,metadata_json=?,updated_at=? "
            "WHERE project_id=? AND id=? AND source_type=? AND status=?",
            (
                "manual_upload",
                "trusted",
                SourceStatus.ELIGIBLE.value,
                self._json_dumps(metadata),
                self._now(),
                project_id,
                source_id,
                "obsidian_unsupported",
                SourceStatus.REJECTED.value,
            ),
        )
        self._commit()
        return self.get_source(project_id, source_id) or {}

    def find_source_by_content_hash(self, project_id: str, content_hash: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_sources WHERE project_id=? AND content_hash=? ORDER BY captured_at DESC, id DESC LIMIT 1",
            (project_id, content_hash),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def get_horizon_import_claim(
        self,
        *,
        project_id: str,
        horizon_run_id: str,
        horizon_stage: str,
        horizon_item_id: str,
    ) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_horizon_import_claims "
            "WHERE project_id=? AND horizon_run_id=? AND horizon_stage=? AND horizon_item_id=?",
            (project_id, horizon_run_id, horizon_stage, horizon_item_id),
        ).fetchone()
        return self._decode(row)

    def claim_horizon_import(
        self,
        *,
        project_id: str,
        horizon_run_id: str,
        horizon_stage: str,
        horizon_item_id: str,
        content_hash: str,
        capture_run_id: str = "",
        lease_seconds: int = 900,
    ) -> dict[str, Any]:
        """Atomically claim one external signal before creating immutable evidence.

        A Horizon worker may be retried while another worker is still handling the
        same staged artifact. The database unique key is the authority here; a
        process-local check would allow both workers to create evidence. Claims
        are leased so a process crash cannot permanently block a later retry.
        """
        now_at = datetime.now(timezone.utc)
        now = _iso(now_at)
        expires_at = _iso(now_at + timedelta(seconds=max(1, int(lease_seconds))))
        claim_id = _horizon_import_claim_id(project_id, horizon_run_id, horizon_stage, horizon_item_id)
        cursor = self._execute(
            "INSERT INTO knowledge_horizon_import_claims "
            "(id,project_id,horizon_run_id,horizon_stage,horizon_item_id,content_hash,capture_run_id,status,source_id,lease_expires_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(project_id,horizon_run_id,horizon_stage,horizon_item_id) DO NOTHING",
            (
                claim_id,
                project_id,
                horizon_run_id,
                horizon_stage,
                horizon_item_id,
                content_hash,
                capture_run_id,
                "claimed",
                "",
                expires_at,
                now,
                now,
            ),
        )
        inserted = bool(getattr(cursor, "rowcount", 0))
        self._commit()
        if inserted:
            claim = self.get_horizon_import_claim(
                project_id=project_id,
                horizon_run_id=horizon_run_id,
                horizon_stage=horizon_stage,
                horizon_item_id=horizon_item_id,
            ) or {}
            return {"claimed": True, "recovered": False, "claim": claim}

        existing = self.get_horizon_import_claim(
            project_id=project_id,
            horizon_run_id=horizon_run_id,
            horizon_stage=horizon_stage,
            horizon_item_id=horizon_item_id,
        )
        if not existing:
            raise RuntimeError("Horizon import claim disappeared before it could be read")
        if existing["status"] == "completed":
            return {"claimed": False, "recovered": False, "claim": existing}

        reclaim = self._execute(
            "UPDATE knowledge_horizon_import_claims "
            "SET content_hash=?,capture_run_id=?,status='claimed',source_id='',lease_expires_at=?,updated_at=? "
            "WHERE project_id=? AND horizon_run_id=? AND horizon_stage=? AND horizon_item_id=? "
            "AND status='claimed' AND lease_expires_at<=?",
            (
                content_hash,
                capture_run_id,
                expires_at,
                now,
                project_id,
                horizon_run_id,
                horizon_stage,
                horizon_item_id,
                now,
            ),
        )
        reclaimed = bool(getattr(reclaim, "rowcount", 0))
        self._commit()
        if reclaimed:
            claim = self.get_horizon_import_claim(
                project_id=project_id,
                horizon_run_id=horizon_run_id,
                horizon_stage=horizon_stage,
                horizon_item_id=horizon_item_id,
            ) or {}
            return {"claimed": True, "recovered": True, "claim": claim}
        return {"claimed": False, "recovered": False, "claim": existing}

    def complete_horizon_import_claim(
        self,
        *,
        project_id: str,
        horizon_run_id: str,
        horizon_stage: str,
        horizon_item_id: str,
        capture_run_id: str,
        source_id: str,
    ) -> bool:
        """Bind a completed claim to the actual immutable source it produced."""
        cursor = self._execute(
            "UPDATE knowledge_horizon_import_claims "
            "SET status='completed',source_id=?,lease_expires_at='',updated_at=? "
            "WHERE project_id=? AND horizon_run_id=? AND horizon_stage=? AND horizon_item_id=? "
            "AND capture_run_id=? AND status='claimed'",
            (
                source_id,
                self._now(),
                project_id,
                horizon_run_id,
                horizon_stage,
                horizon_item_id,
                capture_run_id,
            ),
        )
        self._commit()
        return bool(getattr(cursor, "rowcount", 0))

    def release_horizon_import_claim(
        self,
        *,
        project_id: str,
        horizon_run_id: str,
        horizon_stage: str,
        horizon_item_id: str,
        capture_run_id: str,
    ) -> bool:
        """Release an uncompleted claim after a capture failure so retries can run."""
        cursor = self._execute(
            "DELETE FROM knowledge_horizon_import_claims "
            "WHERE project_id=? AND horizon_run_id=? AND horizon_stage=? AND horizon_item_id=? "
            "AND capture_run_id=? AND status='claimed'",
            (project_id, horizon_run_id, horizon_stage, horizon_item_id, capture_run_id),
        )
        self._commit()
        return bool(getattr(cursor, "rowcount", 0))

    def find_latest_source_by_origin(self, project_id: str, source_type: str, origin: str) -> dict | None:
        if not origin:
            return None
        row = self._execute(
            "SELECT * FROM knowledge_sources WHERE project_id=? AND source_type=? AND origin=? AND status<>? "
            "ORDER BY captured_at DESC,id DESC LIMIT 1",
            (project_id, source_type, origin, SourceStatus.SUPERSEDED.value),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_sources(self, project_id: str, status: str | None = None) -> list[dict]:
        if status:
            rows = self._execute(
                "SELECT * FROM knowledge_sources WHERE project_id=? AND status=? ORDER BY captured_at DESC, id DESC",
                (project_id, status),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_sources WHERE project_id=? ORDER BY captured_at DESC, id DESC", (project_id,)
            ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def get_evidence_source_metadata(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        """Read one Evidence Atlas source projection without selecting its body."""
        row = self._execute(
            "SELECT id,project_id,source_type,origin,vault_path,content_hash,trust_level,status,metadata_json,"
            "supersedes_id,captured_at,updated_at FROM knowledge_sources WHERE project_id=? AND id=?",
            (project_id, source_id),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_evidence_source_metadata(self, project_id: str) -> list[dict[str, Any]]:
        """List Evidence Atlas source metadata without loading ``raw_content``."""
        rows = self._execute(
            "SELECT id,project_id,source_type,origin,vault_path,content_hash,trust_level,status,metadata_json,"
            "supersedes_id,captured_at,updated_at FROM knowledge_sources WHERE project_id=? "
            "ORDER BY captured_at DESC,id DESC",
            (project_id,),
        ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def get_source_reference_candidate(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        """Return only the immutable source identifiers needed for link projection."""
        row = self._execute(
            "SELECT id,project_id,origin,metadata_json FROM knowledge_sources WHERE project_id=? AND id=?",
            (project_id, source_id),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_source_reference_candidates(self, project_id: str, limit: int = 10_000) -> list[dict[str, Any]]:
        """List metadata-only reference candidates without selecting source bodies."""
        rows = self._execute(
            "SELECT id,project_id,origin,metadata_json FROM knowledge_sources WHERE project_id=? ORDER BY captured_at DESC,id DESC LIMIT ?",
            (project_id, max(1, min(int(limit), 10_000))),
        ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    # Information-intelligence tables are deliberately separate from the Wiki
    # lifecycle. The registry is discovery configuration; receipts are the
    # audit ledger that connects an untrusted producer to BSC evidence.
    def upsert_information_source_registry(
        self,
        entry: SourceRegistryEntry,
        *,
        availability: str,
        unavailable_reason: str,
    ) -> dict:
        existing = self._execute(
            "SELECT id FROM knowledge_information_source_registry WHERE project_id=? AND connector_type=? AND feed_url=?",
            (entry.project_id, entry.connector_type, entry.feed_url),
        ).fetchone()
        now = self._now()
        if existing:
            registry_id = self._row_to_dict(existing)["id"]
            self._execute(
                "UPDATE knowledge_information_source_registry SET name=?,channel_id=?,topics_json=?,languages_json=?,freshness_hours=?,retention_days=?,authority_tier=?,enabled=?,availability=?,unavailable_reason=?,metadata_json=?,updated_at=? WHERE project_id=? AND id=?",
                (
                    entry.name, entry.channel_id, self._json_dumps(entry.topics), self._json_dumps(entry.languages),
                    entry.freshness_hours, entry.retention_days, entry.authority_tier, int(entry.enabled), availability,
                    unavailable_reason, self._json_dumps(entry.metadata), now, entry.project_id, registry_id,
                ),
            )
        else:
            registry_id = entry.id
            self._execute(
                "INSERT INTO knowledge_information_source_registry (id,project_id,name,connector_type,feed_url,channel_id,topics_json,languages_json,freshness_hours,retention_days,authority_tier,enabled,availability,unavailable_reason,metadata_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    registry_id, entry.project_id, entry.name, entry.connector_type, entry.feed_url, entry.channel_id,
                    self._json_dumps(entry.topics), self._json_dumps(entry.languages), entry.freshness_hours,
                    entry.retention_days, entry.authority_tier, int(entry.enabled), availability, unavailable_reason,
                    self._json_dumps(entry.metadata), _iso(entry.created_at), now,
                ),
            )
        self._commit()
        return self.get_information_source_registry(entry.project_id, registry_id) or {}

    def get_information_source_registry(self, project_id: str, registry_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_information_source_registry WHERE project_id=? AND id=?",
            (project_id, registry_id),
        ).fetchone()
        return self._decode(row, ("topics_json", "languages_json", "metadata_json"))

    def list_information_source_registry(self, project_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_information_source_registry WHERE project_id=? ORDER BY enabled DESC,name ASC,id ASC",
            (project_id,),
        ).fetchall()
        return [self._decode(row, ("topics_json", "languages_json", "metadata_json")) or {} for row in rows]

    def create_signal_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        execution_id: str,
        schema_version: str,
        connector_type: str,
        workflow_id: str,
        collected_at: str,
        payload_hash: str,
        run_id: str,
    ) -> dict:
        record_id = self._generate_id()
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_signal_batches (id,project_id,batch_id,execution_id,schema_version,connector_type,workflow_id,collected_at,payload_hash,run_id,status,output_refs_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (record_id, project_id, batch_id, execution_id, schema_version, connector_type, workflow_id, collected_at,
             payload_hash, run_id, "processing", self._json_dumps({}), now, now),
        )
        self._commit()
        return self.get_signal_batch(project_id, batch_id) or {}

    def get_signal_batch(self, project_id: str, batch_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_signal_batches WHERE project_id=? AND batch_id=?", (project_id, batch_id)
        ).fetchone()
        return self._decode(row, ("output_refs_json",))

    def get_signal_batch_by_execution(self, project_id: str, execution_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_signal_batches WHERE project_id=? AND execution_id=?", (project_id, execution_id)
        ).fetchone()
        return self._decode(row, ("output_refs_json",))

    def list_signal_batches(self, project_id: str, *, limit: int = 500) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_signal_batches WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
            (project_id, max(1, min(int(limit), 1_000))),
        ).fetchall()
        return [self._decode(row, ("output_refs_json",)) or {} for row in rows]

    def update_signal_batch_status(
        self, project_id: str, batch_id: str, status: str, *, output_refs: dict[str, Any] | None = None
    ) -> dict:
        self._execute(
            "UPDATE knowledge_signal_batches SET status=?,output_refs_json=?,updated_at=? WHERE project_id=? AND batch_id=?",
            (status, self._json_dumps(output_refs or {}), self._now(), project_id, batch_id),
        )
        self._commit()
        return self.get_signal_batch(project_id, batch_id) or {}

    def create_signal_receipt(
        self,
        *,
        project_id: str,
        batch_id: str,
        item_key: str,
        registry_id: str,
        external_id: str,
        canonical_url: str,
        source_id: str,
        disposition: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> dict:
        existing = self.get_signal_receipt(project_id, batch_id, item_key)
        if existing:
            return existing
        receipt_id = self._generate_id()
        self._execute(
            "INSERT INTO knowledge_signal_receipts (id,project_id,batch_id,item_key,registry_id,external_id,canonical_url,source_id,disposition,reason,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (receipt_id, project_id, batch_id, item_key, registry_id, external_id, canonical_url, source_id,
             disposition, reason, self._json_dumps(metadata), self._now()),
        )
        self._commit()
        return self.get_signal_receipt(project_id, batch_id, item_key) or {}

    def get_signal_receipt(self, project_id: str, batch_id: str, item_key: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_signal_receipts WHERE project_id=? AND batch_id=? AND item_key=?",
            (project_id, batch_id, item_key),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_signal_receipts(self, project_id: str, batch_id: str = "", *, limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_signal_receipts WHERE project_id=?"
        if batch_id:
            query += " AND batch_id=?"
            params.append(batch_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def create_signal_derivative(
        self,
        *,
        project_id: str,
        source_id: str,
        kind: str,
        provider: str,
        model: str,
        revision: str,
        input_hash: str,
        content: str,
        metadata: dict[str, Any],
    ) -> dict:
        if not self.get_source(project_id, source_id):
            raise KeyError("signal derivative source is missing or belongs to another project")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self._execute(
            "SELECT id FROM knowledge_signal_derivatives WHERE project_id=? AND source_id=? AND kind=? AND provider=? AND model=? AND revision=? AND input_hash=? AND content_hash=?",
            (project_id, source_id, kind, provider, model, revision, input_hash, content_hash),
        ).fetchone()
        if existing:
            return self.get_signal_derivative(project_id, self._row_to_dict(existing)["id"]) or {}
        derivative_id = self._generate_id()
        self._execute(
            "INSERT INTO knowledge_signal_derivatives (id,project_id,source_id,kind,provider,model,revision,input_hash,content_hash,content,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (derivative_id, project_id, source_id, kind, provider, model, revision, input_hash, content_hash,
             content, self._json_dumps(metadata), self._now()),
        )
        self._commit()
        return self.get_signal_derivative(project_id, derivative_id) or {}

    def get_signal_derivative(self, project_id: str, derivative_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_signal_derivatives WHERE project_id=? AND id=?", (project_id, derivative_id)
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_signal_derivatives(self, project_id: str, source_id: str = "", *, limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_signal_derivatives WHERE project_id=?"
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def register_media_asset(self, asset: MediaAsset) -> dict:
        """Register immutable media metadata without copying its bytes."""
        if not self.get_source(asset.project_id, asset.source_id):
            raise KeyError("media asset source is missing or belongs to another project")
        existing = self._execute(
            "SELECT * FROM knowledge_media_assets WHERE project_id=? AND source_id=? AND byte_hash=? AND storage_ref=?",
            (asset.project_id, asset.source_id, asset.byte_hash, asset.storage_ref),
        ).fetchone()
        if existing:
            return self._decode(existing, ("metadata_json",)) or {}
        self._execute(
            "INSERT INTO knowledge_media_assets "
            "(id,project_id,source_id,mime_type,byte_hash,byte_size,storage_ref,rights,access_state,metadata_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset.id,
                asset.project_id,
                asset.source_id,
                asset.mime_type,
                asset.byte_hash,
                asset.byte_size,
                asset.storage_ref,
                asset.rights,
                asset.access_state.value,
                self._json_dumps(asset.metadata),
                _iso(asset.created_at),
                _iso(asset.updated_at),
            ),
        )
        self._commit()
        return self.get_media_asset(asset.project_id, asset.id) or {}

    def get_media_asset(self, project_id: str, asset_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_media_assets WHERE project_id=? AND id=?", (project_id, asset_id)
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_media_assets(self, project_id: str, source_id: str = "", limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_media_assets WHERE project_id=?"
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def create_extraction_artifact(self, artifact: ExtractionArtifact) -> dict:
        """Persist a versioned derivative; regular reads intentionally omit content."""
        if not self.get_source(artifact.project_id, artifact.source_id):
            raise KeyError("extraction source is missing or belongs to another project")
        asset = self.get_media_asset(artifact.project_id, artifact.asset_id)
        if not asset or asset["source_id"] != artifact.source_id:
            raise KeyError("extraction asset is missing or belongs to another source")
        existing = self._execute(
            "SELECT id FROM knowledge_extraction_artifacts WHERE project_id=? AND source_id=? AND asset_id=? "
            "AND extractor=? AND extractor_revision=? AND input_hash=?",
            (
                artifact.project_id,
                artifact.source_id,
                artifact.asset_id,
                artifact.extractor,
                artifact.extractor_revision,
                artifact.input_hash,
            ),
        ).fetchone()
        if existing:
            return self.get_extraction_artifact(artifact.project_id, self._row_to_dict(existing)["id"]) or {}
        self._execute(
            "INSERT INTO knowledge_extraction_artifacts "
            "(id,project_id,source_id,asset_id,extractor,extractor_revision,input_hash,content_hash,content,status,error,metadata_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                artifact.id,
                artifact.project_id,
                artifact.source_id,
                artifact.asset_id,
                artifact.extractor,
                artifact.extractor_revision,
                artifact.input_hash,
                artifact.content_hash,
                artifact.content,
                artifact.status.value,
                artifact.error,
                self._json_dumps(artifact.metadata),
                _iso(artifact.created_at),
            ),
        )
        self._commit()
        return self.get_extraction_artifact(artifact.project_id, artifact.id) or {}

    def get_extraction_artifact(self, project_id: str, extraction_id: str) -> dict | None:
        row = self._execute(
            "SELECT id,project_id,source_id,asset_id,extractor,extractor_revision,input_hash,content_hash,status,error,metadata_json,created_at "
            "FROM knowledge_extraction_artifacts WHERE project_id=? AND id=?",
            (project_id, extraction_id),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_extraction_artifacts(self, project_id: str, source_id: str = "", limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = (
            "SELECT id,project_id,source_id,asset_id,extractor,extractor_revision,input_hash,content_hash,status,error,metadata_json,created_at "
            "FROM knowledge_extraction_artifacts WHERE project_id=?"
        )
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def latest_extraction_for_asset(
        self,
        project_id: str,
        asset_id: str,
        *,
        extractor_revision: str = "",
    ) -> dict | None:
        """Return the newest bounded derivative for one project-owned asset."""
        params: list[Any] = [project_id, asset_id]
        query = (
            "SELECT id,project_id,source_id,asset_id,extractor,extractor_revision,input_hash,content_hash,status,error,metadata_json,created_at "
            "FROM knowledge_extraction_artifacts WHERE project_id=? AND asset_id=?"
        )
        if extractor_revision:
            query += " AND extractor_revision=?"
            params.append(extractor_revision)
        query += " ORDER BY created_at DESC,id DESC LIMIT 1"
        return self._decode(self._execute(query, tuple(params)).fetchone(), ("metadata_json",))

    def get_extraction_content(self, project_id: str, extraction_id: str) -> dict | None:
        """Internal-only retrieval used by governed compiler/extractor work."""
        row = self._execute(
            "SELECT id,project_id,content_hash,content FROM knowledge_extraction_artifacts WHERE project_id=? AND id=?",
            (project_id, extraction_id),
        ).fetchone()
        return self._decode(row)

    def create_table_artifact(self, table: TableArtifact) -> dict:
        extraction = self.get_extraction_artifact(table.project_id, table.extraction_id)
        if not extraction or extraction["source_id"] != table.source_id:
            raise KeyError("table extraction is missing or belongs to another source")
        existing = self._execute(
            "SELECT * FROM knowledge_table_artifacts WHERE project_id=? AND extraction_id=? AND content_hash=?",
            (table.project_id, table.extraction_id, table.content_hash),
        ).fetchone()
        if existing:
            return self._decode(existing, ("schema_json", "units_json", "metadata_json")) or {}
        self._execute(
            "INSERT INTO knowledge_table_artifacts "
            "(id,project_id,source_id,extraction_id,schema_json,row_count,units_json,content_hash,status,metadata_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                table.id,
                table.project_id,
                table.source_id,
                table.extraction_id,
                self._json_dumps(table.table_schema),
                table.row_count,
                self._json_dumps(table.units),
                table.content_hash,
                table.status,
                self._json_dumps(table.metadata),
                _iso(table.created_at),
            ),
        )
        self._commit()
        return self.get_table_artifact(table.project_id, table.id) or {}

    def get_table_artifact(self, project_id: str, table_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_table_artifacts WHERE project_id=? AND id=?", (project_id, table_id)
        ).fetchone()
        return self._decode(row, ("schema_json", "units_json", "metadata_json"))

    def list_table_artifacts(self, project_id: str, extraction_id: str = "", limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_table_artifacts WHERE project_id=?"
        if extraction_id:
            query += " AND extraction_id=?"
            params.append(extraction_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("schema_json", "units_json", "metadata_json")) or {} for row in rows]

    def create_reference_link(self, reference: ReferenceLink) -> dict:
        if not self.get_source(reference.project_id, reference.source_id):
            raise KeyError("reference source is missing or belongs to another project")
        existing = self._execute(
            "SELECT * FROM knowledge_reference_links WHERE project_id=? AND target_type=? AND target_id=? AND source_id=? "
            "AND anchor_type=? AND anchor=? AND relation=?",
            (
                reference.project_id,
                reference.target_type,
                reference.target_id,
                reference.source_id,
                reference.anchor_type,
                reference.anchor,
                reference.relation,
            ),
        ).fetchone()
        if existing:
            return self._decode(existing, ("metadata_json",)) or {}
        self._execute(
            "INSERT INTO knowledge_reference_links "
            "(id,project_id,source_id,target_type,target_id,anchor_type,anchor,relation,resolution_state,metadata_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                reference.id,
                reference.project_id,
                reference.source_id,
                reference.target_type,
                reference.target_id,
                reference.anchor_type,
                reference.anchor,
                reference.relation,
                reference.resolution_state.value,
                self._json_dumps(reference.metadata),
                _iso(reference.created_at),
            ),
        )
        self._commit()
        return self.get_reference_link(reference.project_id, reference.id) or {}

    def get_reference_link(self, project_id: str, reference_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_reference_links WHERE project_id=? AND id=?", (project_id, reference_id)
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_reference_links(self, project_id: str, source_id: str = "", limit: int = 100) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_reference_links WHERE project_id=?"
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def create_source_capture_attempt(self, attempt: SourceCaptureAttempt) -> dict:
        """Persist capture evidence without duplicating raw source material."""
        if attempt.run_id and not self.get_run(attempt.project_id, attempt.run_id):
            raise KeyError("capture attempt run is missing or belongs to another project")
        if attempt.source_id and not self.get_source(attempt.project_id, attempt.source_id):
            raise KeyError("capture attempt source is missing or belongs to another project")
        self._execute(
            "INSERT INTO knowledge_source_capture_attempts "
            "(id,project_id,source_type,origin,content_hash,run_id,source_id,outcome,policy_json,projection_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                attempt.id,
                attempt.project_id,
                attempt.source_type,
                attempt.origin,
                attempt.content_hash,
                attempt.run_id,
                attempt.source_id,
                attempt.outcome.value,
                self._json_dumps(attempt.policy),
                self._json_dumps(attempt.projection),
                _iso(attempt.created_at),
            ),
        )
        self._commit()
        return self.get_source_capture_attempt(attempt.project_id, attempt.id) or {}

    def get_source_capture_attempt(self, project_id: str, attempt_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_source_capture_attempts WHERE project_id=? AND id=?",
            (project_id, attempt_id),
        ).fetchone()
        return self._decode(row, ("policy_json", "projection_json"))

    def list_source_capture_attempts(
        self,
        project_id: str,
        *,
        run_id: str = "",
        source_id: str = "",
        limit: int = 100,
    ) -> list[dict]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_source_capture_attempts WHERE project_id=?"
        if run_id:
            query += " AND run_id=?"
            params.append(run_id)
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode(row, ("policy_json", "projection_json")) or {} for row in rows]

    def update_source_status(self, project_id: str, source_id: str, status: SourceStatus) -> dict:
        now = self._now()
        self._execute(
            "UPDATE knowledge_sources SET status=?,updated_at=? WHERE project_id=? AND id=?",
            (status.value, now, project_id, source_id),
        )
        self._commit()
        return self.get_source(project_id, source_id) or {}

    def return_source_to_review(self, project_id: str, source_id: str, *, reason: str) -> dict:
        """Revoke a pre-triage eligibility grant without deleting evidence."""
        source = self.get_source(project_id, source_id)
        if not source:
            raise KeyError("source not found in project")
        if source["status"] == SourceStatus.VALIDATED.value:
            return source
        if source["status"] != SourceStatus.ELIGIBLE.value:
            raise ValueError("only eligible evidence can return to review")
        metadata = dict(source.get("metadata") or {})
        metadata["admission_correction"] = {
            "reason": reason,
            "previous_status": SourceStatus.ELIGIBLE.value,
            "corrected_at": self._now(),
        }
        self._execute(
            "UPDATE knowledge_sources SET status=?,metadata_json=?,updated_at=? WHERE project_id=? AND id=? AND status=?",
            (
                SourceStatus.VALIDATED.value,
                self._json_dumps(metadata),
                self._now(),
                project_id,
                source_id,
                SourceStatus.ELIGIBLE.value,
            ),
        )
        self._commit()
        return self.get_source(project_id, source_id) or {}

    def mark_source_citations_stale(self, project_id: str, source_id: str) -> None:
        self._execute(
            "UPDATE knowledge_citations SET status='stale' WHERE project_id=? AND source_id=? AND status='active'",
            (project_id, source_id),
        )
        self._commit()

    def create_proposal(self, proposal: WikiProposal, actor_id: str = "") -> dict:
        self._execute(
            "INSERT INTO knowledge_proposals "
            "(id,project_id,base_revision,source_ids_json,operations_json,rationale,status,eval_summary_json,manual,actor_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal.id, proposal.project_id, proposal.base_revision,
                self._json_dumps(proposal.source_ids),
                self._json_dumps([operation.model_dump(mode="json") for operation in proposal.operations]),
                proposal.rationale, proposal.status.value, self._json_dumps(proposal.eval_summary),
                1 if proposal.manual else 0, actor_id, _iso(proposal.created_at), _iso(proposal.updated_at),
            ),
        )
        for position, operation in enumerate(proposal.operations):
            self._execute(
                "INSERT INTO knowledge_proposal_operations "
                "(id,proposal_id,project_id,operation_index,operation_type,target_path,destination_path,expected_content_hash,content,source_ids_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    operation.id, proposal.id, proposal.project_id, position, operation.operation.value,
                    operation.path, operation.destination_path, operation.expected_content_hash,
                    operation.content, self._json_dumps(operation.source_ids),
                ),
            )
        self._commit()
        return self.get_proposal(proposal.project_id, proposal.id) or {}

    def get_proposal(self, project_id: str, proposal_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_proposals WHERE project_id=? AND id=?", (project_id, proposal_id)
        ).fetchone()
        return self._decode(row, ("source_ids_json", "operations_json", "eval_summary_json"))

    def list_proposals(self, project_id: str, limit: int = 100) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_proposals WHERE project_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [self._decode(row, ("source_ids_json", "operations_json", "eval_summary_json")) or {} for row in rows]

    def upsert_schedule(
        self, *, project_id: str, job_type: str, cron: str, timezone_name: str, enabled: bool, next_run_at: str
    ) -> dict:
        schedule_id = hashlib.sha256(f"{project_id}|{job_type}".encode("utf-8")).hexdigest()[:24]
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_schedules (id,project_id,job_type,cron,enabled,timezone,last_run_at,next_run_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET cron=excluded.cron,enabled=excluded.enabled, "
            "timezone=excluded.timezone,next_run_at=excluded.next_run_at,updated_at=excluded.updated_at",
            (schedule_id, project_id, job_type, cron, 1 if enabled else 0, timezone_name, None, next_run_at, now, now),
        )
        self._commit()
        row = self._execute("SELECT * FROM knowledge_schedules WHERE id=?", (schedule_id,)).fetchone()
        return self._decode(row) or {}

    def list_schedules(self, project_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_schedules WHERE project_id=? ORDER BY job_type", (project_id,)
        ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def get_schedule(self, project_id: str, schedule_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_schedules WHERE project_id=? AND id=?", (project_id, schedule_id)
        ).fetchone()
        return self._decode(row)

    def set_schedule_enabled(self, *, project_id: str, schedule_id: str, enabled: bool, next_run_at: str = "") -> dict:
        cursor = self._execute(
            "UPDATE knowledge_schedules SET enabled=?,next_run_at=?,updated_at=? WHERE project_id=? AND id=?",
            (1 if enabled else 0, next_run_at if enabled else "", self._now(), project_id, schedule_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("knowledge schedule not found")
        return self.get_schedule(project_id, schedule_id) or {}

    def list_due_schedules(self, now: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_schedules WHERE enabled=1 AND next_run_at<>'' AND next_run_at<=? "
            "ORDER BY next_run_at,id",
            (now,),
        ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def advance_schedule(self, *, schedule_id: str, expected_next_run_at: str, next_run_at: str, last_run_at: str) -> bool:
        cursor = self._execute(
            "UPDATE knowledge_schedules SET last_run_at=?,next_run_at=?,updated_at=? "
            "WHERE id=? AND enabled=1 AND next_run_at=?",
            (last_run_at, next_run_at, self._now(), schedule_id, expected_next_run_at),
        )
        self._commit()
        return cursor.rowcount == 1

    def claim_schedule_run(self, run: KnowledgeRun, idempotency_key: str) -> dict:
        claim_id = hashlib.sha256(
            f"{run.project_id}|{run.run_type}|{idempotency_key}".encode("utf-8")
        ).hexdigest()[:24]
        existing = self._execute("SELECT run_id FROM knowledge_schedule_claims WHERE id=?", (claim_id,)).fetchone()
        if existing:
            return {"claimed": False, "run_id": self._row_to_dict(existing)["run_id"]}
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_schedule_claims (id,project_id,job_type,idempotency_key,run_id,created_at) VALUES (?,?,?,?,?,?)",
            (claim_id, run.project_id, run.run_type, idempotency_key, run.id, now),
        )
        self._execute(
            "INSERT INTO knowledge_runs "
            "(id,project_id,run_type,trigger,status,actor_id,input_refs_json,output_refs_json,error,retry_of,started_at,completed_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.id, run.project_id, run.run_type, run.trigger, run.status.value, run.actor_id,
                self._json_dumps(run.input_refs), self._json_dumps(run.output_refs), run.error, run.retry_of,
                _iso(run.started_at), _iso(run.completed_at), _iso(run.created_at), _iso(run.updated_at),
            ),
        )
        self._commit()
        self.append_run_event(
            project_id=run.project_id,
            run_id=run.id,
            event_type="knowledge.run.queued",
            payload={"run_type": run.run_type, "trigger": run.trigger, "idempotency_key": idempotency_key},
        )
        return {"claimed": True, "run_id": run.id}

    def release_schedule_claim(self, *, project_id: str, job_type: str, idempotency_key: str) -> None:
        claim_id = hashlib.sha256(f"{project_id}|{job_type}|{idempotency_key}".encode("utf-8")).hexdigest()[:24]
        self._execute("DELETE FROM knowledge_schedule_claims WHERE id=?", (claim_id,))
        self._commit()

    def update_proposal_status(self, project_id: str, proposal_id: str, status: ProposalStatus) -> dict:
        self._execute(
            "UPDATE knowledge_proposals SET status=?,updated_at=? WHERE project_id=? AND id=?",
            (status.value, self._now(), project_id, proposal_id),
        )
        self._commit()
        return self.get_proposal(project_id, proposal_id) or {}

    def update_proposal_review(
        self,
        project_id: str,
        proposal_id: str,
        status: ProposalStatus,
        eval_summary: dict[str, Any],
    ) -> dict:
        self._execute(
            "UPDATE knowledge_proposals SET status=?,eval_summary_json=?,updated_at=? WHERE project_id=? AND id=?",
            (status.value, self._json_dumps(eval_summary), self._now(), project_id, proposal_id),
        )
        self._commit()
        return self.get_proposal(project_id, proposal_id) or {}

    def list_pages(self, project_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_wiki_pages WHERE project_id=? AND status='published' ORDER BY path", (project_id,)
        ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def get_page(self, project_id: str, page_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_wiki_pages WHERE project_id=? AND id=?", (project_id, page_id)
        ).fetchone()
        return self._decode(row, ("metadata_json",))

    def list_page_revisions(self, project_id: str, page_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT id,project_id,wiki_page_id,version,content_hash,proposal_id,created_at "
            "FROM knowledge_wiki_page_revisions WHERE project_id=? AND wiki_page_id=? ORDER BY version DESC",
            (project_id, page_id),
        ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def get_page_content(self, project_id: str, page_id: str) -> dict | None:
        row = self._execute(
            "SELECT revision.id,revision.wiki_page_id,revision.version,revision.content_hash,revision.content,revision.proposal_id,revision.created_at "
            "FROM knowledge_wiki_page_revisions AS revision "
            "JOIN knowledge_wiki_pages AS page ON page.id=revision.wiki_page_id AND page.project_id=revision.project_id "
            "WHERE revision.project_id=? AND revision.wiki_page_id=? AND page.status='published' "
            "ORDER BY revision.version DESC LIMIT 1",
            (project_id, page_id),
        ).fetchone()
        return self._decode(row)

    def get_page_revision_content(self, project_id: str, page_id: str, revision_id: str) -> dict | None:
        row = self._execute(
            "SELECT revision.id,revision.wiki_page_id,revision.version,revision.content_hash,revision.content,revision.proposal_id,revision.created_at "
            "FROM knowledge_wiki_page_revisions AS revision "
            "JOIN knowledge_wiki_pages AS page ON page.id=revision.wiki_page_id AND page.project_id=revision.project_id "
            "WHERE revision.project_id=? AND revision.wiki_page_id=? AND revision.id=? AND page.status='published'",
            (project_id, page_id, revision_id),
        ).fetchone()
        return self._decode(row)

    def list_citations(self, project_id: str, page_id: str = "", include_stale: bool = False) -> list[dict]:
        if page_id:
            if include_stale:
                rows = self._execute(
                    "SELECT * FROM knowledge_citations WHERE project_id=? AND wiki_page_id=? ORDER BY id",
                    (project_id, page_id),
                ).fetchall()
            else:
                rows = self._execute(
                    "SELECT * FROM knowledge_citations WHERE project_id=? AND wiki_page_id=? AND status='active' ORDER BY id",
                    (project_id, page_id),
                ).fetchall()
        else:
            if include_stale:
                rows = self._execute(
                    "SELECT * FROM knowledge_citations WHERE project_id=? ORDER BY wiki_page_id,id", (project_id,)
                ).fetchall()
            else:
                rows = self._execute(
                    "SELECT * FROM knowledge_citations WHERE project_id=? AND status='active' ORDER BY wiki_page_id,id",
                    (project_id,),
                ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def list_evidence_citation_metadata(self, project_id: str, *, include_stale: bool = False) -> list[dict[str, Any]]:
        """List citation lineage without selecting immutable Wiki claim text."""
        query = (
            "SELECT id,project_id,wiki_page_id,source_id,anchor,status,created_at "
            "FROM knowledge_citations WHERE project_id=?"
        )
        if not include_stale:
            query += " AND status='active'"
        query += " ORDER BY wiki_page_id,id"
        rows = self._execute(query, (project_id,)).fetchall()
        return [self._decode(row) or {} for row in rows]

    def get_evidence_citation_metadata(self, project_id: str, citation_id: str) -> dict[str, Any] | None:
        """Read citation lineage metadata without selecting its immutable claim text."""
        row = self._execute(
            "SELECT id,project_id,wiki_page_id,source_id,anchor,status,created_at "
            "FROM knowledge_citations WHERE project_id=? AND id=?",
            (project_id, citation_id),
        ).fetchone()
        return self._decode(row)

    def get_citation(self, project_id: str, citation_id: str) -> dict | None:
        """Return one project-scoped Wiki citation for a redacted read projection."""
        row = self._execute(
            "SELECT * FROM knowledge_citations WHERE project_id=? AND id=?",
            (project_id, citation_id),
        ).fetchone()
        return self._decode(row)

    def record_distillation(
        self,
        *,
        project_id: str,
        week: str,
        paths: list[str],
        source_cutoff: str,
        status: str = "generated",
    ) -> dict:
        if len(paths) != 3:
            raise ValueError("weekly distillation requires exactly three output paths")
        by_name = {Path(path).name: path for path in paths}
        required = {"knowledge-action.md", "content-creation.md", "context-pack.md"}
        if set(by_name) != required:
            raise ValueError("weekly distillation output paths are incomplete")
        row_id = hashlib.sha256(f"{project_id}|{week}|{source_cutoff}".encode("utf-8")).hexdigest()[:24]
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_distillations "
            "(id,project_id,week,knowledge_path,content_path,context_path,source_cutoff,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,week,source_cutoff) DO UPDATE SET status=excluded.status",
            (
                row_id,
                project_id,
                week,
                by_name["knowledge-action.md"],
                by_name["content-creation.md"],
                by_name["context-pack.md"],
                source_cutoff,
                status,
                now,
            ),
        )
        self._commit()
        row = self._execute("SELECT * FROM knowledge_distillations WHERE id=?", (row_id,)).fetchone()
        return self._decode(row) or {}

    def list_distillations(self, project_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_distillations WHERE project_id=? ORDER BY week DESC,created_at DESC", (project_id,)
        ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def get_distillation(self, project_id: str, distillation_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_distillations WHERE project_id=? AND id=?", (project_id, distillation_id)
        ).fetchone()
        return self._decode(row)

    def record_publication(
        self,
        *,
        project_id: str,
        proposal_id: str = "",
        contents: dict[str, str],
        source_ids: list[str],
        expected_content_hashes: dict[str, str] | None = None,
    ) -> None:
        """Persist a published Vault snapshot, citations, and its derived graph atomically."""
        pages = {path: content for path, content in contents.items() if path.startswith("wiki/") or path == "AGENTS.md"}
        backend = self._get_connection()
        try:
            dialect = getattr(backend, "dialect", "sqlite")
            if dialect == "sqlite":
                self._execute("BEGIN IMMEDIATE")
            page_query = (
                "SELECT * FROM knowledge_wiki_pages WHERE project_id=? FOR UPDATE"
                if dialect == "postgresql"
                else "SELECT * FROM knowledge_wiki_pages WHERE project_id=?"
            )
            rows = self._execute(
                page_query,
                (project_id,),
            ).fetchall()
            existing = {
                page["path"]: page
                for page in [self._decode(row, ("metadata_json",)) or {} for row in rows]
            }
            for path, expected_hash in (expected_content_hashes or {}).items():
                persisted = existing.get(path)
                if not persisted or persisted["content_hash"] != expected_hash or persisted["status"] != "published":
                    raise PublicationConflictError(f"persisted Wiki revision conflict at {path}")

            now = self._now()
            indexed_pages: list[dict[str, Any]] = []
            changed_revisions: list[tuple[str, int, str, str]] = []
            for path, content in sorted(pages.items()):
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                prior = existing.get(path)
                page_id = prior["id"] if prior else hashlib.sha256(f"{project_id}|{path}".encode("utf-8")).hexdigest()[:24]
                changed = not prior or prior["content_hash"] != content_hash or prior["status"] != "published"
                version = (int(prior["version"]) + 1) if prior and changed else (int(prior["version"]) if prior else 1)
                metadata = self._page_metadata(path, content)
                indexed_pages.append({"id": page_id, "path": path, "content": content, "content_hash": content_hash, "version": version, **metadata})
                if changed:
                    changed_revisions.append((page_id, version, content_hash, content))

            for page in indexed_pages:
                self._execute(
                    "INSERT INTO knowledge_wiki_pages "
                    "(id,project_id,path,title,page_kind,content_hash,version,metadata_json,status,published_at,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,path) DO UPDATE SET "
                    "title=excluded.title,page_kind=excluded.page_kind,content_hash=excluded.content_hash,version=excluded.version,"
                    "metadata_json=excluded.metadata_json,status='published',published_at=excluded.published_at,updated_at=excluded.updated_at",
                    (page["id"], project_id, page["path"], page["title"], page["page_kind"], page["content_hash"],
                     page["version"], self._json_dumps(page["metadata"]), "published", now, now, now),
                )
            missing_paths = set(existing) - set(pages)
            for path in missing_paths:
                self._execute(
                    "UPDATE knowledge_wiki_pages SET status='archived',updated_at=? WHERE project_id=? AND path=?",
                    (now, project_id, path),
                )
            for page_id, version, content_hash, content in changed_revisions:
                revision_id = hashlib.sha256(f"{page_id}|{version}".encode("utf-8")).hexdigest()[:24]
                self._execute(
                    "INSERT INTO knowledge_wiki_page_revisions "
                    "(id,project_id,wiki_page_id,version,content_hash,content,proposal_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (revision_id, project_id, page_id, version, content_hash, content, proposal_id, now),
                )
            self._execute("DELETE FROM knowledge_citations WHERE project_id=?", (project_id,))
            source_records = {source["id"]: source for source in self.list_sources(project_id)}
            source_statuses = {source_id: source["status"] for source_id, source in source_records.items()}
            for page in indexed_pages:
                if page["path"] == "AGENTS.md":
                    continue
                for sequence, source_id in enumerate(self._source_ids(page["content"])):
                    citation_id = hashlib.sha256(f"{page['id']}|{source_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
                    self._execute(
                        "INSERT INTO knowledge_citations (id,project_id,wiki_page_id,source_id,anchor,claim_text,status,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            citation_id, project_id, page["id"], source_id, "", self._citation_claim(page["content"], source_id),
                            "stale" if source_statuses.get(source_id) in {"superseded", "rejected"} else "active", now,
                        ),
                    )
            self._replace_graph_edges_in_transaction(
                project_id,
                indexed_pages,
                proposal_id,
                now,
                source_records=source_records,
            )
            if proposal_id:
                self._execute(
                    "UPDATE knowledge_proposals SET status=?,updated_at=? WHERE project_id=? AND id=?",
                    (ProposalStatus.PUBLISHED.value, now, project_id, proposal_id),
                )
            for source_id in source_ids:
                self._execute(
                    "UPDATE knowledge_sources SET status=?,updated_at=? WHERE project_id=? AND id=?",
                    (SourceStatus.PROCESSED.value, now, project_id, source_id),
                )
            backend.commit()
        except Exception:
            backend.rollback()
            raise

    def _replace_graph_edges_in_transaction(
        self,
        project_id: str,
        pages: list[dict[str, Any]],
        proposal_id: str,
        now: str,
        *,
        source_records: dict[str, dict[str, Any]],
    ) -> None:
        by_path = {page["path"]: page for page in pages}
        graph_rows: dict[str, tuple[str, str, str, str, dict[str, Any], str]] = {}

        def add(
            from_id: str,
            to_id: str,
            edge_type: str,
            *,
            metadata: dict[str, Any] | None = None,
            revision: str = "",
        ) -> None:
            edge_id = hashlib.sha256(f"{project_id}|{from_id}|{to_id}|{edge_type}".encode("utf-8")).hexdigest()[:24]
            graph_rows[edge_id] = (from_id, to_id, edge_type, edge_id, metadata or {}, revision)

        for page in pages:
            for target in re.findall(r"\[\[([^\]]+)\]\]", page["content"]):
                target_path = target if target.endswith(".md") else f"{target}.md"
                if target_path in by_path:
                    add(page["id"], by_path[target_path]["id"], "wiki_links_to")
            if page["path"] == "AGENTS.md":
                if proposal_id:
                    add(proposal_id, page["id"], "proposal_changes_page")
                continue
            for sequence, source_id in enumerate(self._source_ids(page["content"])):
                evidence = self._evidence_edge_metadata(
                    page,
                    source_id,
                    sequence,
                    source_records.get(source_id),
                )
                add(
                    page["id"],
                    source_id,
                    "wiki_cites_source",
                    metadata={"evidence": evidence},
                    revision=page["content_hash"],
                )
                if page["page_kind"] == "decision":
                    add(
                        page["id"],
                        source_id,
                        "decision_uses_evidence",
                        metadata={"evidence": evidence},
                        revision=page["content_hash"],
                    )
            if proposal_id:
                add(proposal_id, page["id"], "proposal_changes_page")
        self._execute(
            "DELETE FROM knowledge_graph_edges WHERE project_id=? AND edge_type<>?",
            (project_id, "source_supersedes_source"),
        )
        for from_id, to_id, edge_type, edge_id, metadata, revision in graph_rows.values():
            self._execute(
                "INSERT INTO knowledge_graph_edges (id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (edge_id, project_id, from_id, to_id, edge_type, self._json_dumps(metadata), revision or proposal_id, now),
            )

    @staticmethod
    def _source_ids(content: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"\[source:([^\]\s]+)\]", content)))

    @staticmethod
    def _citation_claim(content: str, source_id: str) -> str:
        for line in content.splitlines():
            if f"[source:{source_id}]" in line:
                return line.strip()[:1000]
        return ""

    @staticmethod
    def _evidence_edge_metadata(
        page: dict[str, Any],
        source_id: str,
        sequence: int,
        source: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Attach immutable citation/version facts without duplicating evidence text."""
        citation_id = hashlib.sha256(f"{page['id']}|{source_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
        status = str((source or {}).get("status") or "missing")
        return {
            "citation_id": citation_id,
            "source_id": source_id,
            "source_content_hash": str((source or {}).get("content_hash") or ""),
            "source_status": status,
            "source_revision_available": bool(source),
            "page_content_hash": str(page["content_hash"]),
            "page_version": int(page["version"]),
            "extraction_method": "explicit_source_marker_v1",
        }

    @staticmethod
    def _page_metadata(path: str, content: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if content.startswith("---\n"):
            boundary = content.find("\n---", 4)
            if boundary >= 0:
                parsed = yaml.safe_load(content[4:boundary]) or {}
                if isinstance(parsed, dict):
                    metadata = parsed
        title = str(metadata.get("title") or Path(path).stem.replace("-", " ").title())
        page_kind = str(metadata.get("kind") or ("rules" if path == "AGENTS.md" else "index" if path.endswith("index.md") else "general"))
        return {"title": title, "page_kind": page_kind, "metadata": metadata}

    def create_run(self, run: KnowledgeRun) -> dict:
        self._execute(
            "INSERT INTO knowledge_runs "
            "(id,project_id,run_type,trigger,status,actor_id,input_refs_json,output_refs_json,error,retry_of,started_at,completed_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.id, run.project_id, run.run_type, run.trigger, run.status.value, run.actor_id,
                self._json_dumps(run.input_refs), self._json_dumps(run.output_refs), run.error, run.retry_of,
                _iso(run.started_at), _iso(run.completed_at), _iso(run.created_at), _iso(run.updated_at),
            ),
        )
        self._commit()
        self.append_run_event(
            project_id=run.project_id,
            run_id=run.id,
            event_type=f"knowledge.run.{run.status.value}",
            payload={"run_type": run.run_type, "trigger": run.trigger, "status": run.status.value},
        )
        return self.get_run(run.project_id, run.id) or {}

    def get_run(self, project_id: str, run_id: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_runs WHERE project_id=? AND id=?", (project_id, run_id)
        ).fetchone()
        return self._decode(row, ("input_refs_json", "output_refs_json"))

    def list_runs(self, project_id: str, limit: int = 100) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_runs WHERE project_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [self._decode(row, ("input_refs_json", "output_refs_json")) or {} for row in rows]

    def list_running_runs(self, project_id: str | None = None, *, limit: int = 500) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        if project_id:
            rows = self._execute(
                "SELECT * FROM knowledge_runs WHERE project_id=? AND status=? ORDER BY updated_at LIMIT ?",
                (project_id, RunStatus.RUNNING.value, limit),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_runs WHERE status=? ORDER BY updated_at LIMIT ?",
                (RunStatus.RUNNING.value, limit),
            ).fetchall()
        return [self._decode(row, ("input_refs_json", "output_refs_json")) or {} for row in rows]

    def latest_run_for_type(self, project_id: str, run_type: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_runs WHERE project_id=? AND run_type=? ORDER BY created_at DESC,id DESC LIMIT 1",
            (project_id, run_type),
        ).fetchone()
        return self._decode(row, ("input_refs_json", "output_refs_json"))

    def list_completed_horizon_run_ids(self, project_id: str) -> set[str]:
        rows = self._execute(
            "SELECT output_refs_json FROM knowledge_runs WHERE project_id=? AND run_type=? AND status=?",
            (project_id, "horizon_capture", RunStatus.COMPLETED.value),
        ).fetchall()
        run_ids: set[str] = set()
        for row in rows:
            decoded = self._decode(row, ("output_refs_json",)) or {}
            run_id = str((decoded.get("output_refs") or {}).get("horizon_run_id") or "").strip()
            if run_id:
                run_ids.add(run_id)
        return run_ids

    def update_run_status(
        self,
        project_id: str,
        run_id: str,
        status: RunStatus,
        error: str = "",
        output_refs: dict[str, Any] | None = None,
    ) -> dict:
        now = self._now()
        completed_at = now if status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.UNAVAILABLE} else ""
        if output_refs is None:
            self._execute(
                "UPDATE knowledge_runs SET status=?,error=?,completed_at=?,updated_at=? WHERE project_id=? AND id=?",
                (status.value, error, completed_at, now, project_id, run_id),
            )
        else:
            self._execute(
                "UPDATE knowledge_runs SET status=?,error=?,output_refs_json=?,completed_at=?,updated_at=? WHERE project_id=? AND id=?",
                (status.value, error, self._json_dumps(output_refs), completed_at, now, project_id, run_id),
            )
        self._commit()
        self.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type=f"knowledge.run.{status.value}",
            payload={"status": status.value, "error": error, "output_refs": output_refs or {}},
        )
        return self.get_run(project_id, run_id) or {}

    def update_run_input_refs(self, project_id: str, run_id: str, input_refs: dict[str, Any]) -> dict:
        """Persist normalized executor inputs before a run can be retried."""
        self._execute(
            "UPDATE knowledge_runs SET input_refs_json=?,updated_at=? WHERE project_id=? AND id=?",
            (self._json_dumps(input_refs), self._now(), project_id, run_id),
        )
        self._commit()
        return self.get_run(project_id, run_id) or {}

    def claim_run_execution(self, *, project_id: str, run_id: str) -> bool:
        """Atomically claim a queued run before an executor performs any work."""
        now = self._now()
        cursor = self._execute(
            "UPDATE knowledge_runs SET status=?,error='',started_at=?,completed_at='',updated_at=? "
            "WHERE project_id=? AND id=? AND status=?",
            (RunStatus.RUNNING.value, now, now, project_id, run_id, RunStatus.QUEUED.value),
        )
        claimed = bool(getattr(cursor, "rowcount", 0))
        self._commit()
        if claimed:
            self.append_run_event(
                project_id=project_id,
                run_id=run_id,
                event_type="knowledge.run.running",
                payload={"status": RunStatus.RUNNING.value, "error": "", "output_refs": {}},
            )
        return claimed

    def append_run_event(self, *, project_id: str, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict:
        """Append an ordered, project-scoped event that can be replayed after reconnect."""
        encoded_payload = self._json_dumps(payload or {})
        if getattr(self._get_connection(), "dialect", "sqlite") == "postgresql":
            # Queue dispatch and a fast worker can append at the same instant.
            # Serialize only this run's sequence allocation until the commit below.
            self._execute("SELECT pg_advisory_xact_lock(?)", (_run_event_advisory_lock_key(project_id, run_id),))
        exists = self._execute(
            "SELECT 1 FROM knowledge_runs WHERE project_id=? AND id=?", (project_id, run_id)
        ).fetchone()
        if not exists:
            raise ValueError("knowledge run not found")
        existing = self._execute(
            "SELECT * FROM knowledge_run_events WHERE project_id=? AND run_id=? AND event_type=? "
            "AND payload_json=? ORDER BY sequence DESC LIMIT 1",
            (project_id, run_id, event_type, encoded_payload),
        ).fetchone()
        if existing:
            self._commit()
            return self._decode(existing, ("payload_json",)) or {}
        row = self._execute(
            "SELECT COALESCE(MAX(sequence),0)+1 AS next_sequence FROM knowledge_run_events WHERE project_id=? AND run_id=?",
            (project_id, run_id),
        ).fetchone()
        sequence = int(self._row_to_dict(row)["next_sequence"])
        event_id = hashlib.sha256(f"{project_id}|{run_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
        created_at = self._now()
        self._execute(
            "INSERT INTO knowledge_run_events (id,project_id,run_id,sequence,event_type,payload_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (event_id, project_id, run_id, sequence, event_type, encoded_payload, created_at),
        )
        self._commit()
        return {
            "id": event_id, "project_id": project_id, "run_id": run_id, "sequence": sequence,
            "event_type": event_type, "payload": payload or {}, "created_at": created_at,
        }

    def list_run_events(self, *, project_id: str, run_id: str, after_sequence: int = 0, limit: int = 500) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_run_events WHERE project_id=? AND run_id=? AND sequence>? "
            "ORDER BY sequence ASC LIMIT ?",
            (project_id, run_id, after_sequence, limit),
        ).fetchall()
        return [self._decode(row, ("payload_json",)) or {} for row in rows]

    def latest_run_event_sequence(self, *, project_id: str, run_id: str) -> int:
        row = self._execute(
            "SELECT COALESCE(MAX(sequence),0) AS sequence FROM knowledge_run_events WHERE project_id=? AND run_id=?",
            (project_id, run_id),
        ).fetchone()
        return int(row["sequence"] if row else 0)

    def list_graph_edges(
        self,
        project_id: str,
        edge_type: str | None = None,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        if edge_type:
            rows = self._execute(
                "SELECT * FROM knowledge_graph_edges WHERE project_id=? AND edge_type=? ORDER BY id LIMIT ? OFFSET ?",
                (project_id, edge_type, limit, offset),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_graph_edges WHERE project_id=? ORDER BY id LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def count_graph_edges(self, project_id: str, edge_type: str | None = None) -> int:
        if edge_type:
            row = self._execute(
                "SELECT COUNT(*) AS count FROM knowledge_graph_edges WHERE project_id=? AND edge_type=?",
                (project_id, edge_type),
            ).fetchone()
        else:
            row = self._execute(
                "SELECT COUNT(*) AS count FROM knowledge_graph_edges WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return int(row["count"] if row else 0)

    def list_backlinks(self, project_id: str, page_id: str, *, limit: int = 200) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_graph_edges WHERE project_id=? AND to_id=? AND edge_type='wiki_links_to' "
            "ORDER BY from_id LIMIT ?",
            (project_id, page_id, max(1, min(int(limit), 200))),
        ).fetchall()
        return [self._decode(row, ("metadata_json",)) or {} for row in rows]

    def replace_graph_edges(self, project_id: str, edges: list[KnowledgeGraphEdge]) -> list[dict]:
        expected = {
            (edge.id, edge.from_id, edge.to_id, edge.edge_type, self._json_dumps(edge.metadata), edge.revision)
            for edge in edges
        }
        existing = self.list_graph_edges(project_id)
        current = {
            (edge["id"], edge["from_id"], edge["to_id"], edge["edge_type"], self._json_dumps(edge["metadata"]), edge["revision"])
            for edge in existing
        }
        if current == expected:
            return existing
        self._execute("DELETE FROM knowledge_graph_edges WHERE project_id=?", (project_id,))
        for edge in edges:
            self._execute(
                "INSERT INTO knowledge_graph_edges (id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (edge.id, edge.project_id, edge.from_id, edge.to_id, edge.edge_type,
                 self._json_dumps(edge.metadata), edge.revision, _iso(edge.created_at)),
            )
        self._commit()
        return self.list_graph_edges(project_id)

    def record_source_supersession(self, *, project_id: str, prior_source_id: str, current_source_id: str) -> dict:
        edge_id = hashlib.sha256(
            f"{project_id}|{current_source_id}|{prior_source_id}|source_supersedes_source".encode("utf-8")
        ).hexdigest()[:24]
        self._execute(
            "INSERT INTO knowledge_graph_edges (id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (edge_id, project_id, current_source_id, prior_source_id, "source_supersedes_source", "{}", "", self._now()),
        )
        self._commit()
        row = self._execute("SELECT * FROM knowledge_graph_edges WHERE id=?", (edge_id,)).fetchone()
        return self._decode(row, ("metadata_json",)) or {}

    def upsert_eval_case(self, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict:
        row_id = hashlib.sha256(f"{project_id}|{case_id}".encode("utf-8")).hexdigest()[:24]
        now = self._now()
        self._execute(
            "INSERT INTO knowledge_eval_cases (id,project_id,case_id,case_type,expected_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id,case_id) DO UPDATE SET "
            "case_type=excluded.case_type,expected_json=excluded.expected_json,updated_at=excluded.updated_at",
            (row_id, project_id, case_id, case_type, self._json_dumps(expected), now, now),
        )
        self._commit()
        row = self._execute(
            "SELECT * FROM knowledge_eval_cases WHERE project_id=? AND case_id=?", (project_id, case_id)
        ).fetchone()
        return self._decode(row, ("expected_json",)) or {}

    def list_eval_cases(self, project_id: str) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_eval_cases WHERE project_id=? ORDER BY case_id", (project_id,)
        ).fetchall()
        return [self._decode(row, ("expected_json",)) or {} for row in rows]

    def record_eval_run(self, *, project_id: str, proposal_id: str = "", wiki_revision: str = "", status: str, summary: dict[str, Any]) -> dict:
        now = self._now()
        row_id = self._generate_id()
        self._execute(
            "INSERT INTO knowledge_eval_runs (id,project_id,proposal_id,wiki_revision,status,summary_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (row_id, project_id, proposal_id or None, wiki_revision, status, self._json_dumps(summary), now),
        )
        self._commit()
        row = self._execute("SELECT * FROM knowledge_eval_runs WHERE id=?", (row_id,)).fetchone()
        return self._decode(row, ("summary_json",)) or {}

    def list_eval_runs(self, project_id: str, limit: int = 20) -> list[dict]:
        rows = self._execute(
            "SELECT * FROM knowledge_eval_runs WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT ?", (project_id, limit)
        ).fetchall()
        return [self._decode(row, ("summary_json",)) or {} for row in rows]
