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
