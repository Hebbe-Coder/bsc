from datetime import datetime, timedelta, timezone

from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.proposal_gate import ProposalGate
from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun, ProposalStatus, RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_command_capture_immediately_projects_bsc_owned_source_into_obsidian(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands-projection.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        result = WikiCommandService(repo).capture_source(
            {
                "project_id": "project-a",
                "source_type": "manual_upload",
                "origin": "operator-note",
                "raw_content": "This is a real operator observation.",
                "trust_level": "reviewed",
            },
            actor_id="test",
        )
        source = result["source"]
        mirror = repo.get_run("project-a", result["run_id"])["output_refs"]["evidence_mirror"]
        target = project_root / "01_Sources" / "bsc-evidence" / f"{source['id']}.md"

        assert mirror["status"] == "completed"
        assert mirror["created"] == 1
        assert target.is_file()
        assert "This is a real operator observation." in target.read_text(encoding="utf-8")
    finally:
        repo.close()


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


def test_command_service_revises_an_overview_link_without_appending_a_duplicate(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "clients" / "acme"
    (project_root / "wiki" / "concepts").mkdir(parents=True)
    initial_page = "---\ntitle: Approval\nkind: concept\n---\nApproval is required. [source:source-a]\n"
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    (project_root / "wiki" / "concepts" / "approval.md").write_text(initial_page, encoding="utf-8")
    (project_root / "wiki" / "overview.md").write_text(
        "---\ntitle: Overview\nkind: brief\n---\n- [[wiki/concepts/approval.md]]\n", encoding="utf-8"
    )
    (project_root / "wiki" / "index.md").write_text("# Index\n- [[wiki/concepts/approval.md]]\n", encoding="utf-8")
    (project_root / "wiki" / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands-overview.db"))
    repo.configure_vault("project-a", "clients/acme")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="brief.md",
            raw_content="Approval remains mandatory.", trust_level="trusted",
        )
    ).source
    service = WikiCommandService(repo)
    try:
        proposal = service.create_proposal(
            {
                "project_id": "project-a",
                "source_ids": [source["id"]],
                "operations": [
                    {
                        "operation": "replace", "path": "wiki/concepts/approval.md",
                        "content": "---\ntitle: Approval\nkind: concept\n---\nApproval remains mandatory. [source:%s]\n" % source["id"],
                        "source_ids": [source["id"]],
                    },
                    {"operation": "append", "path": "wiki/index.md", "content": "\n- Approval revision recorded\n", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/log.md", "content": "\n- Revised approval. [source:%s]\n" % source["id"], "source_ids": [source["id"]]},
                ],
            }
        )

        assert all(operation["path"] != "wiki/overview.md" for operation in proposal["operations"])
        assert service.lint_proposal(project_id="project-a", proposal_id=proposal["id"])["valid"] is True
    finally:
        repo.close()


def test_command_service_runs_manual_source_sync_without_a_celery_scheduler(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "01_Sources" / "note.md").parent.mkdir(parents=True)
    (project_root / "01_Sources" / "note.md").write_text("# User Note\nA source fact.", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "command-sync.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    try:
        result = WikiCommandService(repo).start_run(project_id="project-a", job_type="source_sync", trigger="http")

        assert result["status"] == "completed"
        assert result["execution"] == "synchronous"
        assert repo.list_sources("project-a")[0]["origin"] == "projects/project-a/01_Sources/note.md"
    finally:
        repo.close()


def test_command_service_reports_unavailable_when_the_real_celery_broker_is_down(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "commands-broker-down.db"))
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: True)
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_broker_available", lambda: False)
    try:
        result = WikiCommandService(repo).start_run(
            project_id="project-a", job_type="source_sync", trigger="manual"
        )

        assert result["status"] == "unavailable"
        assert result["failure"]["code"] == "celery_broker_unavailable"
        persisted = repo.get_run("project-a", result["run_id"])
        assert persisted["status"] == "unavailable"
        assert persisted["output_refs"]["failure"]["retryable"] is True
    finally:
        repo.close()


def test_command_service_persists_celery_assignment_for_a_queued_run(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "commands-celery-assignment.db"))
    dispatched: list[list[str]] = []

    class QueuedTask:
        id = "celery-task-123"

    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: True)
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_broker_available", lambda: True)
    monkeypatch.setattr(
        "app.tasks.knowledge_tasks.knowledge_execute.apply_async",
        lambda args: dispatched.append(args) or QueuedTask(),
    )
    try:
        result = WikiCommandService(repo).start_run(
            project_id="project-a", job_type="source_sync", trigger="http"
        )

        assert result["status"] == "queued"
        assert result["task_id"] == "celery-task-123"
        assert dispatched == [["project-a", result["run_id"]]]
        events = repo.list_run_events(project_id="project-a", run_id=result["run_id"])
        assert [event["event_type"] for event in events] == [
            "knowledge.run.queued",
            "knowledge.run.execution_assigned",
        ]
        assert events[-1]["payload"] == {
            "execution": "celery",
            "task_name": "knowledge.execute",
            "task_id": "celery-task-123",
        }
    finally:
        repo.close()


def test_command_service_routes_growth_runs_to_the_bounded_growth_task(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "commands-growth-celery-assignment.db"))
    dispatched: list[list[str]] = []

    class QueuedTask:
        id = "growth-task-123"

    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: True)
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_broker_available", lambda: True)
    monkeypatch.setattr(
        "app.tasks.growth_tasks.growth_execute.apply_async",
        lambda args: dispatched.append(args) or QueuedTask(),
    )
    try:
        result = WikiCommandService(repo).start_run(
            project_id="project-a", job_type="growth_daily", trigger="http"
        )

        assert result["status"] == "queued"
        assert result["task_id"] == "growth-task-123"
        assert dispatched == [["project-a", result["run_id"]]]
        events = repo.list_run_events(project_id="project-a", run_id=result["run_id"])
        assert [event["event_type"] for event in events] == [
            "knowledge.run.queued",
            "knowledge.run.execution_assigned",
            "knowledge.growth.dispatched",
        ]
        assert events[-1]["payload"] == {
            "execution": "celery",
            "task_name": "knowledge.growth.execute",
            "task_id": "growth-task-123",
            "trigger": "http",
        }
    finally:
        repo.close()


def test_command_service_restores_a_prior_revision_through_a_new_gated_proposal(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    project_root = vault_root / "clients" / "acme"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands-rollback.db"))
    repo.configure_vault("project-a", "clients/acme")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="brief.md",
            raw_content="Human approval is mandatory.", trust_level="trusted",
        )
    ).source
    service = WikiCommandService(repo)
    version_one = "---\ntitle: Approval\nkind: concept\n---\nHuman approval is mandatory. [source:%s]" % source["id"]
    version_two = "---\ntitle: Approval\nkind: concept\n---\nHuman approval is mandatory and reviewed weekly. [source:%s]" % source["id"]
    try:
        repo_case = service.save_eval_case(
            project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]}
        )
        assert repo_case["case_id"] == "citation"
        first = service.create_proposal(
            {
                "project_id": "project-a", "source_ids": [source["id"]], "rationale": "Initial approval rule.",
                "operations": [
                    {"operation": "create", "path": "wiki/concepts/approval.md", "content": version_one, "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/index.md", "content": "\n- [[wiki/concepts/approval.md]]\n", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/log.md", "content": "\n- Approval added. [source:%s]\n" % source["id"], "source_ids": [source["id"]]},
                ],
            }
        )
        service.publish_proposal(project_id="project-a", proposal_id=first["id"])
        page = next(item for item in repo.list_pages("project-a") if item["path"] == "wiki/concepts/approval.md")

        second = service.create_proposal(
            {
                "project_id": "project-a", "source_ids": [source["id"]], "rationale": "Add review cadence.",
                "operations": [
                    {"operation": "replace", "path": "wiki/concepts/approval.md", "content": version_two, "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/index.md", "content": "\n- Approval reviewed\n", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/log.md", "content": "\n- Approval reviewed. [source:%s]\n" % source["id"], "source_ids": [source["id"]]},
                ],
            }
        )
        service.publish_proposal(project_id="project-a", proposal_id=second["id"])
        original = next(item for item in repo.list_page_revisions("project-a", page["id"]) if item["version"] == 1)

        rollback = service.create_rollback_proposal(project_id="project-a", page_id=page["id"], revision_id=original["id"])

        assert rollback["status"] == "draft"
        assert rollback["operations"][0]["operation"] == "replace"
        assert rollback["operations"][0]["content"] == ProposalGate._materialize_published_status(
            "wiki/concepts/approval.md", version_one
        )
        assert service.lint_proposal(project_id="project-a", proposal_id=rollback["id"])["valid"] is True
        service.publish_proposal(project_id="project-a", proposal_id=rollback["id"])
        assert repo.get_page_content("project-a", page["id"])["content"] == ProposalGate._materialize_published_status(
            "wiki/concepts/approval.md", version_one
        )
        assert len(repo.list_page_revisions("project-a", page["id"])) == 3
    finally:
        repo.close()


def test_command_service_recovers_an_interrupted_publish_when_all_effects_reached_the_vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands-publish-recovery.db"))
    repo.configure_vault("project-a", "projects/project-a")
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
                "project_id": "project-a", "source_ids": [source["id"]], "rationale": "Record approval.",
                "operations": [
                    {"operation": "create", "path": "wiki/concepts/approval.md", "content": "---\ntitle: Approval\nkind: concept\n---\nApproval is mandatory. [source:%s]" % source["id"], "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/index.md", "content": "\n- [[wiki/concepts/approval.md]]\n", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/log.md", "content": "\n- Approval added. [source:%s]\n" % source["id"], "source_ids": [source["id"]]},
                ],
            }
        )
        repo.update_proposal_status("project-a", proposal["id"], ProposalStatus.VALIDATING)
        vault = FilesystemWikiVault(vault_root, "project-a", "projects/project-a")
        staged = vault.stage(service._proposal("project-a", proposal["id"]))
        vault.commit(ProposalGate._materialize_published_statuses(staged))
        run = KnowledgeRun(
            project_id="project-a", run_type="wiki_publish", trigger="manual", status=RunStatus.RUNNING,
            input_refs={"proposal_id": proposal["id"]},
        )
        repo.create_run(run)
        repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", ("2026-07-20T00:00:00+00:00", run.id))
        repo._commit()

        result = service.recover_abandoned_publications(
            now=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc), timeout_seconds=60
        )

        assert result == {"recovered": 1, "failed": 0}
        assert repo.get_proposal("project-a", proposal["id"])["status"] == "published"
        assert repo.get_run("project-a", run.id)["status"] == "completed"
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
    finally:
        repo.close()


def test_command_service_makes_an_uncommitted_interrupted_publish_retryable(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_commands.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    repo = WikiRepository(db_path=str(tmp_path / "commands-publish-recovery-failed.db"))
    repo.configure_vault("project-a", "projects/project-a")
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
                "project_id": "project-a", "source_ids": [source["id"]], "rationale": "Record approval.",
                "operations": [{"operation": "create", "path": "wiki/concepts/approval.md", "content": "---\ntitle: Approval\nkind: concept\n---\nApproval is mandatory. [source:%s]" % source["id"], "source_ids": [source["id"]]}],
            }
        )
        repo.update_proposal_status("project-a", proposal["id"], ProposalStatus.VALIDATING)
        run = KnowledgeRun(
            project_id="project-a", run_type="wiki_publish", trigger="manual", status=RunStatus.RUNNING,
            input_refs={"proposal_id": proposal["id"]},
        )
        repo.create_run(run)
        repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", ("2026-07-20T00:00:00+00:00", run.id))
        repo._commit()

        result = service.recover_abandoned_publications(
            now=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc), timeout_seconds=60
        )

        assert result == {"recovered": 0, "failed": 1}
        assert repo.get_proposal("project-a", proposal["id"])["status"] == "failed"
        assert repo.get_proposal("project-a", proposal["id"])["eval_summary"]["publication_error"] == "abandoned_publish_recovered"
        assert repo.get_run("project-a", run.id)["output_refs"]["failure"]["code"] == "abandoned_publish"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
    finally:
        repo.close()
