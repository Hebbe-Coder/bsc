from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.main import app


@pytest.fixture
def failure_api(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "API_KEY", "failure-admin-key")
    monkeypatch.setattr(settings, "API_KEY_READER", "failure-reader-key")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    Path(settings.OBSIDIAN_VAULT_ROOT).mkdir()
    repository = GrowthRepository(db_path=str(tmp_path / "failure-api.db"))
    app.dependency_overrides[get_growth_repository] = lambda: repository
    try:
        yield TestClient(app), repository
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repository.close()


def _headers(key: str = "failure-admin-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_failure_api_preserves_project_scope_run_evidence_and_resolution_lifecycle(failure_api):
    client, repository = failure_api
    run = repository.create_run(KnowledgeRun(
        id="failure-run-a", project_id="project-a", run_type="growth_daily",
        trigger="test", status=RunStatus.RUNNING,
    ))
    event = repository.append_run_event(
        project_id="project-a", run_id=run["id"], event_type="knowledge.routing.failed",
        payload={"reason": "no matching published method"},
    )

    created = client.post(
        "/knowledge/projects/project-a/failures",
        headers=_headers(),
        json={
            "code": "routing_mismatch",
            "secondary_diagnostic_patterns": ["P09"],
            "summary": "The requested SOP selected no method for a known sibling task.",
            "run_id": run["id"],
            "event_sequence": event["sequence"],
            "evidence_refs": ["method:briefing", "run:failure-run-a"],
            "minimal_structural_fix": "Add the sibling task as a routing holdout before publication.",
            "retryable": True,
        },
    )
    assert created.status_code == 201, created.text
    failure = created.json()["data"]["failure"]
    assert failure["code"] == "routing_mismatch"
    assert failure["diagnostic_pattern"] == "P05"
    assert failure["secondary_diagnostic_patterns"] == ["P09"]
    assert failure["status"] == "open"
    assert failure["event_sequence"] == event["sequence"]

    listed = client.get("/knowledge/projects/project-a/failures?diagnostic_pattern=P05", headers=_headers())
    cross_project = client.get(f"/knowledge/projects/project-b/failures/{failure['id']}", headers=_headers())
    denied = client.post(
        "/knowledge/projects/project-a/failures",
        headers=_headers("failure-reader-key"),
        json={"code": "stale_index", "summary": "reader must not write"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["failures"][0]["id"] == failure["id"]
    assert listed.json()["data"]["failures"][0]["minimal_structural_fix"].startswith("Add the sibling")
    assert cross_project.status_code == 404
    assert denied.status_code == 403

    resolved = client.post(
        f"/knowledge/projects/project-a/failures/{failure['id']}/resolve",
        headers=_headers(),
        json={"resolution_note": "A routing regression case was added and queued for verification.", "retry_scheduled": True},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["data"]["failure"]["status"] == "retry_scheduled"
