from app.knowledge.wiki_contracts import (
    KnowledgeRun,
    RunStatus,
    SourceRecord,
    SourceStatus,
    WikiOperation,
    WikiOperationType,
    WikiProposal,
)
from app.knowledge.wiki_repository import WikiRepository


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
