from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_contracts import MethodAsset, MethodRevision, MethodStatus, OutputAsset, OutputEvaluation
from app.knowledge.growth_repository import GrowthRepository
from app.main import app


def _headers(key: str = "growth-admin-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def evolution_api(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "API_KEY", "growth-admin-key")
    monkeypatch.setattr(settings, "API_KEY_READER", "growth-reader-key")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    Path(settings.OBSIDIAN_VAULT_ROOT).mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "method-evolution-api.db"))
    app.dependency_overrides[get_growth_repository] = lambda: repo
    client = TestClient(app)
    try:
        yield client, repo
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repo.close()


def _manifest() -> dict:
    return {
        "task_family": "weekly-report",
        "prompt_only": True,
        "trigger_contract": {"positive_signals": ["weekly report"], "negative_signals": ["quick social post"]},
        "applicability": ["weekly reporting"],
        "exclusions": ["quick social post"],
        "inputs": [{"name": "evidence"}],
        "outputs": [{"name": "weekly report"}],
        "steps": ["Review evidence", "Draft the report"],
        "evidence_rules": ["cite sources"],
        "failure_handling": ["stop on missing evidence"],
        "eval_cases": [
            {"id": "positive-1", "type": "should_trigger", "split": "positive", "prompt": "create weekly report", "expected_method": "weekly-report"},
            {"id": "positive-2", "type": "should_trigger", "split": "positive", "prompt": "prepare weekly report", "expected_method": "weekly-report"},
            {"id": "positive-3", "type": "should_trigger", "split": "positive", "prompt": "review weekly report", "expected_method": "weekly-report"},
            {"id": "near-negative-1", "type": "should_not_trigger", "split": "near_negative", "prompt": "quick social post", "expected_method": ""},
            {"id": "near-negative-2", "type": "should_not_trigger", "split": "near_negative", "prompt": "short social post", "expected_method": ""},
            {"id": "holdout-1", "type": "should_trigger", "split": "holdout", "prompt": "weekly report for leadership", "expected_method": "weekly-report"},
            {"id": "holdout-2", "type": "edge_case", "split": "holdout", "prompt": "weekly report but quick social post", "expected_method": ""},
        ],
    }


def _baseline(repo: GrowthRepository) -> tuple[dict, dict, list[str]]:
    method = repo.create_method(MethodAsset(
        id="method-a", project_id="project-a", slug="weekly-report", name="Weekly report",
        status=MethodStatus.PUBLISHED, active_revision_id="baseline-a",
    ))
    baseline = repo.save_method_revision(MethodRevision(
        id="baseline-a", project_id="project-a", method_id=method["id"], version=1,
        body="# Weekly report baseline", manifest=_manifest(),
        eval_summary={"average_quality": 90, "groundedness": 0.95}, status=MethodStatus.PUBLISHED,
    ))
    output_ids: list[str] = []
    for index in range(3):
        output_id = f"output-{index}"
        output_ids.append(output_id)
        repo.register_output(OutputAsset(
            id=output_id, project_id="project-a", kind="report", content_hash=(chr(97 + index) * 64),
            vault_path=f"outputs/{output_id}.md", idempotency_key=f"run-{index}", run_id=f"run-{index}",
            method_revision_id=baseline["id"], status="accepted",
        ))
        repo.save_output_evaluation(OutputEvaluation(
            project_id="project-a", output_id=output_id, groundedness=0.95, task_fit=0.90,
            usefulness=0.90, coherence=0.90, format_quality=0.90,
            evaluator_revision=f"eval-{index}",
        ))
    return method, baseline, output_ids


def test_method_evolution_api_is_project_scoped_review_only_and_visible_in_run_ledger(evolution_api):
    client, repo = evolution_api
    method, baseline, output_ids = _baseline(repo)
    payload = {
        "candidate_body": "# Weekly report baseline\n\nAdd a concise executive synthesis.",
        "candidate_manifest": baseline["manifest"],
        "supporting_output_ids": output_ids,
        "mutation_dimension": "body",
        "rationale": "Add a concise executive synthesis while preserving all routing and evidence rules.",
        "idempotency_key": "api-experiment-1",
    }

    denied = client.post(
        f"/knowledge/projects/project-a/methods/{method['id']}/experiments",
        headers=_headers("growth-reader-key"),
        json=payload,
    )
    created = client.post(
        f"/knowledge/projects/project-a/methods/{method['id']}/experiments",
        headers=_headers(),
        json=payload,
    )
    assert denied.status_code == 403
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    experiment = body["experiment"]
    assert body["publication_status"] == "review_required"
    assert experiment["status"] == "eligible_for_review"
    assert repo.get_method("project-a", method["id"])["active_revision_id"] == baseline["id"]

    listed = client.get(
        f"/knowledge/projects/project-a/methods/{method['id']}/experiments",
        headers=_headers("growth-reader-key"),
    )
    read = client.get(
        f"/knowledge/projects/project-a/methods/experiments/{experiment['id']}",
        headers=_headers("growth-reader-key"),
    )
    runs = client.get("/knowledge/projects/project-a/runs", headers=_headers("growth-reader-key"))
    replay = client.post(
        f"/knowledge/projects/project-a/methods/{method['id']}/experiments",
        headers=_headers(),
        json=payload,
    )

    assert listed.status_code == read.status_code == runs.status_code == 200
    assert replay.status_code == 201
    assert listed.json()["data"]["experiments"][0]["id"] == experiment["id"]
    assert read.json()["data"]["experiment"]["candidate_proposal_id"] == experiment["candidate_proposal_id"]
    assert any(run["id"] == experiment["id"] and run["run_type"] == "method_evolution" for run in runs.json()["data"]["runs"])
    assert replay.json()["data"]["idempotent"] is True
