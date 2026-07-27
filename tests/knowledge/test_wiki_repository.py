from app.knowledge.wiki_contracts import (
    KnowledgeRun,
    RunStatus,
    SourceRecord,
    SourceStatus,
    WikiOperation,
    WikiOperationType,
    WikiProposal,
)
from app.knowledge.wiki_repository import WikiRepository, _run_event_advisory_lock_key


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _PostgresRunEventBackend:
    dialect = "postgresql"


class _PostgresRunEventRepository:
    def __init__(self):
        self.backend = _PostgresRunEventBackend()
        self.executed = []
        self.commits = 0

    def _get_connection(self):
        return self.backend

    def _execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith("SELECT 1 FROM knowledge_runs"):
            return _Cursor({"present": 1})
        if sql.startswith("SELECT COALESCE(MAX(sequence)"):
            return _Cursor({"next_sequence": 4})
        return _Cursor(None)

    @staticmethod
    def _row_to_dict(row):
        return row

    @staticmethod
    def _json_dumps(payload):
        return str(payload)

    @staticmethod
    def _now():
        return "2026-07-26T10:00:00"

    def _commit(self):
        self.commits += 1


def test_repository_keeps_wiki_records_project_scoped(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "wiki-repository.db"))
    try:
        mapping = repo.configure_vault(
            project_id="project-a",
            vault_path="client-a/knowledge",
            actor_id="owner-a",
        )
        assert mapping["project_id"] == "project-a"
        assert mapping["vault_path"] == "client-a/knowledge"
        assert repo.get_vault("project-b") is None

        source = SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            origin="brief.md",
            content_hash="b" * 64,
            raw_content="Project A brief evidence",
            status=SourceStatus.VALIDATED,
        )
        repo.create_source(source)
        assert [row["id"] for row in repo.list_sources("project-a")] == ["source-a"]
        assert repo.list_sources("project-b") == []
        assert repo.find_source_by_content_hash("project-a", "b" * 64)["id"] == "source-a"
        assert repo.find_source_by_content_hash("project-b", "b" * 64) is None
        transitioned = repo.update_source_status("project-a", "source-a", SourceStatus.ELIGIBLE)
        assert transitioned["status"] == "eligible"

        proposal = WikiProposal(
            id="proposal-a",
            project_id="project-a",
            source_ids=["source-a"],
            operations=[
                WikiOperation(
                    operation=WikiOperationType.CREATE,
                    path="wiki/concepts/brief.md",
                    content="# Brief",
                    source_ids=["source-a"],
                )
            ],
        )
        repo.create_proposal(proposal, actor_id="owner-a")
        assert repo.get_proposal("project-a", "proposal-a")["status"] == "draft"
        assert repo.get_proposal("project-b", "proposal-a") is None

        run = KnowledgeRun(
            id="run-a",
            project_id="project-a",
            run_type="wiki_maintenance",
            trigger="manual",
            status=RunStatus.QUEUED,
        )
        repo.create_run(run)
        updated = repo.update_run_status("project-a", "run-a", RunStatus.COMPLETED)
        assert updated["status"] == "completed"
        events = repo.list_run_events(project_id="project-a", run_id="run-a")
        assert [(event["sequence"], event["event_type"]) for event in events] == [
            (1, "knowledge.run.queued"),
            (2, "knowledge.run.completed"),
        ]
        assert repo.list_run_events(project_id="project-b", run_id="run-a") == []
        assert repo.list_runs("project-b") == []
    finally:
        repo.close()


def test_postgres_run_event_append_locks_the_run_before_allocating_its_sequence():
    repo = _PostgresRunEventRepository()

    event = WikiRepository.append_run_event(
        repo,
        project_id="project-a",
        run_id="run-a",
        event_type="knowledge.run.running",
        payload={"status": "running"},
    )

    assert repo.executed[0][0] == "SELECT pg_advisory_xact_lock(?)"
    assert repo.executed[0][1][0] == _run_event_advisory_lock_key("project-a", "run-a")
    assert repo.executed[1][0].startswith("SELECT 1 FROM knowledge_runs")
    assert repo.executed[2][0].startswith("SELECT * FROM knowledge_run_events")
    assert repo.executed[3][0].startswith("SELECT COALESCE(MAX(sequence)")
    assert repo.executed[4][0].startswith("INSERT INTO knowledge_run_events")
    assert event["sequence"] == 4
    assert repo.commits == 1


def test_duplicate_run_event_is_idempotent(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "idempotent-run-event.db"))
    try:
        repo.create_run(
            KnowledgeRun(
                id="run-idempotent",
                project_id="project-a",
                run_type="source_sync",
                trigger="schedule",
            )
        )
        payload = {"schedule_id": "schedule-a", "due_at": "2026-07-26T17:00:00+08:00"}
        first = repo.append_run_event(
            project_id="project-a",
            run_id="run-idempotent",
            event_type="knowledge.run.execution_dispatched",
            payload=payload,
        )
        repeated = repo.append_run_event(
            project_id="project-a",
            run_id="run-idempotent",
            event_type="knowledge.run.execution_dispatched",
            payload=payload,
        )

        assert repeated["id"] == first["id"]
        assert repeated["sequence"] == first["sequence"] == 2
        assert [event["sequence"] for event in repo.list_run_events(project_id="project-a", run_id="run-idempotent")] == [1, 2]
    finally:
        repo.close()


def test_claim_run_execution_allows_only_the_first_executor(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "claimed-run.db"))
    try:
        run = KnowledgeRun(id="run-claim", project_id="project-a", run_type="source_sync", trigger="schedule")
        repo.create_run(run)

        assert repo.claim_run_execution(project_id="project-a", run_id=run.id) is True
        assert repo.claim_run_execution(project_id="project-a", run_id=run.id) is False
        assert repo.get_run("project-a", run.id)["status"] == "running"
        assert [event["event_type"] for event in repo.list_run_events(project_id="project-a", run_id=run.id)] == [
            "knowledge.run.queued",
            "knowledge.run.running",
        ]
    finally:
        repo.close()


def test_repository_lists_all_completed_horizon_run_ids_by_project(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "horizon-run-ledger.db"))
    try:
        imported = KnowledgeRun(
            project_id="project-a",
            run_type="horizon_capture",
            trigger="schedule",
            status=RunStatus.COMPLETED,
            output_refs={"horizon_run_id": "run-imported"},
        )
        skipped = KnowledgeRun(
            project_id="project-a",
            run_type="horizon_capture",
            trigger="schedule",
            status=RunStatus.COMPLETED,
            output_refs={"horizon_run_id": ""},
        )
        other_project = KnowledgeRun(
            project_id="project-b",
            run_type="horizon_capture",
            trigger="schedule",
            status=RunStatus.COMPLETED,
            output_refs={"horizon_run_id": "run-other-project"},
        )
        failed = KnowledgeRun(
            project_id="project-a",
            run_type="horizon_capture",
            trigger="schedule",
            status=RunStatus.FAILED,
            output_refs={"horizon_run_id": "run-failed"},
        )
        for run in (imported, skipped, other_project, failed):
            repo.create_run(run)

        assert repo.list_completed_horizon_run_ids("project-a") == {"run-imported"}
        assert repo.list_completed_horizon_run_ids("project-b") == {"run-other-project"}
    finally:
        repo.close()
import hashlib

import pytest

from app.knowledge.wiki_repository import PublicationConflictError

def test_publication_expected_hash_conflict_rolls_back_database_snapshot(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "publication-conflict.db"))
    try:
        repo.record_publication(
            project_id="project-a",
            contents={"wiki/overview.md": "# Version one\n"},
            source_ids=[],
        )
        page = repo.list_pages("project-a")[0]

        with pytest.raises(PublicationConflictError, match="wiki/overview.md"):
            repo.record_publication(
                project_id="project-a",
                contents={"wiki/overview.md": "# Version two\n"},
                source_ids=[],
                expected_content_hashes={"wiki/overview.md": hashlib.sha256(b"wrong").hexdigest()},
            )

        current = repo.get_page_content("project-a", page["id"])
        assert current["content"] == "# Version one\n"
        assert len(repo.list_page_revisions("project-a", page["id"])) == 1
    finally:
        repo.close()


def test_publication_excludes_agents_rule_examples_from_citation_and_evidence_graph(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "agents-rules-projection.db"))
    try:
        repo.record_publication(
            project_id="project-a",
            contents={
                "AGENTS.md": "# Rules\nUse `[source:<id>]` for a resolvable factual claim.\n",
                "wiki/overview.md": "# Overview\nEvidence-backed claim. [source:source-a]\n",
            },
            source_ids=[],
        )
        pages = {page["path"]: page for page in repo.list_pages("project-a")}
        agents_citations = repo.list_citations("project-a", pages["AGENTS.md"]["id"])
        graph = repo.list_graph_edges("project-a")

        assert agents_citations == []
        assert not any(
            edge["edge_type"] == "wiki_cites_source" and edge["to_id"] == "<id>"
            for edge in graph
        )
        assert any(
            edge["edge_type"] == "wiki_cites_source" and edge["to_id"] == "source-a"
            for edge in graph
        )
    finally:
        repo.close()
