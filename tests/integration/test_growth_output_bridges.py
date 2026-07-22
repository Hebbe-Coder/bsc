import hashlib

import pytest

from app.core.config import settings
from app.core.database import SQLiteBackend
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_bridges import OutputCompletionBridge
from app.skills.execution_store import SkillExecutionStore


def _context(project_id="project-a"):
    return {
        "project_id": project_id,
        "goal": "Generate the project report",
        "audience": "operators",
        "channel": "skill",
        "provider": "test-provider",
        "model": "test-model",
        "prompt_revision": "prompt-v1",
        "context_revision": "context-v1",
    }


def test_completed_skill_orchestration_and_export_register_once(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "bridges.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        bridge = OutputCompletionBridge(repo, vault)
        results = [
            bridge.register_skill_completion(execution_id="skill-1", skill_id="reporter", status="completed", result="# Skill", context=_context()),
            bridge.register_orchestration_completion(session_id="session-1", status="completed", result="# Session", context={**_context(), "channel": "orchestration"}),
            bridge.register_export_completion(export_id="export-1", status="completed", result=b"PK\x03\x04", filename="deck.pptx", mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", context={**_context(), "channel": "export"}),
        ]
        assert [item.status for item in results] == ["registered", "registered", "registered"]
        retry = bridge.register_skill_completion(execution_id="skill-1", skill_id="reporter", status="completed", result="# Skill", context=_context())
        assert retry.output_id == results[0].output_id
        assert len(repo.list_outputs("project-a")) == 3
        assert all(item.audit_run_id for item in results)
    finally:
        repo.close()


@pytest.mark.parametrize("status", ["running", "failed", "cancelled"])
def test_bridge_does_not_register_incomplete_or_failed_work(tmp_path, status):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / f"bridge-{status}.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        result = OutputCompletionBridge(repo, vault).register_skill_completion(
            execution_id=f"skill-{status}", skill_id="reporter", status=status, result="partial", context=_context()
        )
        assert result.status == "not_registered_incomplete"
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_bridge_reports_unscoped_and_audits_registration_failure_without_reopening_producer(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "bridge-failure.db"))
    try:
        bridge = OutputCompletionBridge(repo, vault)
        unscoped = bridge.register_skill_completion(execution_id="skill-unscoped", skill_id="reporter", status="completed", result="ok", context={})
        assert unscoped.status == "not_registered_unscoped"
        failed = bridge.register_skill_completion(execution_id="skill-failed", skill_id="reporter", status="completed", result="ok", context=_context())
        assert failed.status == "registration_failed"
        assert "Vault mapping" in failed.error
        audit = repo.get_run("project-a", failed.audit_run_id)
        assert audit["status"] == "failed"
        assert audit["input_refs"]["producer_status"] == "completed"
    finally:
        repo.close()


def test_bridge_hashes_binary_content_and_rejects_changed_retry(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "bridge-hash.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        bridge = OutputCompletionBridge(repo, vault)
        first = bridge.register_export_completion(export_id="export-1", status="completed", result=b"first", filename="asset.bin",
                                                  mime_type="application/octet-stream", context=_context())
        second = bridge.register_export_completion(export_id="export-1", status="completed", result=b"changed", filename="asset.bin",
                                                   mime_type="application/octet-stream", context=_context())
        assert first.status == "registered"
        assert second.status == "registration_failed"
        assert repo.get_output("project-a", first.output_id)["content_hash"] == hashlib.sha256(b"first").hexdigest()
    finally:
        repo.close()


def test_skill_execution_store_optional_hook_persists_bridge_outcome_without_changing_completion(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    backend = SQLiteBackend(str(tmp_path / "skill-hook.db"))
    repo = GrowthRepository(backend=backend)
    repo.configure_vault("project-a", "projects/project-a", "owner")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault))
    store = SkillExecutionStore(connection=backend)
    store.create(
        {
            "execution_id": "exec-hook-1",
            "skill_id": "reporter",
            "status": "running",
            "params": {
                "project_id": "project-a",
                "goal": "Produce a report",
                "audience": "operators",
                "channel": "skill",
                "input": "evidence",
            },
            "provider": "test-provider",
            "model_name": "test-model",
            "manifest_revision": "skill-v1",
        }
    )
    completed = store.update("exec-hook-1", status="completed", result="# Report")
    assert completed["status"] == "completed"
    assert completed["result"] == "# Report"
    outcome = completed["params"]["_growth_output_registration"]
    assert outcome["status"] == "registered"
    assert len(repo.list_outputs("project-a")) == 1

    repeated = store.update("exec-hook-1", status="completed", result="# Report")
    assert repeated["params"]["_growth_output_registration"] == outcome
    assert len(repo.list_outputs("project-a")) == 1
    backend.close()


def test_skill_execution_store_retries_only_failed_registration(tmp_path):
    backend = SQLiteBackend(str(tmp_path / "skill-retry.db"))
    calls = []

    def hook(execution):
        calls.append(execution["execution_id"])
        return {
            "status": "registration_failed" if len(calls) == 1 else "registered",
            "producer_type": "skill", "producer_id": execution["execution_id"],
            "output_id": "output-a" if len(calls) > 1 else "", "audit_run_id": "audit-a", "error": "",
        }

    store = SkillExecutionStore(connection=backend, completion_hook=hook)
    store.create({"execution_id": "exec-retry", "skill_id": "reporter", "status": "running", "params": {"project_id": "project-a"}})
    first = store.update("exec-retry", status="completed", result="report")
    second = store.update("exec-retry", status="completed", result="report")
    third = store.update("exec-retry", status="completed", result="report")
    assert first["params"]["_growth_output_registration"]["status"] == "registration_failed"
    assert second["params"]["_growth_output_registration"]["status"] == "registered"
    assert third["params"]["_growth_output_registration"]["status"] == "registered"
    assert calls == ["exec-retry", "exec-retry"]
    backend.close()
