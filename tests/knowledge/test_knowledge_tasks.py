from datetime import datetime, timezone

from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_rules import build_default_agents_rules
from app.tasks.knowledge_tasks import execute_knowledge_run
from app.tasks.knowledge_tasks import reconcile_knowledge_schedules


def test_weekly_distillation_task_marks_run_unavailable_without_eligible_evidence(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-empty.db"))
    run = KnowledgeRun(project_id="project-a", run_type="weekly_distillation", trigger="manual")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "unavailable"
        assert result["failure"] == {
            "category": "policy", "code": "no_eligible_evidence", "retryable": False
        }
        assert repo.get_run("project-a", run.id)["status"] == "unavailable"
        assert repo.get_run("project-a", run.id)["output_refs"]["failure"] == result["failure"]
    finally:
        repo.close()


def test_execute_is_idempotent_for_an_existing_terminal_run(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-terminal.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    repo.update_run_status("project-a", run.id, RunStatus.COMPLETED, output_refs={"sync": {"created": 1}})
    before_events = repo.list_run_events(project_id="project-a", run_id=run.id)
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result == {"status": "completed", "run_id": run.id, "duplicate": True, "output_refs": {"sync": {"created": 1}}}
        assert repo.list_run_events(project_id="project-a", run_id=run.id) == before_events
    finally:
        repo.close()


def test_source_sync_task_imports_only_non_managed_obsidian_notes(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-sync.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "projects/project-a")
    (vault_root / "research.md").write_text("# Research\nGrounded observation.", encoding="utf-8")
    (vault_root / "projects" / "project-a" / "wiki").mkdir(parents=True)
    (vault_root / "projects" / "project-a" / "wiki" / "overview.md").write_text("managed output", encoding="utf-8")
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "completed"
        assert result["sync"] == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0, "wiki_pages": 1}
        assert repo.get_run("project-a", run.id)["status"] == "completed"
        assert repo.list_sources("project-a")[0]["origin"] == "research.md"
    finally:
        repo.close()


def test_source_sync_task_reconciles_user_edited_managed_wiki_pages(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-wiki-sync.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    project_root = vault_root / "clients" / "acme"
    (project_root / "wiki" / "concepts").mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("---\nproject_id: project-a\n---\n# Rules\n", encoding="utf-8")
    (project_root / "wiki" / "concepts" / "approval.md").write_text(
        "---\ntitle: Approval\nkind: concept\n---\n# Approval\nUser-maintained page.\n", encoding="utf-8"
    )
    repo.configure_vault("project-a", "clients/acme")
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "completed"
        assert result["sync"]["wiki_pages"] == 2
        page = next(page for page in repo.list_pages("project-a") if page["path"] == "wiki/concepts/approval.md")
        assert repo.get_page_content("project-a", page["id"])["content"].endswith("User-maintained page.\n")
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        assert any(event["event_type"] == "knowledge.wiki.snapshot.synced" for event in events)
    finally:
        repo.close()


def test_wiki_maintenance_task_is_unavailable_without_a_real_configured_llm(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-maintenance.db"))
    run = KnowledgeRun(project_id="project-a", run_type="wiki_maintenance", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "projects/project-a")
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(
        "---\nproject_id: project-a\npage_kinds: [concept]\nwrite_root: wiki/\n---\n"
        "## Project Scope\n## Evidence Hierarchy\n## Allowed Page Kinds\n## Frontmatter Schema\n"
        "## Citation Convention\n## Contradiction Policy\n## SOP Requirements\n## Content Voice\n## Maintenance Workflow\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    monkeypatch.setattr("app.knowledge.wiki_llm_provider.settings.KNOWLEDGE_WIKI_LLM_PROVIDER", "")
    monkeypatch.setattr("app.knowledge.wiki_llm_provider.settings.SOP_LLM_PROVIDER", "mock")
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "unavailable"
        assert result["failure"]["code"] == "wiki_llm_provider_not_configured"
        assert repo.get_run("project-a", run.id)["status"] == "unavailable"
    finally:
        repo.close()


def test_wiki_maintenance_auto_publishes_only_for_enabled_trusted_project_policy(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-auto-publish.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault(
        "project-a",
        "projects/project-a",
        metadata={"auto_publish_enabled": True},
    )
    rules = build_default_agents_rules("project-a")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="policy.md",
            raw_content="Human approval is mandatory.",
            trust_level="trusted",
        )
    ).source
    contents = {
        "AGENTS.md": rules,
        "wiki/overview.md": "---\ntitle: Overview\nkind: brief\n---\n# Overview\n",
        "wiki/index.md": "---\ntitle: Index\nkind: brief\n---\n# Index\n",
        "wiki/log.md": "# Log\n",
    }
    vault = FilesystemWikiVault(vault_root, "project-a", "projects/project-a")
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    WikiEvaluator(repo).save_case(
        project_id="project-a",
        case_id="citation",
        case_type="citation",
        expected={"source_ids": [source["id"]]},
    )
    run = KnowledgeRun(
        project_id="project-a",
        run_type="wiki_maintenance",
        trigger="scheduled",
        input_refs={"source_ids": [source["id"]]},
    )
    repo.create_run(run)

    class TrustedProvider:
        def compile_wiki(self, _prompt):
            return {
                "rationale": "Record the trusted approval policy.",
                "operations": [{
                    "operation": "create",
                    "path": "wiki/concepts/approval.md",
                    "content": (
                        "---\ntitle: Approval\nkind: concept\n---\n"
                        f"Human approval is mandatory. [source:{source['id']}]"
                    ),
                    "source_ids": [source["id"]],
                }],
            }

    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.KNOWLEDGE_WIKI_AUTO_PUBLISH_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.SOPWikiCompilerProvider", TrustedProvider)
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        assert result["publication"]["status"] == "published"
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
        assert "wiki/concepts/approval.md" in vault.contents
        assert repo.get_run("project-a", run.id)["output_refs"]["publication"]["publication_policy"]["mode"] == "automatic"
    finally:
        repo.close()


def test_weekly_distillation_task_writes_project_bundle(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-bundle.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="# Evidence\nA grounded fact.", trust_level="trusted")
    ).source
    repo.record_publication(
        project_id="project-a",
        contents={"wiki/overview.md": "---\ntitle: Overview\nkind: brief\n---\n# Overview\n"},
        source_ids=[],
    )
    page_id = repo.list_pages("project-a")[0]["id"]
    run = KnowledgeRun(project_id="project-a", run_type="weekly_distillation", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "projects/project-a")
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("rules", encoding="utf-8")
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id, week="2026-W30")

        assert result["status"] == "completed"
        assert (project_root / "distillations" / "2026-W30" / "knowledge-action.md").exists()
        assert repo.get_run("project-a", run.id)["status"] == "completed"
        distillation = repo.list_distillations("project-a")
        assert distillation[0]["week"] == "2026-W30"
        assert distillation[0]["knowledge_path"].endswith("knowledge-action.md")
        action = (project_root / "distillations" / "2026-W30" / "knowledge-action.md").read_text(encoding="utf-8")
        assert page_id in action
        assert source["status"] == "eligible"
    finally:
        repo.close()


def test_schedule_reconciler_claims_due_run_and_advances_only_after_enqueue(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "schedule-reconcile.db"))
    due_at = "2026-07-21T13:00:00+00:00"
    schedule = repo.upsert_schedule(
        project_id="project-a", job_type="weekly_distillation", cron="*/5 * * * *",
        timezone_name="UTC", enabled=True, next_run_at=due_at,
    )
    dispatched: list[list[str]] = []
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr(
        "app.tasks.knowledge_tasks.knowledge_execute.apply_async",
        lambda args: dispatched.append(args) or type("QueuedTask", (), {"id": "queued-task"})(),
    )
    try:
        result = reconcile_knowledge_schedules(datetime(2026, 7, 21, 13, 5, tzinfo=timezone.utc))

        assert result == {"queued": 1, "duplicates": 0, "failures": 0, "recovered": 0}
        assert dispatched and dispatched[0][0] == "project-a"
        assert repo.list_schedules("project-a")[0]["id"] == schedule["id"]
        assert repo.list_schedules("project-a")[0]["next_run_at"] > due_at
        assert repo.list_runs("project-a")[0]["status"] == "queued"
    finally:
        repo.close()


def test_quality_task_runs_project_lint_and_persisted_evaluation(tmp_path, monkeypatch):
    from app.knowledge.wiki_rules import build_default_agents_rules

    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    rules = build_default_agents_rules("project-a")
    (project_root / "AGENTS.md").write_text(rules, encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "tasks-quality.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Approval evidence", trust_level="trusted")
    ).source
    repo.record_publication(
        project_id="project-a",
        contents={
            "AGENTS.md": rules,
            "wiki/overview.md": f"---\ntitle: Overview\nkind: brief\n---\n# Overview\n[[wiki/concepts/approval.md]] [source:{source['id']}]",
            "wiki/index.md": "# Index\n[[wiki/concepts/approval.md]]",
            "wiki/log.md": "# Log\n",
            "wiki/concepts/approval.md": f"---\ntitle: Approval\nkind: concept\n---\nApproval required. [source:{source['id']}]",
        },
        source_ids=[],
    )
    WikiEvaluator(repo).save_case(
        project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]}
    )
    run = KnowledgeRun(project_id="project-a", run_type="knowledge_lint_eval", trigger="manual")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        assert result["lint"]["valid"] is True
        assert result["evaluation"]["status"] == "passed"
        assert repo.get_run("project-a", run.id)["output_refs"]["evaluation"]["score"] == 1.0
    finally:
        repo.close()
