"""Persistence for project profiles and the governed C/D growth assets."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any
from urllib.parse import urlparse

from app.knowledge.growth_contracts import (
    KnowledgeCandidate,
    KnowledgeCandidateStatus,
    KnowledgeFailureRecord,
    KnowledgeFailureStatus,
    KnowledgeLineageEdge,
    MethodAsset,
    MethodEvolutionRun,
    MethodProposal,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputEvaluation,
    OutputFeedback,
    OutputStatus,
    ProjectKnowledgeProfile,
    SourceTriage,
)
from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_repository import WikiRepository


class LineageConflictError(ValueError):
    """Raised for invalid, cross-project, duplicate or cyclic knowledge lineage."""


class ProfileRevisionConflictError(ValueError):
    """Raised when a profile write loses its database-level revision compare-and-swap."""


class LifecycleConflictError(ValueError):
    """Raised when a governed asset lifecycle precondition or transition is invalid."""


def _iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _bounded_lineage_label(value: object, fallback: str) -> str:
    """Return a compact, non-body label suitable for a graph node."""
    normalized = " ".join(str(value or "").split())
    if not normalized:
        normalized = fallback
    return f"{normalized[:95].rstrip()}..." if len(normalized) > 96 else normalized


def _source_lineage_label(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    horizon = metadata.get("horizon_metadata") if isinstance(metadata.get("horizon_metadata"), dict) else {}
    for value in (
        metadata.get("title"),
        metadata.get("headline"),
        horizon.get("title"),
        metadata.get("ai_summary"),
    ):
        if isinstance(value, str) and value.strip():
            return _bounded_lineage_label(value, "Captured evidence")

    origin = str(record.get("origin") or record.get("vault_path") or "")
    parsed = urlparse(origin)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return _bounded_lineage_label(f"{parsed.hostname.removeprefix('www.')} signal", "Captured evidence")
    return _bounded_lineage_label(origin.rsplit("/", 1)[-1], "Captured evidence")


class GrowthRepository(WikiRepository):
    """Project-scoped repository for the additive A/B/C/D domain."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        ensure_schema(self)

    @classmethod
    def borrow(cls, repository: WikiRepository) -> "GrowthRepository":
        """Expose A/B/C/D tables through an existing Wiki repository backend.

        Task execution owns the original repository. The temporary growth
        facade must therefore not close the shared backend when it is garbage
        collected after one D-layer import.
        """
        growth = cls(backend=repository._get_connection())
        growth._owns_connection = False
        return growth

    def _decode_growth(self, row: Any, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
        return self._decode(row, json_fields) if row else None

    # ---- project profile -------------------------------------------------

    def get_profile(self, project_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT project_id,revision,profile_json,actor_id,created_at,updated_at "
            "FROM knowledge_project_profiles WHERE project_id=?",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        value = self._row_to_dict(row)
        profile = self._json_loads(value.pop("profile_json", "{}"))
        profile.update({"project_id": project_id, "revision": value["revision"], "actor_id": value["actor_id"], "created_at": value["created_at"], "updated_at": value["updated_at"]})
        return profile

    def list_profile_revisions(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT id,project_id,revision,profile_json,actor_id,created_at "
            "FROM knowledge_project_profile_revisions WHERE project_id=? ORDER BY revision DESC LIMIT ?",
            (project_id, max(1, min(limit, 500))),
        ).fetchall()
        return [self._decode(row, ("profile_json",)) or {} for row in rows]

    def save_profile(
        self,
        profile: ProjectKnowledgeProfile,
        actor_id: str = "",
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        backend = self._get_connection()
        dialect = getattr(backend, "dialect", "sqlite")
        try:
            if dialect == "postgresql":
                # Covers both an existing row and the first insert for one
                # project without requiring a separate lock table.
                self._execute(
                    "SELECT pg_advisory_xact_lock(hashtext(?))",
                    (profile.project_id,),
                )
            else:
                self._execute("BEGIN IMMEDIATE")
            row = self._execute(
                "SELECT revision FROM knowledge_project_profiles WHERE project_id=?",
                (profile.project_id,),
            ).fetchone()
            current_revision = int(row["revision"]) if row else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise ProfileRevisionConflictError(
                    f"expected profile revision {expected_revision}, current revision {current_revision}"
                )
            revision = current_revision + 1
            now = self._now()
            payload = profile.model_dump(mode="json")
            payload.pop("revision", None)
            payload.pop("actor_id", None)
            payload.pop("created_at", None)
            payload.pop("updated_at", None)
            encoded = self._json_dumps(payload)
            history_id = hashlib.sha256(
                f"{profile.project_id}|profile|{revision}".encode()
            ).hexdigest()[:24]
            self._execute(
                "INSERT INTO knowledge_project_profile_revisions "
                "(id,project_id,revision,profile_json,actor_id,created_at) VALUES (?,?,?,?,?,?)",
                (history_id, profile.project_id, revision, encoded, actor_id, now),
            )
            if current_revision:
                cursor = self._execute(
                    "UPDATE knowledge_project_profiles SET revision=?,profile_json=?,actor_id=?,updated_at=? "
                    "WHERE project_id=? AND revision=?",
                    (
                        revision,
                        encoded,
                        actor_id,
                        now,
                        profile.project_id,
                        current_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProfileRevisionConflictError(
                        "profile revision changed during update"
                    )
            else:
                self._execute(
                    "INSERT INTO knowledge_project_profiles "
                    "(project_id,revision,profile_json,actor_id,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (profile.project_id, revision, encoded, actor_id, now, now),
                )
            self._commit()
        except Exception:
            backend.rollback()
            raise
        return self.get_profile(profile.project_id) or {}

    # ---- triage ---------------------------------------------------------

    def save_triage(self, triage: SourceTriage) -> dict[str, Any]:
        source = self.get_source(triage.project_id, triage.source_id)
        if not source:
            raise KeyError("source not found in project")
        existing = self._execute(
            "SELECT * FROM knowledge_source_triage "
            "WHERE project_id=? AND source_id=? AND profile_revision=? AND evaluator_revision=?",
            (triage.project_id, triage.source_id, triage.profile_revision, triage.evaluator_revision),
        ).fetchone()
        if existing:
            return self._decode_growth(existing, ("reasons_json",)) or {}
        self._execute(
            "INSERT INTO knowledge_source_triage "
            "(id,project_id,source_id,profile_revision,relevance,value_score,freshness,outputability,connectedness,priority,reliability_pass,disposition,reasons_json,evaluator_revision,evaluator_status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                triage.id, triage.project_id, triage.source_id, triage.profile_revision,
                triage.relevance, triage.value, triage.freshness, triage.outputability,
                triage.connectedness, triage.priority, 1 if triage.reliability_pass else 0,
                triage.disposition.value, self._json_dumps(triage.reasons), triage.evaluator_revision,
                triage.evaluator_status, _iso(triage.created_at),
            ),
        )
        self._commit()
        return self._decode_growth(
            self._execute("SELECT * FROM knowledge_source_triage WHERE id=?", (triage.id,)).fetchone(),
            ("reasons_json",),
        ) or {}

    def list_triage(self, project_id: str, limit: int = 100, disposition: str = "") -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_source_triage WHERE project_id=?"
        if disposition:
            query += " AND disposition=?"
            params.append(disposition)
        query += " ORDER BY priority DESC,created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [self._decode_growth(row, ("reasons_json",)) or {} for row in rows]

    # ---- Cangjie evidence candidates -----------------------------------

    def save_candidate(self, candidate: KnowledgeCandidate) -> dict[str, Any]:
        """Persist a review-only candidate with source/run lineage.

        The immutable source hash is verified before the first write. A
        deterministic fingerprint makes a repeated worker delivery idempotent
        without concealing the original extraction run in the lineage graph.
        """
        source = self.get_source(candidate.project_id, candidate.source_id)
        if not source:
            raise KeyError("candidate source not found in project")
        if str(source.get("content_hash") or "") != candidate.source_content_hash:
            raise ValueError("candidate source content hash no longer matches immutable evidence")
        if not self.get_run(candidate.project_id, candidate.extraction_run_id):
            raise KeyError("candidate extraction run not found in project")
        existing = self._execute(
            "SELECT * FROM knowledge_candidates WHERE project_id=? AND fingerprint=?",
            (candidate.project_id, candidate.fingerprint),
        ).fetchone()
        if existing:
            record = self._decode_growth(existing, ("evidence_json", "metadata_json")) or {}
            self._ensure_candidate_lineage(record)
            return record

        try:
            self._execute(
                "INSERT INTO knowledge_candidates "
                "(id,project_id,source_id,source_content_hash,extraction_run_id,candidate_type,title,claim,explanation,evidence_json,fingerprint,status,reviewer_id,review_note,reviewed_at,metadata_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    candidate.id,
                    candidate.project_id,
                    candidate.source_id,
                    candidate.source_content_hash,
                    candidate.extraction_run_id,
                    candidate.candidate_type.value,
                    candidate.title,
                    candidate.claim,
                    candidate.explanation,
                    self._json_dumps([item.model_dump(mode="json") for item in candidate.evidence]),
                    candidate.fingerprint,
                    candidate.status.value,
                    candidate.reviewer_id,
                    candidate.review_note,
                    _iso(candidate.reviewed_at),
                    self._json_dumps(candidate.metadata),
                    _iso(candidate.created_at),
                    _iso(candidate.updated_at),
                ),
            )
            self._commit()
            record = self.get_candidate(candidate.project_id, candidate.id) or {}
            self._ensure_candidate_lineage(record)
            return record
        except Exception:
            self._execute(
                "DELETE FROM knowledge_graph_edges WHERE project_id=? AND (from_id=? OR to_id=?)",
                (candidate.project_id, candidate.id, candidate.id),
            )
            self._execute(
                "DELETE FROM knowledge_candidates WHERE project_id=? AND id=?",
                (candidate.project_id, candidate.id),
            )
            self._commit()
            raise

    def _ensure_candidate_lineage(self, candidate: dict[str, Any]) -> None:
        if not candidate:
            return
        project_id = str(candidate["project_id"])
        candidate_id = str(candidate["id"])
        self.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=project_id,
                from_type="source",
                from_id=str(candidate["source_id"]),
                to_type="candidate",
                to_id=candidate_id,
                relation="source_extracts_candidate",
                metadata={
                    "content_hash": str(candidate["source_content_hash"]),
                    "candidate_type": str(candidate["candidate_type"]),
                },
            )
        )
        self.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=project_id,
                from_type="run",
                from_id=str(candidate["extraction_run_id"]),
                to_type="candidate",
                to_id=candidate_id,
                relation="run_produces_candidate",
                metadata={"candidate_type": str(candidate["candidate_type"])},
            )
        )

    def get_candidate(self, project_id: str, candidate_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_candidates WHERE project_id=? AND id=?",
            (project_id, candidate_id),
        ).fetchone()
        return self._decode_growth(row, ("evidence_json", "metadata_json"))

    def list_candidates(
        self,
        project_id: str,
        *,
        status: str = "",
        source_id: str = "",
        extraction_run_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_candidates WHERE project_id=?"
        if status:
            query += " AND status=?"
            params.append(status)
        if source_id:
            query += " AND source_id=?"
            params.append(source_id)
        if extraction_run_id:
            query += " AND extraction_run_id=?"
            params.append(extraction_run_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [
            self._decode_growth(row, ("evidence_json", "metadata_json")) or {}
            for row in rows
        ]

    def review_candidate(
        self,
        project_id: str,
        candidate_id: str,
        *,
        decision: KnowledgeCandidateStatus,
        actor_id: str,
        review_note: str = "",
    ) -> dict[str, Any]:
        """Record one terminal human decision; acceptance is not publication."""
        actor = actor_id.strip()
        note = review_note.strip()
        if decision not in {KnowledgeCandidateStatus.ACCEPTED, KnowledgeCandidateStatus.REJECTED}:
            raise ValueError("candidate review decision must be accepted or rejected")
        if not actor:
            raise ValueError("candidate reviewer_id is required")
        backend = self._begin_lifecycle_transaction(f"{project_id}|candidate|{candidate_id}|review")
        try:
            row = self._execute(
                "SELECT * FROM knowledge_candidates WHERE project_id=? AND id=?",
                (project_id, candidate_id),
            ).fetchone()
            current = self._decode_growth(row, ("evidence_json", "metadata_json"))
            if not current:
                raise KeyError("candidate not found in project")
            if current.get("status") != KnowledgeCandidateStatus.PENDING_REVIEW.value:
                raise LifecycleConflictError("candidate review state conflict: decision is already recorded")
            now = self._now()
            cursor = self._execute(
                "UPDATE knowledge_candidates SET status=?,reviewer_id=?,review_note=?,reviewed_at=?,updated_at=? "
                "WHERE project_id=? AND id=? AND status=?",
                (
                    decision.value,
                    actor,
                    note,
                    now,
                    now,
                    project_id,
                    candidate_id,
                    KnowledgeCandidateStatus.PENDING_REVIEW.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleConflictError("candidate review state conflict")
            self._record_lifecycle_audit(
                project_id=project_id,
                target_type="candidate",
                target_id=candidate_id,
                action="review",
                event_type="knowledge.candidate.reviewed",
                actor_id=actor,
                reason=note or "candidate review recorded",
                from_status=KnowledgeCandidateStatus.PENDING_REVIEW.value,
                to_status=decision.value,
                expected={"source_content_hash": str(current.get("source_content_hash") or "")},
                now=now,
            )
            self._commit()
        except Exception:
            backend.rollback()
            raise
        return self.get_candidate(project_id, candidate_id) or {}

    # ---- methods --------------------------------------------------------

    def create_method(self, method: MethodAsset) -> dict[str, Any]:
        self._execute(
            "INSERT INTO knowledge_methods (id,project_id,slug,name,applicability_json,exclusions_json,status,active_revision_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                method.id, method.project_id, method.slug, method.name,
                self._json_dumps(method.applicability), self._json_dumps(method.exclusions),
                method.status.value, method.active_revision_id, _iso(method.created_at), _iso(method.updated_at),
            ),
        )
        self._commit()
        return self.get_method(method.project_id, method.id) or {}

    def get_method(self, project_id: str, method_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_methods WHERE project_id=? AND id=?", (project_id, method_id)
        ).fetchone()
        return self._decode_growth(row, ("applicability_json", "exclusions_json"))

    def get_method_by_slug(self, project_id: str, slug: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_methods WHERE project_id=? AND slug=?", (project_id, slug)
        ).fetchone()
        return self._decode_growth(row, ("applicability_json", "exclusions_json"))

    def list_methods(self, project_id: str, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_methods WHERE project_id=?"
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row, ("applicability_json", "exclusions_json")) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def save_method_revision(self, revision: MethodRevision) -> dict[str, Any]:
        method = self.get_method(revision.project_id, revision.method_id)
        if not method:
            raise KeyError("method not found in project")
        self._execute(
            "INSERT INTO knowledge_method_revisions "
            "(id,method_id,project_id,version,body,manifest_json,eval_summary_json,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                revision.id, revision.method_id, revision.project_id, revision.version,
                revision.body, self._json_dumps(revision.manifest), self._json_dumps(revision.eval_summary),
                revision.status.value, _iso(revision.created_at),
            ),
        )
        self._commit()
        return self.get_method_revision(revision.project_id, revision.id) or {}

    def get_method_revision(self, project_id: str, revision_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_method_revisions WHERE project_id=? AND id=?", (project_id, revision_id)
        ).fetchone()
        return self._decode_growth(row, ("manifest_json", "eval_summary_json"))

    def list_method_revisions(
        self,
        project_id: str,
        method_id: str,
        *,
        limit: int = 100,
        before_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return one method's immutable revisions newest-first within a project."""
        if not self.get_method(project_id, method_id):
            raise KeyError("method not found in project")
        params: list[Any] = [project_id, method_id]
        query = (
            "SELECT * FROM knowledge_method_revisions "
            "WHERE project_id=? AND method_id=?"
        )
        if before_version is not None:
            if before_version < 1:
                raise ValueError("before_version must be at least 1")
            query += " AND version<?"
            params.append(before_version)
        query += " ORDER BY version DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [
            self._decode_growth(row, ("manifest_json", "eval_summary_json")) or {}
            for row in rows
        ]

    def save_method_proposal(self, proposal: MethodProposal) -> dict[str, Any]:
        self._execute(
            "INSERT INTO knowledge_method_proposals "
            "(id,project_id,method_id,operation,body,manifest_json,source_output_ids_json,rationale,status,package_audit_json,eval_summary_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal.id, proposal.project_id, proposal.method_id, proposal.operation, proposal.body,
                self._json_dumps(proposal.manifest), self._json_dumps(proposal.source_output_ids), proposal.rationale,
                proposal.status.value, self._json_dumps(proposal.package_audit), self._json_dumps(proposal.eval_summary),
                _iso(proposal.created_at), _iso(proposal.updated_at),
            ),
        )
        self._commit()
        return self.get_method_proposal(proposal.project_id, proposal.id) or {}

    def get_method_proposal(self, project_id: str, proposal_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_method_proposals WHERE project_id=? AND id=?", (project_id, proposal_id)
        ).fetchone()
        return self._decode_growth(row, ("manifest_json", "source_output_ids_json", "package_audit_json", "eval_summary_json"))

    def list_method_proposals(
        self, project_id: str, status: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_method_proposals WHERE project_id=?"
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(limit)
        rows = self._execute(query, tuple(params)).fetchall()
        return [
            self._decode_growth(row, ("manifest_json", "source_output_ids_json", "package_audit_json", "eval_summary_json")) or {}
            for row in rows
        ]

    def update_method_proposal_package_audit(
        self, project_id: str, proposal_id: str, audit: dict[str, Any]
    ) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_method_proposals SET package_audit_json=?,updated_at=? WHERE project_id=? AND id=?",
            (self._json_dumps(audit), self._now(), project_id, proposal_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("method proposal not found in project")
        return self.get_method_proposal(project_id, proposal_id) or {}

    def update_method_proposal_evaluation(self, project_id: str, proposal_id: str, summary: dict[str, Any], status: str) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_method_proposals SET status=?,eval_summary_json=?,updated_at=? WHERE project_id=? AND id=?",
            (status, self._json_dumps(summary), self._now(), project_id, proposal_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("method proposal not found in project")
        return self.get_method_proposal(project_id, proposal_id) or {}

    # ---- governed method-evolution experiments -------------------------

    def create_method_evolution_run(self, run: MethodEvolutionRun) -> tuple[dict[str, Any], bool]:
        """Insert one idempotent experiment and return ``(record, created)``.

        The idempotency key is scoped to a project and bound to an immutable
        input fingerprint. Retrying the same experiment is safe; reusing a
        key for different candidate material is refused rather than silently
        returning unrelated evidence.
        """
        existing = self.get_method_evolution_run_by_idempotency(
            run.project_id, run.idempotency_key
        )
        if existing:
            if str(existing.get("input_fingerprint") or "") != run.input_fingerprint:
                raise ValueError("method evolution idempotency key is bound to different input")
            return existing, False
        self._execute(
            "INSERT INTO knowledge_method_evolution_runs "
            "(id,project_id,method_id,baseline_revision_id,mutation_dimension,rationale,"
            "supporting_output_ids_json,candidate_proposal_id,input_fingerprint,evaluation_summary_json,"
            "decision,rollback_revision_id,status,idempotency_key,actor_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,idempotency_key) DO NOTHING",
            (
                run.id,
                run.project_id,
                run.method_id,
                run.baseline_revision_id,
                run.mutation_dimension,
                run.rationale,
                self._json_dumps(run.supporting_output_ids),
                run.candidate_proposal_id,
                run.input_fingerprint,
                self._json_dumps(run.evaluation_summary),
                run.decision.value,
                run.rollback_revision_id,
                run.status.value,
                run.idempotency_key,
                run.actor_id,
                _iso(run.created_at),
                _iso(run.updated_at),
            ),
        )
        self._commit()
        persisted = self.get_method_evolution_run_by_idempotency(
            run.project_id, run.idempotency_key
        )
        if not persisted:
            raise RuntimeError("method evolution run was not persisted")
        if str(persisted.get("input_fingerprint") or "") != run.input_fingerprint:
            raise ValueError("method evolution idempotency key is bound to different input")
        return persisted, str(persisted.get("id") or "") == run.id

    def get_method_evolution_run(
        self, project_id: str, experiment_id: str
    ) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_method_evolution_runs WHERE project_id=? AND id=?",
            (project_id, experiment_id),
        ).fetchone()
        return self._decode_growth(
            row,
            ("supporting_output_ids_json", "evaluation_summary_json"),
        )

    def get_method_evolution_run_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_method_evolution_runs WHERE project_id=? AND idempotency_key=?",
            (project_id, idempotency_key),
        ).fetchone()
        return self._decode_growth(
            row,
            ("supporting_output_ids_json", "evaluation_summary_json"),
        )

    def list_method_evolution_runs(
        self,
        project_id: str,
        *,
        method_id: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_method_evolution_runs WHERE project_id=?"
        if method_id:
            query += " AND method_id=?"
            params.append(method_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [
            self._decode_growth(
                row, ("supporting_output_ids_json", "evaluation_summary_json")
            )
            or {}
            for row in rows
        ]

    def update_method_evolution_run(
        self,
        project_id: str,
        experiment_id: str,
        *,
        evaluation_summary: dict[str, Any],
        decision: str,
        status: str,
    ) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_method_evolution_runs "
            "SET evaluation_summary_json=?,decision=?,status=?,updated_at=? "
            "WHERE project_id=? AND id=?",
            (
                self._json_dumps(evaluation_summary),
                decision,
                status,
                self._now(),
                project_id,
                experiment_id,
            ),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("method evolution run not found in project")
        return self.get_method_evolution_run(project_id, experiment_id) or {}

    def latest_method_version(self, project_id: str, method_id: str) -> int:
        row = self._execute(
            "SELECT COALESCE(MAX(version),0) AS version FROM knowledge_method_revisions WHERE project_id=? AND method_id=?",
            (project_id, method_id),
        ).fetchone()
        return int(row["version"] if row else 0)

    def publish_method_revision(self, project_id: str, method_id: str, revision_id: str) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_methods SET status='published',active_revision_id=?,updated_at=? WHERE project_id=? AND id=?",
            (revision_id, self._now(), project_id, method_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("method not found in project")
        return self.get_method(project_id, method_id) or {}

    def deprecate_method(
        self,
        project_id: str,
        method_id: str,
        *,
        actor_id: str,
        reason: str,
        expected_active_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically transition a published method to deprecated and audit it."""
        actor_id = actor_id.strip()
        reason = reason.strip()
        if not actor_id:
            raise ValueError("actor_id is required")
        if not reason:
            raise ValueError("deprecation reason is required")

        backend = self._begin_lifecycle_transaction(
            f"{project_id}|method|{method_id}|deprecate"
        )
        try:
            row = self._execute(
                "SELECT * FROM knowledge_methods WHERE project_id=? AND id=?",
                (project_id, method_id),
            ).fetchone()
            method = self._decode_growth(
                row, ("applicability_json", "exclusions_json")
            )
            if not method:
                raise KeyError("method not found in project")
            active_revision_id = str(method.get("active_revision_id") or "")
            if (
                expected_active_revision_id is not None
                and active_revision_id != expected_active_revision_id
            ):
                raise LifecycleConflictError(
                    "method active revision conflict during deprecation"
                )
            if method.get("status") == MethodStatus.DEPRECATED.value:
                self._commit()
                return method
            if method.get("status") != MethodStatus.PUBLISHED.value:
                raise LifecycleConflictError(
                    "method lifecycle conflict: only published to deprecated is allowed"
                )

            now = self._now()
            cursor = self._execute(
                "UPDATE knowledge_methods SET status=?,updated_at=? "
                "WHERE project_id=? AND id=? AND status=? AND active_revision_id=?",
                (
                    MethodStatus.DEPRECATED.value,
                    now,
                    project_id,
                    method_id,
                    MethodStatus.PUBLISHED.value,
                    active_revision_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleConflictError(
                    "method lifecycle conflict during deprecation"
                )
            self._record_lifecycle_audit(
                project_id=project_id,
                target_type="method",
                target_id=method_id,
                action="deprecate",
                event_type="knowledge.method.deprecated",
                actor_id=actor_id,
                reason=reason,
                from_status=MethodStatus.PUBLISHED.value,
                to_status=MethodStatus.DEPRECATED.value,
                expected={"active_revision_id": expected_active_revision_id},
                now=now,
            )
            self._commit()
        except Exception:
            backend.rollback()
            raise
        return self.get_method(project_id, method_id) or {}

    # ---- outputs, evaluation and feedback -------------------------------

    def register_output(self, output: OutputAsset) -> dict[str, Any]:
        existing = self._execute(
            "SELECT * FROM knowledge_outputs WHERE project_id=? AND idempotency_key=?",
            (output.project_id, output.idempotency_key),
        ).fetchone()
        if existing:
            row = self._row_to_dict(existing)
            if row.get("content_hash") != output.content_hash:
                raise ValueError("output idempotency key is already bound to another content hash")
            return self._decode_growth(existing, ("source_refs_json", "page_refs_json", "quality_json", "metadata_json")) or {}
        references = [
            *(('source', source_id) for source_id in output.source_refs),
            *(('page', page_id) for page_id in output.page_refs),
        ]
        if output.method_revision_id:
            references.append(("method_revision", output.method_revision_id))
        for endpoint_type, endpoint_id in references:
            if not self._endpoint_exists(output.project_id, endpoint_type, endpoint_id):
                raise LineageConflictError(
                    f"{endpoint_type} reference is missing or belongs to another project"
                )
        try:
            self._execute(
                "INSERT INTO knowledge_outputs "
                "(id,project_id,kind,title,mime_type,content_hash,vault_path,run_id,method_revision_id,context_revision,source_refs_json,page_refs_json,idempotency_key,status,quality_json,metadata_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    output.id, output.project_id, output.kind, output.title, output.mime_type, output.content_hash,
                    output.vault_path, output.run_id, output.method_revision_id, output.context_revision,
                    self._json_dumps(output.source_refs), self._json_dumps(output.page_refs), output.idempotency_key,
                    output.status.value, self._json_dumps(output.quality), self._json_dumps(output.metadata),
                    _iso(output.created_at), _iso(output.updated_at),
                ),
            )
            self._commit()
            for source_id in output.source_refs:
                self.add_lineage_edge(KnowledgeLineageEdge(project_id=output.project_id, from_type="source", from_id=source_id, to_type="output", to_id=output.id, relation="output_used_source"))
            for page_id in output.page_refs:
                self.add_lineage_edge(KnowledgeLineageEdge(project_id=output.project_id, from_type="page", from_id=page_id, to_type="output", to_id=output.id, relation="output_used_page"))
            if output.method_revision_id:
                self.add_lineage_edge(KnowledgeLineageEdge(project_id=output.project_id, from_type="method_revision", from_id=output.method_revision_id, to_type="output", to_id=output.id, relation="output_used_method_revision"))
            if output.run_id and self._endpoint_exists(output.project_id, "run", output.run_id):
                self.add_lineage_edge(KnowledgeLineageEdge(project_id=output.project_id, from_type="run", from_id=output.run_id, to_type="output", to_id=output.id, relation="output_produced_by_run"))
        except Exception:
            self._execute(
                "DELETE FROM knowledge_graph_edges WHERE project_id=? AND (from_id=? OR to_id=?)",
                (output.project_id, output.id, output.id),
            )
            self._execute(
                "DELETE FROM knowledge_outputs WHERE project_id=? AND id=?",
                (output.project_id, output.id),
            )
            self._commit()
            raise
        return self.get_output(output.project_id, output.id) or {}

    def get_output(self, project_id: str, output_id: str) -> dict[str, Any] | None:
        row = self._execute("SELECT * FROM knowledge_outputs WHERE project_id=? AND id=?", (project_id, output_id)).fetchone()
        return self._decode_growth(row, ("source_refs_json", "page_refs_json", "quality_json", "metadata_json"))

    def list_outputs(self, project_id: str, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_outputs WHERE project_id=?"
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row, ("source_refs_json", "page_refs_json", "quality_json", "metadata_json")) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def list_output_evidence_references(self, project_id: str, output_id: str) -> dict[str, list[str]]:
        """Return registration references plus separately attached review evidence."""
        output = self.get_output(project_id, output_id)
        if not output:
            raise KeyError("output not found in project")
        source_ids = list(dict.fromkeys(str(value) for value in output.get("source_refs") or [] if str(value)))
        page_ids = list(dict.fromkeys(str(value) for value in output.get("page_refs") or [] if str(value)))
        rows = self._execute(
            "SELECT from_id,edge_type FROM knowledge_graph_edges "
            "WHERE project_id=? AND to_id=? AND edge_type IN ('output_used_source','output_used_page') "
            "ORDER BY created_at,id",
            (project_id, output_id),
        ).fetchall()
        for row in rows:
            edge = self._row_to_dict(row)
            if edge["edge_type"] == "output_used_source":
                source_ids.append(str(edge["from_id"]))
            else:
                page_ids.append(str(edge["from_id"]))
        return {
            "source_ids": list(dict.fromkeys(source_ids)),
            "page_ids": list(dict.fromkeys(page_ids)),
        }

    def attach_output_evidence_references(
        self,
        project_id: str,
        output_id: str,
        *,
        source_ids: list[str],
        page_ids: list[str],
    ) -> dict[str, Any]:
        """Attach reviewable A/B evidence before an output's first evaluation.

        Output bytes, registration provenance, and generation references stay
        immutable. This only appends graph evidence that an external Obsidian
        plugin cannot provide when it writes a standalone export.
        """
        output = self.get_output(project_id, output_id)
        if not output:
            raise KeyError("output not found in project")
        if output.get("status") != OutputStatus.REGISTERED.value:
            raise LifecycleConflictError(
                "evidence references can only be changed while the output status is registered"
            )

        sources = list(dict.fromkeys(str(value).strip() for value in source_ids if str(value).strip()))
        pages = list(dict.fromkeys(str(value).strip() for value in page_ids if str(value).strip()))
        if not sources and not pages:
            raise ValueError("at least one evidence reference is required")
        for source_id in sources:
            source = self.get_source(project_id, source_id)
            if not source:
                raise KeyError("source evidence reference is missing or belongs to another project")
            if str(source.get("source_type") or "") in {"generated_output", "output", "synthetic"}:
                raise ValueError("output evidence must reference external A-layer sources")
            if str(source.get("status") or "") not in {"eligible", "processed"}:
                raise ValueError("output evidence source must be eligible or processed")
        for page_id in pages:
            if not self.get_page(project_id, page_id):
                raise KeyError("page evidence reference is missing or belongs to another project")

        references = [
            *(('source', source_id, "output_used_source") for source_id in sources),
            *(('page', page_id, "output_used_page") for page_id in pages),
        ]
        backend = self._begin_lifecycle_transaction(f"{project_id}:output:{output_id}:evidence")
        try:
            current = self.get_output(project_id, output_id)
            if not current or current.get("status") != OutputStatus.REGISTERED.value:
                raise LifecycleConflictError(
                    "evidence references could not be attached because the output status changed"
                )
            existing = self.list_output_evidence_references(project_id, output_id)
            if len(set(existing["source_ids"]) | set(sources)) + len(set(existing["page_ids"]) | set(pages)) > 100:
                raise ValueError("evidence references exceed the maximum of 100")
            for endpoint_type, endpoint_id, relation in references:
                duplicate = self._execute(
                    "SELECT 1 FROM knowledge_graph_edges WHERE project_id=? AND from_id=? AND to_id=? AND edge_type=? LIMIT 1",
                    (project_id, endpoint_id, output_id, relation),
                ).fetchone()
                if duplicate:
                    continue
                if self._would_cycle(project_id, endpoint_id, output_id):
                    raise LineageConflictError("evidence lineage would create a cycle")
                edge_id = hashlib.sha256(
                    f"{project_id}|{endpoint_type}|{endpoint_id}|{output_id}|{relation}".encode()
                ).hexdigest()[:24]
                self._execute(
                    "INSERT INTO knowledge_graph_edges "
                    "(id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                    (
                        edge_id,
                        project_id,
                        endpoint_id,
                        output_id,
                        relation,
                        self._json_dumps({"attached_during": "output_review"}),
                        "output-evidence-v1",
                        self._now(),
                    ),
                )
            self._commit()
        except Exception:
            backend.rollback()
            raise
        return self.get_output(project_id, output_id) or {}

    def file_output(
        self,
        project_id: str,
        output_id: str,
        *,
        actor_id: str,
        reason: str,
        expected_status: OutputStatus | str | None = None,
    ) -> dict[str, Any]:
        """Atomically transition an accepted output to filed and audit it."""
        actor_id = actor_id.strip()
        reason = reason.strip()
        if not actor_id:
            raise ValueError("actor_id is required")
        if not reason:
            raise ValueError("filing reason is required")
        expected = (
            expected_status.value
            if isinstance(expected_status, OutputStatus)
            else str(expected_status or "")
        )

        backend = self._begin_lifecycle_transaction(
            f"{project_id}|output|{output_id}|file"
        )
        try:
            row = self._execute(
                "SELECT * FROM knowledge_outputs WHERE project_id=? AND id=?",
                (project_id, output_id),
            ).fetchone()
            output = self._decode_growth(
                row,
                (
                    "source_refs_json",
                    "page_refs_json",
                    "quality_json",
                    "metadata_json",
                ),
            )
            if not output:
                raise KeyError("output not found in project")
            current_status = str(output.get("status") or "")
            if current_status == OutputStatus.FILED.value:
                self._commit()
                return output
            if expected and current_status != expected:
                raise LifecycleConflictError(
                    f"output status conflict: expected {expected}, current {current_status}"
                )
            if current_status != OutputStatus.ACCEPTED.value:
                raise LifecycleConflictError(
                    "output lifecycle conflict: only accepted to filed is allowed"
                )

            now = self._now()
            cursor = self._execute(
                "UPDATE knowledge_outputs SET status=?,updated_at=? "
                "WHERE project_id=? AND id=? AND status=?",
                (
                    OutputStatus.FILED.value,
                    now,
                    project_id,
                    output_id,
                    OutputStatus.ACCEPTED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleConflictError("output lifecycle conflict during filing")
            self._record_lifecycle_audit(
                project_id=project_id,
                target_type="output",
                target_id=output_id,
                action="file",
                event_type="knowledge.output.filed",
                actor_id=actor_id,
                reason=reason,
                from_status=OutputStatus.ACCEPTED.value,
                to_status=OutputStatus.FILED.value,
                expected={"status": expected or None},
                now=now,
            )
            self._commit()
        except Exception:
            backend.rollback()
            raise
        return self.get_output(project_id, output_id) or {}

    def save_output_evaluation(self, evaluation: OutputEvaluation) -> dict[str, Any]:
        if not self.get_output(evaluation.project_id, evaluation.output_id):
            raise KeyError("output not found in project")
        self._execute(
            "INSERT INTO knowledge_output_evaluations "
            "(id,project_id,output_id,groundedness,task_fit,usefulness,coherence,format_quality,quality,status,evaluator_revision,findings_json,latency_ms,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(project_id,output_id,evaluator_revision) DO UPDATE SET quality=excluded.quality,status=excluded.status,findings_json=excluded.findings_json,latency_ms=excluded.latency_ms",
            (
                evaluation.id, evaluation.project_id, evaluation.output_id, evaluation.groundedness, evaluation.task_fit,
                evaluation.usefulness, evaluation.coherence, evaluation.format_quality, evaluation.quality,
                evaluation.status, evaluation.evaluator_revision, self._json_dumps(evaluation.findings), evaluation.latency_ms, _iso(evaluation.created_at),
            ),
        )
        output_status = "accepted" if evaluation.quality >= 85 else "rejected" if evaluation.quality < 60 else "evaluating"
        self._execute(
            "UPDATE knowledge_outputs SET status=?,quality_json=?,updated_at=? WHERE project_id=? AND id=?",
            (output_status, self._json_dumps(evaluation.model_dump(mode="json")), self._now(), evaluation.project_id, evaluation.output_id),
        )
        self._commit()
        return self._decode_growth(
            self._execute("SELECT * FROM knowledge_output_evaluations WHERE project_id=? AND output_id=? AND evaluator_revision=?", (evaluation.project_id, evaluation.output_id, evaluation.evaluator_revision)).fetchone(),
            ("findings_json",),
        ) or {}

    def list_output_evaluations(self, project_id: str, output_id: str = "", limit: int = 500) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_output_evaluations WHERE project_id=?"
        if output_id:
            query += " AND output_id=?"
            params.append(output_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row, ("findings_json",)) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def add_output_feedback(self, feedback: OutputFeedback) -> dict[str, Any]:
        if not self.get_output(feedback.project_id, feedback.output_id):
            raise KeyError("output not found in project")
        self._execute(
            "INSERT INTO knowledge_output_feedback "
            "(id,project_id,output_id,feedback_type,actor_id,rating,correction,comment,status,processed_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                feedback.id, feedback.project_id, feedback.output_id, feedback.feedback_type.value, feedback.actor_id,
                feedback.rating, feedback.correction, feedback.comment, feedback.status.value, _iso(feedback.processed_at), _iso(feedback.created_at),
            ),
        )
        self._commit()
        return self._decode_growth(self._execute("SELECT * FROM knowledge_output_feedback WHERE id=?", (feedback.id,)).fetchone()) or {}

    def list_feedback(self, project_id: str, output_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_output_feedback WHERE project_id=?"
        if output_id:
            query += " AND output_id=?"
            params.append(output_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def get_feedback(self, project_id: str, feedback_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_output_feedback WHERE project_id=? AND id=?",
            (project_id, feedback_id),
        ).fetchone()
        return self._decode_growth(row)

    def mark_feedback_processed(self, project_id: str, feedback_id: str, processed_ref: str) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_output_feedback SET status='processed',processed_at=?,processed_ref=? WHERE project_id=? AND id=?",
            (self._now(), processed_ref, project_id, feedback_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("feedback not found in project")
        return self.get_feedback(project_id, feedback_id) or {}

    def upsert_eval_case(self, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict[str, Any]:
        return super().upsert_eval_case(project_id, case_id, case_type, expected)

    # ---- diagnosed knowledge failures ---------------------------------

    def create_failure_record(self, failure: KnowledgeFailureRecord) -> dict[str, Any]:
        """Persist a failure without allowing a cross-project run/event reference."""
        if failure.run_id:
            run = self.get_run(failure.project_id, failure.run_id)
            if not run:
                raise KeyError("failure run is missing or belongs to another project")
        if failure.event_sequence is not None:
            event = self._execute(
                "SELECT 1 FROM knowledge_run_events WHERE project_id=? AND run_id=? AND sequence=?",
                (failure.project_id, failure.run_id, failure.event_sequence),
            ).fetchone()
            if not event:
                raise KeyError("failure event is missing or belongs to another project")
        self._execute(
            "INSERT INTO knowledge_failure_records "
            "(id,project_id,code,diagnostic_pattern,secondary_diagnostic_patterns_json,severity,summary,run_id,event_sequence,evidence_refs_json,root_cause,minimal_structural_fix,retryable,status,resolution_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                failure.id, failure.project_id, failure.code.value, failure.diagnostic_pattern.value,
                self._json_dumps([item.value for item in failure.secondary_diagnostic_patterns]), failure.severity,
                failure.summary, failure.run_id, failure.event_sequence,
                self._json_dumps(failure.evidence_refs), failure.root_cause, failure.minimal_structural_fix,
                1 if failure.retryable else 0, failure.status.value,
                self._json_dumps(failure.resolution), _iso(failure.created_at), _iso(failure.updated_at),
            ),
        )
        self._commit()
        return self.get_failure_record(failure.project_id, failure.id) or {}

    def get_failure_record(self, project_id: str, failure_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_failure_records WHERE project_id=? AND id=?",
            (project_id, failure_id),
        ).fetchone()
        return self._decode_growth(row, ("evidence_refs_json", "secondary_diagnostic_patterns_json", "resolution_json"))

    def list_failure_records(
        self,
        project_id: str,
        *,
        status: str = "",
        run_id: str = "",
        diagnostic_pattern: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_failure_records WHERE project_id=?"
        if status:
            query += " AND status=?"
            params.append(status)
        if run_id:
            query += " AND run_id=?"
            params.append(run_id)
        if diagnostic_pattern:
            query += " AND diagnostic_pattern=?"
            params.append(diagnostic_pattern)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = self._execute(query, tuple(params)).fetchall()
        return [
            self._decode_growth(row, ("evidence_refs_json", "secondary_diagnostic_patterns_json", "resolution_json")) or {}
            for row in rows
        ]

    def resolve_failure_record(
        self,
        project_id: str,
        failure_id: str,
        *,
        actor_id: str,
        resolution_note: str,
        retry_scheduled: bool = False,
    ) -> dict[str, Any]:
        """Close or schedule a retry while retaining the original diagnostic evidence."""
        actor = actor_id.strip()
        note = resolution_note.strip()
        if not actor:
            raise ValueError("actor_id is required to resolve a failure")
        if not note:
            raise ValueError("resolution_note is required")
        current = self.get_failure_record(project_id, failure_id)
        if not current:
            raise KeyError("failure record not found in project")
        if current.get("status") == KnowledgeFailureStatus.RESOLVED.value:
            return current
        now = self._now()
        status = (
            KnowledgeFailureStatus.RETRY_SCHEDULED.value
            if retry_scheduled
            else KnowledgeFailureStatus.RESOLVED.value
        )
        resolution = {
            "actor_id": actor,
            "note": note,
            "resolved_at": now,
            "retry_scheduled": retry_scheduled,
        }
        cursor = self._execute(
            "UPDATE knowledge_failure_records SET status=?,resolution_json=?,updated_at=? "
            "WHERE project_id=? AND id=? AND status<>?",
            (
                status, self._json_dumps(resolution), now, project_id, failure_id,
                KnowledgeFailureStatus.RESOLVED.value,
            ),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise LifecycleConflictError("failure lifecycle conflict during resolution")
        return self.get_failure_record(project_id, failure_id) or {}

    # ---- authoritative lineage -----------------------------------------

    _RELATIONS = {
        "source_supports_page", "source_contradicts_source", "page_informs_method",
        "source_distills_method_proposal",
        "source_extracts_candidate", "run_produces_candidate", "candidate_guides_method_proposal",
        "output_used_source", "output_used_page", "output_used_method_revision",
        "output_produced_by_run", "feedback_evaluates_output", "output_proposes_page",
        "output_proposes_method", "method_supersedes_method",
        "method_revision_baselines_method_proposal",
        "output_supports_method_proposal", "run_evaluates_method_proposal",
    }

    def _endpoint_exists(self, project_id: str, endpoint_type: str, endpoint_id: str) -> bool:
        tables = {
            "source": "knowledge_sources",
            "page": "knowledge_wiki_pages",
            "method": "knowledge_methods",
            "method_revision": "knowledge_method_revisions",
            "method_proposal": "knowledge_method_proposals",
            "candidate": "knowledge_candidates",
            "output": "knowledge_outputs",
            "feedback": "knowledge_output_feedback",
            "run": "knowledge_runs",
            "proposal": "knowledge_proposals",
        }
        table = tables.get(endpoint_type)
        if not table:
            return False
        row = self._execute(f"SELECT 1 FROM {table} WHERE project_id=? AND id=? LIMIT 1", (project_id, endpoint_id)).fetchone()
        return bool(row)

    def _begin_lifecycle_transaction(self, lock_key: str):
        backend = self._get_connection()
        dialect = getattr(backend, "dialect", "sqlite")
        if dialect == "postgresql":
            self._execute("SELECT pg_advisory_xact_lock(hashtext(?))", (lock_key,))
        else:
            self._execute("BEGIN IMMEDIATE")
        return backend

    def _record_lifecycle_audit(
        self,
        *,
        project_id: str,
        target_type: str,
        target_id: str,
        action: str,
        event_type: str,
        actor_id: str,
        reason: str,
        from_status: str,
        to_status: str,
        expected: dict[str, Any],
        now: str,
    ) -> None:
        identity = f"{project_id}|{target_type}|{target_id}|{action}"
        run_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        event_id = hashlib.sha256(f"{identity}|event|1".encode("utf-8")).hexdigest()[:24]
        input_refs = {
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "from_status": from_status,
            "expected": expected,
        }
        output_refs = {
            "target_type": target_type,
            "target_id": target_id,
            "status": to_status,
        }
        self._execute(
            "INSERT INTO knowledge_runs "
            "(id,project_id,run_type,trigger,status,actor_id,input_refs_json,output_refs_json,error,retry_of,started_at,completed_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                run_id,
                project_id,
                f"{target_type}_{action}",
                "lifecycle",
                "completed",
                actor_id,
                self._json_dumps(input_refs),
                self._json_dumps(output_refs),
                "",
                None,
                now,
                now,
                now,
                now,
            ),
        )
        self._execute(
            "INSERT INTO knowledge_run_events "
            "(id,project_id,run_id,sequence,event_type,payload_json,created_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                event_id,
                project_id,
                run_id,
                1,
                event_type,
                self._json_dumps(
                    {
                        "target_type": target_type,
                        "target_id": target_id,
                        "action": action,
                        "actor_id": actor_id,
                        "reason": reason,
                        "from_status": from_status,
                        "to_status": to_status,
                        "expected": expected,
                    }
                ),
                now,
            ),
        )

    def _would_cycle(self, project_id: str, from_id: str, to_id: str) -> bool:
        if from_id == to_id:
            return True
        rows = self._execute("SELECT from_id,to_id FROM knowledge_graph_edges WHERE project_id=?", (project_id,)).fetchall()
        adjacency: dict[str, set[str]] = {}
        for row in rows:
            adjacency.setdefault(str(row["from_id"]), set()).add(str(row["to_id"]))
        frontier = [to_id]
        visited: set[str] = set()
        while frontier:
            current = frontier.pop()
            if current in visited:
                continue
            if current == from_id:
                return True
            visited.add(current)
            frontier.extend(adjacency.get(current, ()))
        return False

    def add_lineage_edge(self, edge: KnowledgeLineageEdge) -> dict[str, Any]:
        if edge.relation not in self._RELATIONS:
            raise LineageConflictError("unsupported lineage relation")
        if edge.relation == "candidate_guides_method_proposal" and (
            edge.from_type != "candidate" or edge.to_type != "method_proposal"
        ):
            raise LineageConflictError("candidate guidance must connect a candidate to a method proposal")
        if not self._endpoint_exists(edge.project_id, edge.from_type, edge.from_id) or not self._endpoint_exists(edge.project_id, edge.to_type, edge.to_id):
            raise LineageConflictError("lineage endpoint is missing or belongs to another project")
        duplicate = self._execute(
            "SELECT * FROM knowledge_graph_edges WHERE project_id=? AND from_id=? AND to_id=? AND edge_type=?",
            (edge.project_id, edge.from_id, edge.to_id, edge.relation),
        ).fetchone()
        if duplicate:
            return self._decode_growth(duplicate, ("metadata_json",)) or {}
        if self._would_cycle(edge.project_id, edge.from_id, edge.to_id):
            raise LineageConflictError("lineage edge would create a cycle")
        self._execute(
            "INSERT INTO knowledge_graph_edges (id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (edge.id, edge.project_id, edge.from_id, edge.to_id, edge.relation, self._json_dumps(edge.metadata), edge.revision, _iso(edge.created_at)),
        )
        self._commit()
        return self._decode_growth(self._execute("SELECT * FROM knowledge_graph_edges WHERE id=?", (edge.id,)).fetchone(), ("metadata_json",)) or {}

    def list_lineage(self, project_id: str, relation: str = "", limit: int = 500) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_graph_edges WHERE project_id=?"
        if relation:
            query += " AND edge_type=?"
            params.append(relation)
        query += " ORDER BY created_at,id LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row, ("metadata_json",)) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def lineage_endpoints(
        self, project_id: str, endpoint_ids: list[str] | set[str]
    ) -> dict[str, dict[str, str]]:
        """Resolve bounded, non-body endpoint projections for graph clients."""
        remaining = {str(value) for value in endpoint_ids if str(value)}
        resolved: dict[str, dict[str, str]] = {}
        endpoints = (
            (
                "source",
                "SELECT id,source_type,origin,vault_path,status,metadata_json "
                "FROM knowledge_sources WHERE project_id=? AND id IN ({placeholders})",
                ("metadata_json",),
            ),
            (
                "page",
                "SELECT id,title,path,status FROM knowledge_wiki_pages "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "method",
                "SELECT id,name,slug,status FROM knowledge_methods "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "method_revision",
                "SELECT revision.id,revision.version,revision.status,method.name AS method_name,method.slug AS method_slug "
                "FROM knowledge_method_revisions AS revision "
                "LEFT JOIN knowledge_methods AS method ON method.id=revision.method_id AND method.project_id=revision.project_id "
                "WHERE revision.project_id=? AND revision.id IN ({placeholders})",
                (),
            ),
            (
                "method_proposal",
                "SELECT id,operation,rationale,status FROM knowledge_method_proposals "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "candidate",
                "SELECT id,candidate_type,title,claim,status FROM knowledge_candidates "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "output",
                "SELECT id,title,kind,vault_path,status FROM knowledge_outputs "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "feedback",
                "SELECT id,feedback_type,status,correction,comment FROM knowledge_output_feedback "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "run",
                "SELECT id,run_type,status FROM knowledge_runs "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
            (
                "proposal",
                "SELECT id,rationale,status FROM knowledge_proposals "
                "WHERE project_id=? AND id IN ({placeholders})",
                (),
            ),
        )
        for endpoint_type, query, json_fields in endpoints:
            candidates = sorted(remaining)
            for offset in range(0, len(candidates), 400):
                chunk = candidates[offset : offset + 400]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                rows = self._execute(
                    query.format(placeholders=placeholders),
                    (project_id, *chunk),
                ).fetchall()
                for row in rows:
                    record = self._decode_growth(row, json_fields) or {}
                    endpoint_id = str(record.get("id") or "")
                    if not endpoint_id:
                        continue
                    label = self._lineage_endpoint_label(endpoint_type, record)
                    resolved[endpoint_id] = {
                        "id": endpoint_id,
                        "type": endpoint_type,
                        "label": label,
                        "status": str(record.get("status") or "recorded"),
                    }
                    remaining.discard(endpoint_id)
            if not remaining:
                break
        return resolved

    @staticmethod
    def _lineage_endpoint_label(endpoint_type: str, record: dict[str, Any]) -> str:
        if endpoint_type == "source":
            return _source_lineage_label(record)
        if endpoint_type == "page":
            return _bounded_lineage_label(record.get("title") or record.get("path"), "Published Wiki page")
        if endpoint_type == "method":
            return _bounded_lineage_label(record.get("name") or record.get("slug"), "Method")
        if endpoint_type == "method_revision":
            method = record.get("method_name") or record.get("method_slug") or "Method"
            version = record.get("version")
            return _bounded_lineage_label(f"{method} v{version}" if version else method, "Method revision")
        if endpoint_type == "method_proposal":
            return _bounded_lineage_label(record.get("rationale") or record.get("operation"), "Method proposal")
        if endpoint_type == "candidate":
            prefix = str(record.get("candidate_type") or "candidate").replace("_", " ")
            return _bounded_lineage_label(f"{prefix}: {record.get('title') or record.get('claim')}", "Knowledge candidate")
        if endpoint_type == "output":
            return _bounded_lineage_label(record.get("title") or record.get("vault_path") or record.get("kind"), "Output")
        if endpoint_type == "feedback":
            return _bounded_lineage_label(record.get("feedback_type"), "Feedback")
        if endpoint_type == "run":
            return _bounded_lineage_label(record.get("run_type"), "Knowledge run")
        if endpoint_type == "proposal":
            return _bounded_lineage_label(record.get("rationale"), "Wiki proposal")
        return "Recorded knowledge asset"

    def lineage_endpoint_types(
        self, project_id: str, endpoint_ids: list[str] | set[str]
    ) -> dict[str, str]:
        """Compatibility projection for callers that only need endpoint types."""
        return {
            endpoint_id: endpoint["type"]
            for endpoint_id, endpoint in self.lineage_endpoints(project_id, endpoint_ids).items()
        }

    # ---- dual-track distillation ---------------------------------------

    def get_growth_distillation(self, project_id: str, kind: str, period: str, input_hash: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_growth_distillations WHERE project_id=? AND kind=? AND period=? AND input_hash=?",
            (project_id, kind, period, input_hash),
        ).fetchone()
        return self._decode_growth(row, ("paths_json", "manifest_json"))

    def record_growth_distillation(self, *, project_id: str, period: str, kind: str, input_hash: str, paths: list[str], manifest: dict[str, Any], status: str = "generated") -> dict[str, Any]:
        row_id = hashlib.sha256(f"{project_id}|{kind}|{period}|{input_hash}".encode()).hexdigest()[:24]
        self._execute(
            "INSERT INTO knowledge_growth_distillations (id,project_id,period,kind,input_hash,paths_json,manifest_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,kind,period,input_hash) DO NOTHING",
            (row_id, project_id, period, kind, input_hash, self._json_dumps(paths), self._json_dumps(manifest), status, self._now()),
        )
        self._commit()
        return self._decode_growth(self._execute("SELECT * FROM knowledge_growth_distillations WHERE id=?", (row_id,)).fetchone(), ("paths_json", "manifest_json")) or {}

    def list_growth_distillations(self, project_id: str, kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: list[Any] = [project_id]
        query = "SELECT * FROM knowledge_growth_distillations WHERE project_id=?"
        if kind:
            query += " AND kind=?"
            params.append(kind)
        query += " ORDER BY period DESC,created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [self._decode_growth(row, ("paths_json", "manifest_json")) or {} for row in self._execute(query, tuple(params)).fetchall()]

    def get_growth_distillation_by_id(self, project_id: str, distillation_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_growth_distillations WHERE project_id=? AND id=?",
            (project_id, distillation_id),
        ).fetchone()
        return self._decode_growth(row, ("paths_json", "manifest_json"))
