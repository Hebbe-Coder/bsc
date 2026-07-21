from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_command_service_creates_lints_and_publishes_only_through_project_vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    project_root = vault_root / "clients" / "acme"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands.db"))
    repo.configure_vault("project-a", "clients/acme")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="brief.md",
            raw_content="Approval is mandatory.", trust_level="trusted",
        )
    ).source
    service = WikiCommandService(repo)
    try:
        proposal = service.create_proposal(
            {
                "project_id": "project-a",
                "source_ids": [source["id"]],
                "rationale": "Record the confirmed approval requirement.",
                "operations": [
                    {
                        "operation": "create", "path": "wiki/concepts/approval.md",
                        "content": "---\ntitle: Approval\nkind: concept\n---\nApproval is mandatory. [source:%s]" % source["id"],
                        "source_ids": [source["id"]],
                    },
                    {
                        "operation": "append", "path": "wiki/index.md",
                        "content": "\n- [[wiki/concepts/approval.md]]\n", "source_ids": [source["id"]],
                    },
                    {
                        "operation": "append", "path": "wiki/log.md",
                        "content": "\n- Approval added. [source:%s]\n" % source["id"], "source_ids": [source["id"]],
                    },
                ],
            }
        )
        assert not (project_root / "wiki").exists()
        assert service.lint_proposal(project_id="project-a", proposal_id=proposal["id"])["valid"] is True

        service.save_eval_case(
            project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]}
        )
        result = service.publish_proposal(project_id="project-a", proposal_id=proposal["id"])

        assert result["status"] == "published"
        assert (project_root / "wiki" / "concepts" / "approval.md").is_file()
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
        pages = repo.list_pages("project-a")
        approval = next(page for page in pages if page["path"] == "wiki/concepts/approval.md")
        assert repo.list_page_revisions("project-a", approval["id"])[0]["proposal_id"] == proposal["id"]
        assert repo.list_citations("project-a", approval["id"])[0]["source_id"] == source["id"]
        assert any(edge["edge_type"] == "wiki_cites_source" for edge in repo.list_graph_edges("project-a"))
        assert not (vault_root / "wiki").exists()
        assert not (vault_root / "projects" / "project-a").exists()
    finally:
        repo.close()


def test_command_service_runs_manual_source_sync_without_a_celery_scheduler(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "note.md").write_text("# User Note\nA source fact.", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "command-sync.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    try:
        result = WikiCommandService(repo).start_run(project_id="project-a", job_type="source_sync", trigger="http")

        assert result["status"] == "completed"
        assert result["execution"] == "synchronous"
        assert repo.list_sources("project-a")[0]["origin"] == "note.md"
    finally:
        repo.close()
