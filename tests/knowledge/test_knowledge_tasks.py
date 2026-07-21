from datetime import datetime, timezone

from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
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
        assert repo.get_run("project-a", run.id)["status"] == "unavailable"
    finally:
        repo.close()


def test_source_sync_task_imports_only_non_managed_obsidian_notes(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-sync.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "research.md").write_text("# Research\nGrounded observation.", encoding="utf-8")
    (vault_root / "projects" / "project-a" / "wiki").mkdir(parents=True)
    (vault_root / "projects" / "project-a" / "wiki" / "overview.md").write_text("managed output", encoding="utf-8")
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "completed"
        assert result["sync"] == {"scanned": 1, "created": 1, "duplicates": 0, "skipped": 0}
        assert repo.get_run("project-a", run.id)["status"] == "completed"
        assert repo.list_sources("project-a")[0]["origin"] == "research.md"
    finally:
        repo.close()


def test_wiki_maintenance_task_is_unavailable_without_a_real_configured_llm(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-maintenance.db"))
    run = KnowledgeRun(project_id="project-a", run_type="wiki_maintenance", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
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
        assert repo.get_run("project-a", run.id)["status"] == "unavailable"
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

        assert result == {"queued": 1, "duplicates": 0, "failures": 0}
        assert dispatched and dispatched[0][0] == "project-a"
        assert repo.list_schedules("project-a")[0]["id"] == schedule["id"]
        assert repo.list_schedules("project-a")[0]["next_run_at"] > due_at
        assert repo.list_runs("project-a")[0]["status"] == "queued"
    finally:
        repo.close()
