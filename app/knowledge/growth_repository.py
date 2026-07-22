"""Persistence for project profiles and the governed C/D growth assets."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from app.knowledge.growth_contracts import (
    KnowledgeLineageEdge,
    MethodAsset,
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


class GrowthRepository(WikiRepository):
    """Project-scoped repository for the additive A/B/C/D domain."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        ensure_schema(self)

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
            "SELECT * FROM knowledge_source_triage WHERE project_id=? AND source_id=? AND profile_revision=?",
            (triage.project_id, triage.source_id, triage.profile_revision),
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
            "(id,project_id,method_id,operation,body,manifest_json,source_output_ids_json,rationale,status,eval_summary_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal.id, proposal.project_id, proposal.method_id, proposal.operation, proposal.body,
                self._json_dumps(proposal.manifest), self._json_dumps(proposal.source_output_ids), proposal.rationale,
                proposal.status.value, self._json_dumps(proposal.eval_summary), _iso(proposal.created_at), _iso(proposal.updated_at),
            ),
        )
        self._commit()
        return self.get_method_proposal(proposal.project_id, proposal.id) or {}

    def get_method_proposal(self, project_id: str, proposal_id: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT * FROM knowledge_method_proposals WHERE project_id=? AND id=?", (project_id, proposal_id)
        ).fetchone()
        return self._decode_growth(row, ("manifest_json", "source_output_ids_json", "eval_summary_json"))

    def update_method_proposal_evaluation(self, project_id: str, proposal_id: str, summary: dict[str, Any], status: str) -> dict[str, Any]:
        cursor = self._execute(
            "UPDATE knowledge_method_proposals SET status=?,eval_summary_json=?,updated_at=? WHERE project_id=? AND id=?",
            (status, self._json_dumps(summary), self._now(), project_id, proposal_id),
        )
        self._commit()
        if cursor.rowcount != 1:
            raise KeyError("method proposal not found in project")
        return self.get_method_proposal(project_id, proposal_id) or {}

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

    # ---- authoritative lineage -----------------------------------------

    _RELATIONS = {
        "source_supports_page", "source_contradicts_source", "page_informs_method",
        "output_used_source", "output_used_page", "output_used_method_revision",
        "output_produced_by_run", "feedback_evaluates_output", "output_proposes_page",
        "output_proposes_method", "method_supersedes_method",
    }

    def _endpoint_exists(self, project_id: str, endpoint_type: str, endpoint_id: str) -> bool:
        tables = {
            "source": "knowledge_sources",
            "page": "knowledge_wiki_pages",
            "method": "knowledge_methods",
            "method_revision": "knowledge_method_revisions",
            "method_proposal": "knowledge_method_proposals",
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

    def lineage_endpoint_types(
        self, project_id: str, endpoint_ids: list[str] | set[str]
    ) -> dict[str, str]:
        """Resolve graph endpoint types in bounded batches for transport clients."""
        remaining = {str(value) for value in endpoint_ids if str(value)}
        resolved: dict[str, str] = {}
        tables = (
            ("source", "knowledge_sources"),
            ("page", "knowledge_wiki_pages"),
            ("method", "knowledge_methods"),
            ("method_revision", "knowledge_method_revisions"),
            ("method_proposal", "knowledge_method_proposals"),
            ("output", "knowledge_outputs"),
            ("feedback", "knowledge_output_feedback"),
            ("run", "knowledge_runs"),
            ("proposal", "knowledge_proposals"),
        )
        for endpoint_type, table in tables:
            candidates = sorted(remaining)
            for offset in range(0, len(candidates), 400):
                chunk = candidates[offset : offset + 400]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                rows = self._execute(
                    f"SELECT id FROM {table} WHERE project_id=? AND id IN ({placeholders})",
                    (project_id, *chunk),
                ).fetchall()
                for row in rows:
                    endpoint_id = str(self._row_to_dict(row)["id"])
                    resolved[endpoint_id] = endpoint_type
                    remaining.discard(endpoint_id)
            if not remaining:
                break
        return resolved

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
