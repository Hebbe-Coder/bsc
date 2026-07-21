"""Persistence facade for the project-scoped LLM Wiki domain."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_contracts import (
    KnowledgeGraphEdge,
    KnowledgeRun,
    ProposalStatus,
    RunStatus,
    SourceRecord,
    SourceStatus,
    WikiProposal,
)
from app.repositories.base_repository import BaseRepository


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


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

    def find_source_by_content_hash(self, project_id: str, content_hash: str) -> dict | None:
        row = self._execute(
            "SELECT * FROM knowledge_sources WHERE project_id=? AND content_hash=? ORDER BY captured_at DESC, id DESC LIMIT 1",
            (project_id, content_hash),
        ).fetchone()
        return self._decode(row, ("metadata_json",))

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

    def update_source_status(self, project_id: str, source_id: str, status: SourceStatus) -> dict:
        now = self._now()
        self._execute(
            "UPDATE knowledge_sources SET status=?,updated_at=? WHERE project_id=? AND id=?",
            (status.value, now, project_id, source_id),
        )
        self._commit()
        return self.get_source(project_id, source_id) or {}

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
            return {"claimed": False, "run_id": existing[0]}
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

    def list_citations(self, project_id: str, page_id: str = "") -> list[dict]:
        if page_id:
            rows = self._execute(
                "SELECT * FROM knowledge_citations WHERE project_id=? AND wiki_page_id=? AND status='active' ORDER BY id",
                (project_id, page_id),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_citations WHERE project_id=? AND status='active' ORDER BY wiki_page_id,id", (project_id,)
            ).fetchall()
        return [self._decode(row) or {} for row in rows]

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

    def record_publication(self, *, project_id: str, proposal_id: str = "", contents: dict[str, str], source_ids: list[str]) -> None:
        """Persist a published Vault snapshot, citations, and its derived graph atomically."""
        pages = {path: content for path, content in contents.items() if path.startswith("wiki/")}
        existing = {
            page["path"]: page
            for page in [self._decode(row, ("metadata_json",)) or {} for row in self._execute(
                "SELECT * FROM knowledge_wiki_pages WHERE project_id=?", (project_id,)
            ).fetchall()]
        }
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

        backend = self._get_connection()
        try:
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
            for page in indexed_pages:
                for sequence, source_id in enumerate(self._source_ids(page["content"])):
                    citation_id = hashlib.sha256(f"{page['id']}|{source_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
                    self._execute(
                        "INSERT INTO knowledge_citations (id,project_id,wiki_page_id,source_id,anchor,claim_text,status,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (citation_id, project_id, page["id"], source_id, "", self._citation_claim(page["content"], source_id), "active", now),
                    )
            self._replace_graph_edges_in_transaction(project_id, indexed_pages, proposal_id, now)
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

    def _replace_graph_edges_in_transaction(self, project_id: str, pages: list[dict[str, Any]], proposal_id: str, now: str) -> None:
        by_path = {page["path"]: page for page in pages}
        graph_rows: dict[str, tuple[str, str, str, str]] = {}

        def add(from_id: str, to_id: str, edge_type: str) -> None:
            edge_id = hashlib.sha256(f"{project_id}|{from_id}|{to_id}|{edge_type}".encode("utf-8")).hexdigest()[:24]
            graph_rows[edge_id] = (from_id, to_id, edge_type, edge_id)

        for page in pages:
            for target in re.findall(r"\[\[([^\]]+)\]\]", page["content"]):
                target_path = target if target.endswith(".md") else f"{target}.md"
                if target_path in by_path:
                    add(page["id"], by_path[target_path]["id"], "wiki_links_to")
            for source_id in self._source_ids(page["content"]):
                add(page["id"], source_id, "wiki_cites_source")
                if page["page_kind"] == "decision":
                    add(page["id"], source_id, "decision_uses_evidence")
            if proposal_id:
                add(proposal_id, page["id"], "proposal_changes_page")
        self._execute(
            "DELETE FROM knowledge_graph_edges WHERE project_id=? AND edge_type<>?",
            (project_id, "source_supersedes_source"),
        )
        for from_id, to_id, edge_type, edge_id in graph_rows.values():
            self._execute(
                "INSERT INTO knowledge_graph_edges (id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (edge_id, project_id, from_id, to_id, edge_type, "{}", proposal_id, now),
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
    def _page_metadata(path: str, content: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if content.startswith("---\n"):
            boundary = content.find("\n---", 4)
            if boundary >= 0:
                parsed = yaml.safe_load(content[4:boundary]) or {}
                if isinstance(parsed, dict):
                    metadata = parsed
        title = str(metadata.get("title") or Path(path).stem.replace("-", " ").title())
        page_kind = str(metadata.get("kind") or ("index" if path.endswith("index.md") else "general"))
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

    def append_run_event(self, *, project_id: str, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict:
        """Append an ordered, project-scoped event that can be replayed after reconnect."""
        exists = self._execute(
            "SELECT 1 FROM knowledge_runs WHERE project_id=? AND id=?", (project_id, run_id)
        ).fetchone()
        if not exists:
            raise ValueError("knowledge run not found")
        row = self._execute(
            "SELECT COALESCE(MAX(sequence),0)+1 AS next_sequence FROM knowledge_run_events WHERE project_id=? AND run_id=?",
            (project_id, run_id),
        ).fetchone()
        sequence = int(self._row_to_dict(row)["next_sequence"])
        event_id = hashlib.sha256(f"{project_id}|{run_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
        created_at = self._now()
        self._execute(
            "INSERT INTO knowledge_run_events (id,project_id,run_id,sequence,event_type,payload_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (event_id, project_id, run_id, sequence, event_type, self._json_dumps(payload or {}), created_at),
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

    def list_graph_edges(self, project_id: str, edge_type: str | None = None) -> list[dict]:
        if edge_type:
            rows = self._execute(
                "SELECT * FROM knowledge_graph_edges WHERE project_id=? AND edge_type=? ORDER BY id",
                (project_id, edge_type),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_graph_edges WHERE project_id=? ORDER BY id", (project_id,)
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
