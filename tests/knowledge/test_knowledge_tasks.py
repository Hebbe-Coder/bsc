from datetime import datetime, timezone
import json

from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.wiki_contracts import SourceRecord
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_compiler import WikiCompilationError, WikiSourceAdmissionError
from app.knowledge.wiki_llm_provider import WikiLLMProviderError
from app.knowledge.scheduler import KnowledgeScheduler
from app.tasks.knowledge_tasks import classify_knowledge_failure, execute_knowledge_run
from app.tasks.knowledge_tasks import reconcile_knowledge_schedules


def test_compiler_schema_failure_is_not_misclassified_as_missing_configuration():
    failure = classify_knowledge_failure(WikiCompilationError("operation field required"))

    assert failure.__dict__ == {
        "category": "compiler",
        "code": "compiler_failed",
        "retryable": False,
    }


def test_source_admission_failure_is_reported_as_a_non_retryable_policy_failure():
    failure = classify_knowledge_failure(
        WikiSourceAdmissionError("horizon-signal", "horizon_signal_requires_independent_primary_capture")
    )

    assert failure.__dict__ == {
        "category": "policy",
        "code": "source_not_admitted",
        "retryable": False,
    }


def test_wiki_llm_payment_requirement_is_an_unavailable_dependency():
    failure = classify_knowledge_failure(WikiLLMProviderError("payment_required"))

    assert failure.__dict__ == {
        "category": "dependency",
        "code": "wiki_llm_payment_required",
        "retryable": False,
    }


def test_wiki_llm_request_shape_failure_remains_a_compiler_failure():
    failure = classify_knowledge_failure(WikiLLMProviderError("response_payload_invalid"))

    assert failure.__dict__ == {
        "category": "compiler",
        "code": "wiki_llm_response_payload_invalid",
        "retryable": False,
    }


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


def test_execute_does_not_repeat_a_run_already_claimed_by_another_worker(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-claimed.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    assert repo.claim_run_execution(project_id="project-a", run_id=run.id) is True
    synchronizer_calls = []

    class _UnexpectedSyncService:
        def __init__(self, *_args, **_kwargs):
            synchronizer_calls.append("initialized")

        def sync(self, **_kwargs):
            synchronizer_calls.append("synced")
            raise AssertionError("a duplicate executor must not synchronize the Vault")

    monkeypatch.setattr("app.tasks.knowledge_tasks.ObsidianSyncService", _UnexpectedSyncService)
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result == {"status": "running", "run_id": run.id, "duplicate": True, "output_refs": {}}
        assert synchronizer_calls == []
        assert [event["event_type"] for event in repo.list_run_events(project_id="project-a", run_id=run.id)] == [
            "knowledge.run.queued",
            "knowledge.run.running",
        ]
    finally:
        repo.close()


def test_source_sync_task_imports_only_non_managed_obsidian_notes(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-sync.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "projects/project-a")
    repo.create_source(SourceRecord(
        id="horizon-test-1",
        project_id="project-a",
        source_type="horizon_signal",
        origin="https://example.com/horizon",
        content_hash="a" * 64,
        raw_content="Captured Horizon evidence",
        trust_level="reviewed",
    ))
    (vault_root / "research.md").write_text("# Research\nGrounded observation.", encoding="utf-8")
    (vault_root / "projects" / "project-a" / "wiki").mkdir(parents=True)
    (vault_root / "projects" / "project-a" / "wiki" / "overview.md").write_text("managed output", encoding="utf-8")
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "completed"
        assert result["sync"]["scanned"] == 1
        assert result["sync"]["evidence_mirror"]["created"] == 1
        assert result["sync"]["wiki_pages"] == 1
        assert result["sync"]["wiki_index"]["indexed"] == 1
        assert repo.get_run("project-a", run.id)["status"] == "completed"
        assert any(source["origin"] == "research.md" for source in repo.list_sources("project-a"))
        assert (vault_root / "projects" / "project-a" / "01_Sources" / "bsc-evidence" / "horizon-test-1.md").is_file()
    finally:
        repo.close()


def test_source_sync_task_is_unavailable_when_its_feature_flag_is_disabled(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-sync-disabled.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.KNOWLEDGE_OBSIDIAN_SYNC_ENABLED", False)
    try:
        result = execute_knowledge_run("project-a", run.id)

        assert result["status"] == "unavailable"
        assert result["failure"] == {
            "category": "configuration", "code": "obsidian_sync_disabled", "retryable": False
        }
        assert repo.get_run("project-a", run.id)["status"] == "unavailable"
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
        assert result["sync"]["wiki_index"]["indexed"] == 2
        page = next(page for page in repo.list_pages("project-a") if page["path"] == "wiki/concepts/approval.md")
        assert repo.get_page_content("project-a", page["id"])["content"].endswith("User-maintained page.\n")
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        assert any(event["event_type"] == "knowledge.wiki.snapshot.synced" for event in events)
    finally:
        repo.close()


def test_source_sync_task_registers_declared_external_output_feedback(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "tasks-output-feedback.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "hyperframes"
    output_root.mkdir(parents=True)
    (output_root / "video-brief.md").write_text("# Video brief\nPlugin generated output", encoding="utf-8")
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"hyperframes","name":"HyperFrames","adapter":"filesystem_output","input_paths":["04_Outputs/hyperframes"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root,
        plugin_ids=["hyperframes"],
        trusted=True,
        actor_id="pytest",
        reason="The test explicitly authorizes this declared filesystem bridge.",
    )
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(vault_root))
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)
        output = repo.list_outputs("project-a")[0]

        assert result["status"] == "completed"
        assert result["sync"]["output_feedback"] == {
            "scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0
        }
        assert output["status"] == "registered"
        assert output["metadata"]["original_path"] == "04_Outputs/hyperframes/video-brief.md"
        assert any(
            edge["edge_type"] == "output_produced_by_run" and edge["from_id"] == run.id and edge["to_id"] == output["id"]
            for edge in repo.list_lineage("project-a")
        )
    finally:
        repo.close()


def test_wiki_maintenance_task_is_unavailable_without_a_real_configured_llm(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-maintenance.db"))
    run = KnowledgeRun(project_id="project-a", run_type="wiki_maintenance", trigger="manual")
    repo.create_run(run)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "projects/project-a")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="provider-required.md",
            raw_content="This eligible evidence requires a governed Wiki maintenance decision.",
            trust_level="trusted",
        )
    ).source
    assert source["status"] == SourceStatus.ELIGIBLE.value
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


def test_horizon_capture_task_imports_native_run_store_artifact(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-run-store.db"))
    runs_root = tmp_path / "mcp-runs"
    run_dir = runs_root / "run-horizon-1"
    run_dir.mkdir(parents=True)
    (run_dir / "filtered_items.json").write_text(
        json.dumps([
            {
                "id": "rss:ai:1",
                "source_type": "rss",
                "title": "Agent systems",
                "url": "https://example.com/agents",
                "content": "Primary article content.",
                "published_at": "2026-07-22T00:00:00Z",
                "ai_score": 8.2,
                "ai_reason": "Useful architecture",
                "ai_summary": "Grounded signal.",
                "ai_tags": ["agents"],
            }
        ]),
        encoding="utf-8",
    )
    run = KnowledgeRun(
        project_id="project-a",
        run_type="horizon_capture",
        trigger="manual",
        input_refs={"horizon_run_id": "run-horizon-1", "stage": "filtered"},
    )
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        assert result["horizon"] == {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 0}
        persisted = repo.get_run("project-a", run.id)
        assert persisted["output_refs"]["source_mode"] == "run_store"
        source = repo.list_sources("project-a")[0]
        assert source["source_type"] == "horizon_signal"
        assert source["metadata"]["horizon_run_id"] == "run-horizon-1"
    finally:
        repo.close()


def test_horizon_capture_uses_host_artifacts_when_direct_api_cannot_see_container_mount(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-host-fallback.db"))
    runs_root = tmp_path / "mcp-runs"
    run_dir = runs_root / "run-host-fallback"
    run_dir.mkdir(parents=True)
    (run_dir / "enriched_items.json").write_text(
        json.dumps([{"id": "rss:host:1", "source_type": "rss", "title": "Host signal", "url": "https://example.com/host", "content": "Host-readable evidence.", "published_at": "2026-07-24T00:00:00Z", "ai_score": 8.4}]),
        encoding="utf-8",
    )
    run = KnowledgeRun(project_id="project-a", run_type="horizon_capture", trigger="manual")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", "/horizon-runs")
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_HOST_PATH", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        persisted = repo.get_run("project-a", run.id)
        assert persisted["output_refs"]["horizon_run_id"] == "run-host-fallback"
        assert persisted["output_refs"]["run_store_resolution"] == "host_fallback"
        assert len(repo.list_sources("project-a")) == 1
    finally:
        repo.close()


def test_scheduled_horizon_capture_discovers_latest_run_and_skips_it_after_import(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-discovery.db"))
    runs_root = tmp_path / "mcp-runs"
    run_dir = runs_root / "run-horizon-auto"
    run_dir.mkdir(parents=True)
    (run_dir / "filtered_items.json").write_text(
        json.dumps([
            {
                "id": "rss:auto:1",
                "source_type": "rss",
                "title": "Automated signal",
                "url": "https://example.com/automated-signal",
                "content": "Evidence captured by an automated Horizon run.",
                "published_at": "2026-07-22T00:00:00Z",
                "ai_score": 8.4,
            }
        ]),
        encoding="utf-8",
    )
    first = KnowledgeRun(project_id="project-a", run_type="horizon_capture", trigger="schedule")
    second = KnowledgeRun(project_id="project-a", run_type="horizon_capture", trigger="schedule")
    repo.create_run(first)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        first_result = execute_knowledge_run("project-a", first.id, repository=repo)
        repo.create_run(second)
        second_result = execute_knowledge_run("project-a", second.id, repository=repo)

        assert first_result["status"] == "completed"
        first_run = repo.get_run("project-a", first.id)
        assert first_run["output_refs"]["horizon_run_id"] == "run-horizon-auto"
        assert first_run["output_refs"]["discovery"] is True
        assert first_run["output_refs"]["outcome"] == "processed"
        assert first_run["output_refs"]["items_observed"] == 1
        assert second_result["horizon"]["skipped"] is True
        second_run = repo.get_run("project-a", second.id)
        assert second_run["status"] == "completed"
        assert second_run["output_refs"]["outcome"] == "no_new_artifact"
        assert second_run["output_refs"]["items_observed"] == 0
        assert len(repo.list_sources("project-a")) == 1
        events = repo.list_run_events(project_id="project-a", run_id=second.id)
        assert any(event["event_type"] == "knowledge.horizon.capture.skipped" for event in events)
    finally:
        repo.close()


def test_scheduled_horizon_capture_records_a_newer_producer_failure(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-producer-failure.db"))
    runs_root = tmp_path / "mcp-runs"
    run_dir = runs_root / "run-backlog"
    run_dir.mkdir(parents=True)
    (run_dir / "filtered_items.json").write_text(
        json.dumps([{"id": "rss:backlog:1", "title": "Backlog"}]),
        encoding="utf-8",
    )
    (runs_root / "producer-state.json").write_text(
        json.dumps({"status": "failed", "error": "HZ_EMPTY_INPUT: No items available for scoring."}),
        encoding="utf-8",
    )
    run = KnowledgeRun(project_id="project-a", run_type="horizon_capture", trigger="schedule")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "failed"
        persisted = repo.get_run("project-a", run.id)
        assert persisted["status"] == "failed"
        assert persisted["output_refs"]["outcome"] == "producer_failure"
        assert persisted["output_refs"]["failure"] == {
            "category": "transient_dependency",
            "code": "horizon_producer_failed",
            "retryable": True,
        }
        assert "HZ_EMPTY_INPUT" in persisted["error"]
    finally:
        repo.close()


def test_horizon_empty_stage_is_completed_without_being_recorded_as_a_channel_failure(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-empty-stage.db"))
    runs_root = tmp_path / "mcp-runs"
    run_dir = runs_root / "run-horizon-empty"
    run_dir.mkdir(parents=True)
    (run_dir / "filtered_items.json").write_text("[]", encoding="utf-8")
    run = KnowledgeRun(
        project_id="project-a",
        run_type="horizon_capture",
        trigger="manual",
        input_refs={"horizon_run_id": "run-horizon-empty", "stage": "filtered"},
    )
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        persisted = repo.get_run("project-a", run.id)
        assert persisted["output_refs"]["outcome"] == "empty_result"
        assert persisted["output_refs"]["items_observed"] == 0
        assert "failure" not in persisted["output_refs"]
        assert persisted["error"] == ""
    finally:
        repo.close()


def test_horizon_missing_explicit_artifact_is_a_channel_error_not_an_empty_result(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "tasks-horizon-channel-error.db"))
    runs_root = tmp_path / "mcp-runs"
    runs_root.mkdir()
    run = KnowledgeRun(
        project_id="project-a",
        run_type="horizon_capture",
        trigger="manual",
        input_refs={"horizon_run_id": "run-unavailable", "stage": "filtered"},
    )
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_RUNS_ROOT", str(runs_root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_API_BASE_URL", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result["status"] == "failed"
        persisted = repo.get_run("project-a", run.id)
        assert persisted["output_refs"]["outcome"] == "channel_error"
        assert persisted["output_refs"]["failure"] == {
            "category": "transient_dependency", "code": "horizon_unavailable", "retryable": True
        }
        assert "empty_result" not in persisted["output_refs"].values()
        failures = GrowthRepository.borrow(repo).list_failure_records("project-a", run_id=run.id)
        assert len(failures) == 1
        assert failures[0]["code"] == "source_capture_failure"
        linked_events = [
            event
            for event in repo.list_run_events(project_id="project-a", run_id=run.id)
            if event["sequence"] == failures[0]["event_sequence"]
        ]
        assert linked_events[0]["event_type"] == "knowledge.run.failure_recorded"
        assert bool(failures[0]["retryable"]) is True
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


def test_schedule_reconciler_requeues_unproven_source_sync_claim(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "schedule-reconcile-requeue.db"))
    due_at = "2026-07-21T13:00:00+00:00"
    schedule = repo.upsert_schedule(
        project_id="project-a", job_type="source_sync", cron="*/5 * * * *",
        timezone_name="UTC", enabled=True, next_run_at=due_at,
    )
    stale_claim = KnowledgeScheduler(repo, scheduler_available=True).claim_run(
        project_id="project-a",
        job_type="source_sync",
        idempotency_key=f"{schedule['id']}:{due_at}",
        trigger="schedule",
    )
    dispatched: list[list[str]] = []
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr(
        "app.tasks.knowledge_tasks.knowledge_execute.apply_async",
        lambda args: dispatched.append(args) or type("QueuedTask", (), {"id": "requeued-task"})(),
    )
    try:
        result = reconcile_knowledge_schedules(datetime(2026, 7, 21, 13, 5, tzinfo=timezone.utc))

        assert stale_claim["claimed"] is True
        assert result == {"queued": 1, "duplicates": 1, "failures": 0, "recovered": 0}
        assert dispatched == [["project-a", stale_claim["run_id"], schedule["id"]]]
        events = repo.list_run_events(project_id="project-a", run_id=stale_claim["run_id"])
        assert any(event["event_type"] == "knowledge.run.execution_dispatched" for event in events)
        assert repo.get_schedule("project-a", schedule["id"])["next_run_at"] > due_at
    finally:
        repo.close()


def test_schedule_reconciler_includes_abandoned_publication_recovery(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "schedule-publish-recovery.db"))
    calls = []

    class _PublicationRecovery:
        def __init__(self, received_repo):
            assert received_repo is repo

        def recover_abandoned_publications(self, *, now, timeout_seconds):
            calls.append((now, timeout_seconds))
            return {"recovered": 1, "failed": 0}

    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: repo)
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiCommandService", _PublicationRecovery)
    try:
        current = datetime(2026, 7, 21, 13, 5, tzinfo=timezone.utc)
        result = reconcile_knowledge_schedules(current)

        assert result == {"queued": 0, "duplicates": 0, "failures": 0, "recovered": 1}
        assert calls == [(current, 120)]
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
        project_id="project-a",
        case_id="citation",
        case_type="citation",
        expected={
            "source_ids": [source["id"]],
            "scope_paths": ["wiki/concepts/approval.md"],
        },
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


def test_wiki_maintenance_without_eligible_evidence_completes_as_auditable_noop(tmp_path, monkeypatch):
    from app.knowledge.wiki_rules import build_default_agents_rules

    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "tasks-maintenance-noop.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = KnowledgeRun(project_id="project-a", run_type="wiki_maintenance", trigger="schedule")
    repo.create_run(run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)

        assert result == {
            "status": "completed",
            "run_id": run.id,
            "outcome": "no_eligible_sources",
        }
        persisted = repo.get_run("project-a", run.id)
        assert persisted["status"] == "completed"
        assert persisted["output_refs"]["outcome"] == "no_eligible_sources"
        assert GrowthRepository.borrow(repo).list_failure_records("project-a", run_id=run.id) == []
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        assert any(event["event_type"] == "knowledge.wiki.maintenance.noop" for event in events)
    finally:
        repo.close()
