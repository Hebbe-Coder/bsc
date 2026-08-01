from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceRecord, SourceStatus
from app.tasks.growth_tasks import (
    classify_growth_failure,
    execute_growth_run,
    growth_task_time_limits,
    growth_execute,
    recover_abandoned_growth_runs,
)
from app.tasks.knowledge_tasks import reconcile_knowledge_schedules


def _queued_run(repo, *, run_id="run-growth", run_type="growth_daily", trigger="manual"):
    run = KnowledgeRun(
        id=run_id,
        project_id="project-a",
        run_type=run_type,
        trigger=trigger,
        input_refs={"date": "2026-07-24", "source_cutoff": "2026-07-24T09:00:00+00:00"},
    )
    repo.create_run(run)
    return run


def test_growth_task_is_registered_and_duplicate_delivery_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-celery.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = _queued_run(repo)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    try:
        assert growth_execute.name == "knowledge.growth.execute"
        first = execute_growth_run("project-a", run.id, repository=repo)
        duplicate = execute_growth_run("project-a", run.id, repository=repo)
        assert first["status"] == "completed"
        assert duplicate["duplicate"] is True
        assert len(repo.list_growth_distillations("project-a", "daily")) == 1
        assert repo.get_run("project-a", run.id)["output_refs"]["metrics"]["duplicate_count"] == 1
    finally:
        repo.close()


def test_growth_task_persists_the_correlated_promptops_execution_event(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-promptops-event.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = _queued_run(repo, run_id="growth-model-event")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))

    def generated(_self, _project_id, _period, *, source_cutoff, knowledge_run_id=""):
        assert source_cutoff == "2026-07-24T09:00:00+00:00"
        return {
            "status": "generated",
            "input_hash": "input-hash",
            "paths": ["distillations/example.md"],
            "manifest": {
                "input_count": 1,
                "generation": {
                    "promptops": {
                        "knowledge_run_id": knowledge_run_id,
                        "prompt_run_id": "prompt-a",
                        "agent_manifest_fingerprint": "a" * 64,
                        "task": "knowledge_distillation",
                        "revision": "growth-distillation-v9",
                        "provider": "deepseek",
                        "model": "deepseek-v4-pro",
                        "usage": {"provider_calls": 1, "reported_calls": 1, "complete": True, "total_tokens": 123},
                        "attempt_count": 2,
                        "retry_count": 1,
                        "retry_categories": ["server_error"],
                    }
                },
            },
        }

    monkeypatch.setattr("app.tasks.growth_tasks.GrowthDistillationService.run_daily", generated)
    try:
        result = execute_growth_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        model_event = next(event for event in events if event["event_type"] == "knowledge.growth.model.completed")
        assert model_event["payload"] == {
            "prompt_run_id": "prompt-a",
            "agent_manifest_fingerprint": "a" * 64,
            "task": "knowledge_distillation",
            "revision": "growth-distillation-v9",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "usage": {"provider_calls": 1, "reported_calls": 1, "complete": True, "total_tokens": 123},
            "attempt_count": 2,
            "retry_count": 1,
            "retry_categories": ["server_error"],
        }
    finally:
        repo.close()


def test_growth_task_records_preserved_weekly_bundle_without_claiming_generation(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-preserved-weekly.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = KnowledgeRun(
        id="growth-preserved-weekly",
        project_id="project-a",
        run_type="growth_weekly_distillation",
        trigger="manual",
        input_refs={"week": "2026-W30", "source_cutoff": "2026-07-24T09:00:00+00:00"},
    )
    repo.create_run(run)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr(
        "app.tasks.growth_tasks.GrowthDistillationService.run_weekly",
        lambda *_a, **_k: {
            "status": "preserved",
            "input_hash": "attempted-input-hash",
            "preserved_input_hash": "published-input-hash",
            "paths": [],
            "manifest": {"input_count": 3, "generation": {"mode": "deterministic"}},
        },
    )
    try:
        result = execute_growth_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        stored = repo.get_run("project-a", run.id)
        assert stored["output_refs"]["growth"]["status"] == "preserved"
        assert stored["output_refs"]["metrics"]["preserved_count"] == 1
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        event = next(item for item in events if item["event_type"] == "knowledge.growth.distillation.preserved")
        assert event["payload"] == {
            "kind": "growth_weekly_distillation",
            "period": "2026-W30",
            "input_hash": "attempted-input-hash",
            "paths": [],
            "preserved_input_hash": "published-input-hash",
        }
        assert not any(item["event_type"] == "knowledge.growth.distillation.completed" for item in events)
    finally:
        repo.close()


def test_growth_daily_syncs_declared_obsidian_exports_before_distillation(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    (project_root / "raw" / "readwise").mkdir(parents=True)
    (project_root / "04_Outputs" / "hyperframes").mkdir(parents=True)
    (project_root / "raw" / "readwise" / "research.md").write_text(
        "# Research signal\nA source exported by an Obsidian plugin.", encoding="utf-8"
    )
    (project_root / "04_Outputs" / "hyperframes" / "brief.md").write_text(
        "# Video brief\nA real plugin output awaiting review.", encoding="utf-8"
    )
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":['
        '{"id":"readwise","name":"Readwise","adapter":"filesystem_drop","input_paths":["raw/readwise"]},'
        '{"id":"hyperframes","name":"HyperFrames","adapter":"filesystem_output","input_paths":["04_Outputs/hyperframes"]}'
        ']}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root,
        plugin_ids=("readwise", "hyperframes"),
        trusted=True,
        actor_id="test-operator",
        reason="fixture grants read-only filesystem bridge access",
    )
    repo = GrowthRepository(db_path=str(tmp_path / "growth-plugin-daily.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.create_source(
        SourceRecord(
            id="trusted-preexisting",
            project_id="project-a",
            source_type="horizon_signal",
            content_hash="a" * 64,
            raw_content="Reviewed signal that should enter the eligible context queue.",
            trust_level="reviewed",
            status=SourceStatus.VALIDATED,
            # Generic model importance is not project relevance. This fixture
            # models a signal already assessed as relevant to this project.
            metadata={"relevance": 90},
        )
    )
    repo.create_source(
        SourceRecord(
            id="trusted-low-priority",
            project_id="project-a",
            source_type="horizon_signal",
            content_hash="b" * 64,
            raw_content="Reviewed but low-priority signal that remains pending human review.",
            trust_level="reviewed",
            status=SourceStatus.VALIDATED,
            metadata={"relevance": 0, "value": 0, "freshness": 0, "outputability": 0, "connectedness": 0},
        )
    )
    run = _queued_run(repo, run_id="plugin-daily")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_OBSIDIAN_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    try:
        result = execute_growth_run("project-a", run.id, repository=repo)

        assert result["status"] == "completed"
        assert result["sync"]["status"] == "completed"
        assert result["sync"]["sources"]["created"] == 1
        assert result["sync"]["triage"] == {"evaluated": 3, "eligible": 1, "pending_review": 2}
        assert result["sync"]["outputs"]["registered"] == 1
        assert result["sync"]["metadata_views"] == {
            "status": "completed", "created": 12, "updated": 0, "unchanged": 0, "conflicts": 0
        }
        assert (project_root / "Knowledge Index" / "Knowledge Operations.base").is_file()
        plugin_source = next(
            source for source in repo.list_sources("project-a") if source["vault_path"].endswith("research.md")
        )
        plugins = {item["id"]: item for item in result["sync"]["plugins"]["plugins"]}
        readwise = plugins["readwise"]
        assert {
            key: value
            for key, value in readwise.items()
            if key not in {"trusted_at", "export_observation"}
        } == {
            "id": "readwise",
            "name": "Readwise",
            "adapter": "filesystem_drop",
            "input_paths": ["raw/readwise"],
            "trust_state": "trusted",
            "trust_actor": "test-operator",
            "path_status": "ready",
            "runtime_configuration": {"state": "declared_only", "detail_code": "no_readonly_settings_probe"},
            "status": "captured",
            "capture_state": "captured",
            "captured_sources": 1,
            "registered_outputs": 0,
            "last_captured_at": plugin_source["captured_at"],
            "last_registered_at": "",
        }
        assert readwise["trusted_at"]
        assert readwise["export_observation"]["state"] == "files_detected"
        assert readwise["export_observation"]["file_count"] == 1
        assert readwise["export_observation"]["latest_modified_at"]
        hyperframes = plugins["hyperframes"]
        assert {
            key: value
            for key, value in hyperframes.items()
            if key not in {"trusted_at", "export_observation"}
        } == {
            "id": "hyperframes",
            "name": "HyperFrames",
            "adapter": "filesystem_output",
            "input_paths": ["04_Outputs/hyperframes"],
            "trust_state": "trusted",
            "trust_actor": "test-operator",
            "path_status": "ready",
            "runtime_configuration": {"state": "declared_only", "detail_code": "no_readonly_settings_probe"},
            "status": "registered_output",
            "capture_state": "registered_output",
            "captured_sources": 0,
            "registered_outputs": 1,
            "last_captured_at": "",
            "last_registered_at": repo.list_outputs("project-a")[0]["created_at"],
        }
        assert hyperframes["trusted_at"]
        assert hyperframes["export_observation"]["state"] == "files_detected"
        assert hyperframes["export_observation"]["file_count"] == 1
        assert hyperframes["export_observation"]["latest_modified_at"]
        assert repo.get_source("project-a", "trusted-preexisting")["status"] == "eligible"
        assert repo.get_source("project-a", "trusted-low-priority")["status"] == "validated"
        assert plugin_source["status"] == "validated"
        assert repo.list_outputs("project-a")[0]["status"] == "registered"
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        assert any(event["event_type"] == "knowledge.growth.obsidian_sync.completed" for event in events)
        assert any(event["event_type"] == "knowledge.growth.distillation.completed" for event in events)
    finally:
        repo.close()


def test_growth_entrypoint_rejects_non_growth_run_without_mutating_it(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-wrong-domain.db"))
    run = KnowledgeRun(id="wiki-run", project_id="project-a", run_type="wiki_maintenance", trigger="manual")
    repo.create_run(run)
    try:
        with pytest.raises(ValueError, match="not a growth task"):
            execute_growth_run("project-a", run.id, repository=repo)
        assert repo.get_run("project-a", run.id)["status"] == "queued"
        assert repo.get_run("project-a", run.id)["output_refs"] == {}
    finally:
        repo.close()


def test_duplicate_delivery_does_not_refresh_running_lease(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-duplicate-lease.db"))
    run = _queued_run(repo, run_id="running-duplicate")
    repo.update_run_status("project-a", run.id, RunStatus.RUNNING)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", (stale, run.id))
    repo._commit()
    try:
        duplicate = execute_growth_run("project-a", run.id, repository=repo)
        assert duplicate["duplicate"] is True
        assert repo.get_run("project-a", run.id)["updated_at"] == stale
    finally:
        repo.close()


def test_growth_task_persists_retryable_and_permanent_failure_categories(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-failures.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))

    transient = _queued_run(repo, run_id="transient")
    monkeypatch.setattr("app.tasks.growth_tasks.GrowthDistillationService.run_daily", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk temporarily unavailable")))
    transient_result = execute_growth_run("project-a", transient.id, repository=repo)
    assert transient_result["failure"]["retryable"] is True
    assert repo.get_run("project-a", transient.id)["status"] == "failed"
    transient_metrics = repo.get_run("project-a", transient.id)["output_refs"]["metrics"]
    assert transient_metrics["failure_category"] == "transient_dependency"
    assert transient_metrics["source_cutoff"] == "2026-07-24T09:00:00+00:00"

    permanent = _queued_run(repo, run_id="permanent")
    monkeypatch.setattr("app.tasks.growth_tasks.GrowthDistillationService.run_daily", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("denied")))
    permanent_result = execute_growth_run("project-a", permanent.id, repository=repo)
    assert permanent_result["failure"] == {"category": "policy", "code": "permission_denied", "retryable": False}
    repo.close()


def test_growth_task_timeout_is_bounded_and_retryable():
    timeout = type("SoftTimeLimitExceeded", (Exception,), {})()
    failure = classify_growth_failure(timeout)

    assert failure.category == "transient_dependency"
    assert failure.code == "growth_task_timeout"
    assert failure.retryable is True
    assert growth_task_time_limits() == {"soft_time_limit": 390, "time_limit": 420}


def test_abandoned_growth_run_is_replayed_once_with_original_inputs(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-recovery.db"))
    run = _queued_run(repo, run_id="abandoned", trigger="schedule")
    repo.update_run_status("project-a", run.id, RunStatus.RUNNING)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", (stale, run.id))
    repo._commit()
    dispatched = []
    try:
        first = recover_abandoned_growth_runs(repo, dispatch=lambda project_id, run_id: dispatched.append((project_id, run_id)))
        second = recover_abandoned_growth_runs(repo, dispatch=lambda project_id, run_id: dispatched.append((project_id, run_id)))
        assert first["recovered"] == 1
        assert second["recovered"] == 0
        assert len(dispatched) == 1
        replay = repo.get_run("project-a", dispatched[0][1])
        assert replay["input_refs"]["date"] == "2026-07-24"
        assert replay["retry_of"] == "abandoned"
    finally:
        repo.close()


def test_recovery_does_not_redispatch_a_celery_assigned_growth_run(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-assignment-recovery.db"))
    run = _queued_run(repo, run_id="assigned-growth", trigger="manual")
    repo.append_run_event(
        project_id="project-a",
        run_id=run.id,
        event_type="knowledge.run.execution_assigned",
        payload={"execution": "celery", "task_name": "knowledge.growth.execute", "task_id": "task-123"},
    )
    dispatched = []
    try:
        recovered = recover_abandoned_growth_runs(
            repo,
            dispatch=lambda project_id, run_id: dispatched.append((project_id, run_id)),
        )

        assert recovered == {"recovered": 0, "failures": 0}
        assert dispatched == []
        assert repo.get_run("project-a", run.id)["status"] == "queued"
    finally:
        repo.close()


def test_broker_failure_leaves_recovery_queued_and_replays_on_next_reconcile(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-broker-replay.db"))
    run = _queued_run(repo, run_id="broker-failure", trigger="schedule")
    repo.update_run_status("project-a", run.id, RunStatus.RUNNING)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", (stale, run.id))
    repo._commit()
    calls = []
    try:
        failed_dispatch = recover_abandoned_growth_runs(
            repo,
            dispatch=lambda *_args: (_ for _ in ()).throw(ConnectionError("Redis unavailable")),
        )
        assert failed_dispatch == {"recovered": 0, "failures": 1}
        queued = [item for item in repo.list_runs("project-a") if item.get("retry_of") == run.id]
        assert len(queued) == 1
        assert queued[0]["status"] == "queued"
        failed_events = repo.list_run_events(project_id="project-a", run_id=queued[0]["id"])
        assert any(event["event_type"] == "knowledge.growth.dispatch_failed" for event in failed_events)

        replayed = recover_abandoned_growth_runs(
            repo,
            dispatch=lambda project_id, run_id: calls.append((project_id, run_id)),
        )
        assert replayed == {"recovered": 1, "failures": 0}
        assert calls == [("project-a", queued[0]["id"])]
    finally:
        repo.close()


def test_reconciler_disables_growth_schedule_when_celery_is_not_durable(tmp_path, monkeypatch):
    database = str(tmp_path / "growth-disabled-celery.db")
    repo = GrowthRepository(db_path=database)
    repo.configure_vault("project-a", "projects/project-a")
    schedule = repo.upsert_schedule(
        project_id="project-a",
        job_type="growth_daily",
        cron="0 17 * * *",
        timezone_name="Asia/Shanghai",
        enabled=True,
        next_run_at="2026-07-24T09:00:00+00:00",
    )
    repo.close()
    monkeypatch.setattr(settings, "CELERY_ENABLED", False)
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: GrowthRepository(db_path=database))

    result = reconcile_knowledge_schedules(datetime(2026, 7, 24, 9, 1, tzinfo=timezone.utc))

    reopened = GrowthRepository(db_path=database)
    try:
        assert result == {"queued": 0, "duplicates": 0, "failures": 1, "recovered": 0}
        persisted = reopened.get_schedule("project-a", schedule["id"])
        assert persisted["enabled"] == 0
        assert persisted["next_run_at"] == ""
        assert reopened.list_runs("project-a") == []
    finally:
        reopened.close()


def test_reconciler_replays_broker_submission_before_advancing_schedule(tmp_path, monkeypatch):
    database = str(tmp_path / "growth-reconcile-replay.db")
    repo = GrowthRepository(db_path=database)
    repo.configure_vault("project-a", "projects/project-a")
    schedule = repo.upsert_schedule(
        project_id="project-a",
        job_type="growth_daily",
        cron="0 17 * * *",
        timezone_name="Asia/Shanghai",
        enabled=True,
        next_run_at="2026-07-24T09:00:00+00:00",
    )
    repo.close()
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.is_celery_real", lambda: True)
    monkeypatch.setattr("app.tasks.knowledge_tasks.WikiRepository", lambda: GrowthRepository(db_path=database))
    monkeypatch.setattr(
        "app.tasks.knowledge_tasks.growth_execute.apply_async",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("Redis unavailable")),
    )

    first = reconcile_knowledge_schedules(datetime(2026, 7, 24, 9, 1, tzinfo=timezone.utc))
    after_failure = GrowthRepository(db_path=database)
    try:
        queued = after_failure.list_runs("project-a")
        assert first["failures"] == 1
        assert len(queued) == 1 and queued[0]["status"] == "queued"
        assert after_failure.get_schedule("project-a", schedule["id"])["next_run_at"] == "2026-07-24T09:00:00+00:00"
    finally:
        after_failure.close()

    dispatched = []
    monkeypatch.setattr(
        "app.tasks.knowledge_tasks.growth_execute.apply_async",
        lambda args: dispatched.append(args) or type("Queued", (), {"failed": lambda self: False})(),
    )
    second = reconcile_knowledge_schedules(datetime(2026, 7, 24, 9, 2, tzinfo=timezone.utc))

    reopened = GrowthRepository(db_path=database)
    try:
        assert second["recovered"] == 1
        assert dispatched and dispatched[0][:2] == ["project-a", queued[0]["id"]]
        assert reopened.get_schedule("project-a", schedule["id"])["next_run_at"] > "2026-07-24T09:00:00+00:00"
    finally:
        reopened.close()
