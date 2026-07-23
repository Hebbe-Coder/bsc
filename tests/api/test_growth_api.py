import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeLineageEdge,
    MethodAsset,
    MethodProposal,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputFeedback,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.wiki_contracts import KnowledgeRun, SourceStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.main import app


@pytest.fixture
def growth_api(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "API_KEY", "growth-admin-key")
    monkeypatch.setattr(settings, "API_KEY_READER", "growth-reader-key")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    Path(settings.OBSIDIAN_VAULT_ROOT).mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-api.db"))
    app.dependency_overrides[get_growth_repository] = lambda: repo
    client = TestClient(app)
    try:
        yield client, repo
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repo.close()


def _headers(key="growth-admin-key"):
    return {"Authorization": f"Bearer {key}"}


def _capture(repo: GrowthRepository, project_id: str, content: str = "evidence") -> dict:
    result = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id=project_id,
            source_type="web",
            origin="https://example.test/source",
            raw_content=content,
            trust_level="trusted",
            metadata={"api_key": "must-not-leak", "topic": "api"},
        )
    )
    repo.update_source_status(project_id, result.source["id"], SourceStatus.VALIDATED)
    return result.source


def _method(
    repo: GrowthRepository,
    project_id: str,
    slug: str,
    *,
    status: MethodStatus = MethodStatus.PUBLISHED,
    revision_count: int = 2,
) -> tuple[dict, list[dict]]:
    revision_ids = [f"{project_id}-{slug}-revision-{index}" for index in range(1, revision_count + 1)]
    method = repo.create_method(
        MethodAsset(
            project_id=project_id,
            slug=slug,
            name=slug.replace("-", " ").title(),
            status=status,
            active_revision_id=revision_ids[-1] if revision_ids else "",
        )
    )
    revisions = [
        repo.save_method_revision(
            MethodRevision(
                id=revision_id,
                project_id=project_id,
                method_id=method["id"],
                version=index,
                body=f"# {slug} v{index}",
                status=MethodStatus.PUBLISHED,
            )
        )
        for index, revision_id in enumerate(revision_ids, start=1)
    ]
    return method, revisions


def _output(repo: GrowthRepository, project_id: str, key: str, *, status: str) -> dict:
    if not repo.get_vault(project_id):
        repo.configure_vault(project_id, f"projects/{project_id}", "test")
    content = f"{project_id}-{key}".encode()
    return OutputRegistry(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).register_content(
        OutputAsset(
            project_id=project_id,
            kind="report",
            content_hash=hashlib.sha256(content).hexdigest(),
            vault_path=f"outputs/2026/{key}.md",
            idempotency_key=f"{project_id}-{key}",
            status=status,
            metadata={
                "goal": "test filing",
                "audience": "test",
                "channel": "api",
                "generator": "pytest",
                "provider": "local",
                "model": "none",
                "prompt_revision": "v1",
            },
        ),
        content,
    )


def test_canonical_profile_summary_and_legacy_alias(growth_api):
    client, _repo = growth_api
    patched = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={"expected_revision": 0, "user_role": "researcher", "target_audiences": ["operators"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["availability"]["growth"] is True

    canonical = client.get("/knowledge/projects/project-a/profile", headers=_headers())
    legacy = client.get("/knowledge/growth/project-a/profile", headers=_headers())
    summary = client.get("/knowledge/projects/project-a/growth/summary", headers=_headers())

    assert canonical.status_code == legacy.status_code == summary.status_code == 200
    assert canonical.json()["data"]["profile"]["user_role"] == "researcher"
    assert legacy.json()["data"]["profile"]["revision"] == canonical.json()["data"]["profile"]["revision"]
    assert summary.json()["data"]["counts"]["sources"] == 0
    assert summary.json()["data"]["counts"]["review_records"] == 0


def test_assets_are_paginated_bounded_and_redacted(growth_api):
    client, repo = growth_api
    _capture(repo, "project-a", "secret body sk-1234567890")

    page = client.get(
        "/knowledge/projects/project-a/growth/assets",
        headers=_headers(),
        params={"stage": "A", "limit": 1},
    )
    over_limit = client.get(
        "/knowledge/projects/project-a/growth/assets",
        headers=_headers(),
        params={"stage": "A", "limit": 501},
    )
    invalid_stage = client.get(
        "/knowledge/projects/project-a/growth/assets",
        headers=_headers(),
        params={"stage": "invalid"},
    )

    assert page.status_code == 200, page.text
    body = page.json()["data"]
    assert body["pagination"] == {"limit": 1, "cursor": None, "next_cursor": None, "count": 1}
    assert "raw_content" not in body["items"][0]
    assert body["items"][0]["metadata"]["api_key"] == "[REDACTED]"
    assert "sk-1234567890" not in page.text
    assert over_limit.status_code == invalid_stage.status_code == 422


def test_method_candidates_are_visible_and_reviewable_in_growth_review_queue(growth_api):
    client, repo = growth_api
    proposal = repo.save_method_proposal(
        MethodProposal(
            id="method-proposal-a",
            project_id="project-a",
            operation="create",
            body="# Evidence brief\nUse the verified project evidence.",
            manifest={"task_family": "evidence-brief"},
            source_output_ids=["output-a", "output-b", "output-c"],
            rationale="Three comparable accepted outputs",
        )
    )

    review = client.get(
        "/knowledge/projects/project-a/growth/assets",
        headers=_headers(),
        params={"stage": "review"},
    )
    detail = client.get(
        f"/knowledge/projects/project-a/methods/proposals/{proposal['id']}",
        headers=_headers(),
    )
    summary = client.get(
        "/knowledge/projects/project-a/growth/summary",
        headers=_headers(),
    )

    assert review.status_code == detail.status_code == summary.status_code == 200
    candidate = next(item for item in review.json()["data"]["items"] if item["id"] == proposal["id"])
    assert candidate["asset_type"] == "method_proposal"
    assert candidate["task_family"] == "evidence-brief"
    assert "body" not in candidate
    assert detail.json()["data"]["proposal"]["body"] == proposal["body"]
    assert summary.json()["data"]["counts"]["method_proposals"] == 1
    assert summary.json()["data"]["counts"]["review_records"] == 1


def test_reader_can_read_but_cannot_mutate(growth_api):
    client, _repo = growth_api
    read = client.get("/knowledge/projects/project-a/profile", headers=_headers("growth-reader-key"))
    write = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers("growth-reader-key"),
        json={"expected_revision": 0, "user_role": "writer"},
    )
    assert read.status_code == 200
    assert write.status_code == 403
    assert write.json()["message"]["code"] == "growth_permission_denied"


def test_profile_patch_requires_database_revision_precondition(growth_api):
    client, repo = growth_api
    first = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={"expected_revision": 0, "user_role": "first-writer"},
    )
    stale = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={"expected_revision": 0, "user_role": "stale-writer"},
    )
    missing = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={"user_role": "missing-precondition"},
    )

    assert first.status_code == 200
    assert first.json()["data"]["profile"]["revision"] == 1
    assert stale.status_code == 409
    assert stale.json()["message"]["code"] == "growth_revision_conflict"
    assert missing.status_code == 422
    assert repo.get_profile("project-a")["user_role"] == "first-writer"

    def update(role):
        return client.patch(
            "/knowledge/projects/project-a/profile",
            headers=_headers(),
            json={"expected_revision": 1, "user_role": role},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent = list(executor.map(update, ["concurrent-a", "concurrent-b"]))

    assert sorted(response.status_code for response in concurrent) == [200, 409]
    conflict = next(response for response in concurrent if response.status_code == 409)
    assert conflict.json()["message"]["code"] == "growth_revision_conflict"
    assert repo.get_profile("project-a")["revision"] == 2


def test_sources_triage_methods_outputs_feedback_and_review_are_project_scoped(growth_api):
    client, repo = growth_api
    source = _capture(repo, "project-a")
    other_source = _capture(repo, "project-b")

    triage = client.post(
        f"/knowledge/projects/project-a/sources/{source['id']}/triage",
        headers=_headers(),
    )
    cross = client.post(
        f"/knowledge/projects/project-a/sources/{other_source['id']}/triage",
        headers=_headers(),
    )
    assert triage.status_code == 200, triage.text
    assert cross.status_code == 404
    assert cross.json()["message"]["code"] == "growth_resource_not_found"

    output_ids = []
    for index in range(3):
        output = repo.register_output(
            OutputAsset(
                project_id="project-a",
                kind="report",
                content_hash=hashlib.sha256(f"output-{index}".encode()).hexdigest(),
                vault_path=f"outputs/{index}.md",
                idempotency_key=f"output-{index}",
                status="accepted",
                source_refs=[source["id"]],
            )
        )
        output_ids.append(output["id"])

    proposed = client.post(
        "/knowledge/projects/project-a/methods",
        headers=_headers(),
        json={
            "slug": "research-brief",
            "body": "Use evidence and produce a concise brief.",
            "source_output_ids": output_ids,
            "manifest": {"prompt_only": True},
        },
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["data"]["publication_status"] == "proposal_only"

    outputs = client.get(
        "/knowledge/projects/project-a/outputs",
        headers=_headers(),
        params={"limit": 2},
    )
    assert outputs.status_code == 200
    assert outputs.json()["data"]["pagination"]["next_cursor"] == "2"

    feedback = client.post(
        f"/knowledge/projects/project-a/outputs/{output_ids[0]}/feedback",
        headers=_headers(),
        json={"feedback_type": "accepted", "comment": "useful"},
    )
    assert feedback.status_code == 201, feedback.text
    feedback_id = feedback.json()["data"]["feedback"]["id"]
    reviewed = client.post(
        "/knowledge/projects/project-a/growth/review",
        headers=_headers(),
        json={"target_type": "feedback", "target_id": feedback_id},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["review"]["feedback_id"] == feedback_id


def test_external_output_must_link_eligible_project_evidence_before_quality_review(growth_api):
    client, repo = growth_api
    source = _capture(repo, "project-a", "source supporting the plugin export")
    repo.update_source_status("project-a", source["id"], SourceStatus.ELIGIBLE)
    other_source = _capture(repo, "project-b", "private source")
    repo.update_source_status("project-b", other_source["id"], SourceStatus.ELIGIBLE)
    output = repo.register_output(
        OutputAsset(
            id="external-plugin-output",
            project_id="project-a",
            kind="external_plugin_output",
            title="Plugin research draft",
            content_hash=hashlib.sha256(b"plugin-output").hexdigest(),
            vault_path="outputs/2026/plugin-research.md",
            idempotency_key="external-plugin-output",
            metadata={"origin": "external", "obsidian_plugin": "web-clipper"},
        )
    )
    immutable_before = {
        key: output[key]
        for key in ("content_hash", "vault_path", "idempotency_key", "source_refs", "page_refs")
    }
    components = {
        "groundedness": 0.9,
        "task_fit": 0.9,
        "usefulness": 0.9,
        "coherence": 0.9,
        "format_quality": 0.9,
        "findings": ["Claim coverage matches the linked source."],
    }

    unlinked_review = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evaluate",
        headers=_headers(),
        json=components,
    )
    cross_project = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evidence",
        headers=_headers(),
        json={"source_ids": [other_source["id"]], "page_ids": []},
    )
    reader_link = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evidence",
        headers=_headers("growth-reader-key"),
        json={"source_ids": [source["id"]], "page_ids": []},
    )

    assert unlinked_review.status_code == 400
    assert "external evidence ancestry" in unlinked_review.json()["message"]["message"]
    assert cross_project.status_code == 404
    assert reader_link.status_code == 403

    linked = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evidence",
        headers=_headers(),
        json={"source_ids": [source["id"], source["id"]], "page_ids": []},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["data"]["output"]["source_refs"] == []
    assert linked.json()["data"]["evidence"]["source_ids"] == [source["id"]]
    assert repo.get_output("project-a", output["id"])["updated_at"] == output["updated_at"]

    reviewed = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evaluate",
        headers=_headers(),
        json=components,
    )
    locked = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evidence",
        headers=_headers(),
        json={"source_ids": [source["id"]], "page_ids": []},
    )

    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["evaluation"]["quality"] == 90
    assert repo.get_output("project-a", output["id"])["status"] == "accepted"
    assert {key: repo.get_output("project-a", output["id"])[key] for key in immutable_before} == immutable_before
    assert locked.status_code == 409
    detail = client.get(
        f"/knowledge/projects/project-a/outputs/{output['id']}", headers=_headers()
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["evidence"]["source_ids"] == [source["id"]]
    edges = repo.list_lineage("project-a", relation="output_used_source")
    assert any(edge["from_id"] == source["id"] and edge["to_id"] == output["id"] for edge in edges)


def test_method_revisions_are_paginated_readable_and_project_scoped(growth_api):
    client, repo = growth_api
    method, revisions = _method(repo, "project-a", "revision-history")
    other, _ = _method(repo, "project-b", "private-history", revision_count=1)

    first = client.get(
        f"/knowledge/projects/project-a/methods/{method['id']}/revisions",
        headers=_headers("growth-reader-key"),
        params={"limit": 1},
    )
    second = client.get(
        f"/knowledge/projects/project-a/methods/{method['id']}/revisions",
        headers=_headers("growth-reader-key"),
        params={"limit": 1, "cursor": "1"},
    )
    cross = client.get(
        f"/knowledge/projects/project-a/methods/{other['id']}/revisions",
        headers=_headers(),
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["pagination"]["next_cursor"] == "1"
    returned = [
        first.json()["data"]["revisions"][0]["id"],
        second.json()["data"]["revisions"][0]["id"],
    ]
    assert returned == [revisions[1]["id"], revisions[0]["id"]]
    assert cross.status_code == 404
    assert cross.json()["message"]["code"] == "growth_resource_not_found"


def test_deprecate_and_file_enforce_state_idempotency_scope_and_immutability(growth_api):
    client, repo = growth_api
    published, _ = _method(repo, "project-a", "published-method")
    candidate, _ = _method(
        repo,
        "project-a",
        "candidate-method",
        status=MethodStatus.CANDIDATE,
        revision_count=0,
    )
    other_method, _ = _method(repo, "project-b", "other-method")
    accepted = _output(repo, "project-a", "accepted", status="accepted")
    registered = _output(repo, "project-a", "registered", status="registered")
    other_output = _output(repo, "project-b", "other", status="accepted")
    immutable_before = {
        key: accepted[key]
        for key in ("id", "project_id", "content_hash", "vault_path", "idempotency_key")
    }

    deprecated = client.post(
        f"/knowledge/projects/project-a/methods/{published['id']}/deprecate",
        headers=_headers(),
        json={"reason": "superseded by the reviewed workflow"},
    )
    repeated_deprecation = client.post(
        f"/knowledge/projects/project-a/methods/{published['id']}/deprecate",
        headers=_headers(),
        json={"reason": "safe retry"},
    )
    invalid_deprecation = client.post(
        f"/knowledge/projects/project-a/methods/{candidate['id']}/deprecate",
        headers=_headers(),
        json={"reason": "candidate cannot be deprecated"},
    )
    cross_deprecation = client.post(
        f"/knowledge/projects/project-a/methods/{other_method['id']}/deprecate",
        headers=_headers(),
        json={"reason": "must not cross projects"},
    )
    reader_deprecation = client.post(
        f"/knowledge/projects/project-a/methods/{candidate['id']}/deprecate",
        headers=_headers("growth-reader-key"),
        json={"reason": "reader write"},
    )

    filed = client.post(
        f"/knowledge/projects/project-a/outputs/{accepted['id']}/file",
        headers=_headers(),
        json={"reason": "approved for the durable output collection"},
    )
    repeated_filing = client.post(
        f"/knowledge/projects/project-a/outputs/{accepted['id']}/file",
        headers=_headers(),
        json={"reason": "safe retry"},
    )
    invalid_filing = client.post(
        f"/knowledge/projects/project-a/outputs/{registered['id']}/file",
        headers=_headers(),
        json={"reason": "not accepted"},
    )
    cross_filing = client.post(
        f"/knowledge/projects/project-a/outputs/{other_output['id']}/file",
        headers=_headers(),
        json={"reason": "must not cross projects"},
    )
    reader_filing = client.post(
        f"/knowledge/projects/project-a/outputs/{registered['id']}/file",
        headers=_headers("growth-reader-key"),
        json={"reason": "reader write"},
    )
    missing_reason = client.post(
        f"/knowledge/projects/project-a/outputs/{registered['id']}/file",
        headers=_headers(),
        json={},
    )

    assert deprecated.status_code == repeated_deprecation.status_code == 200
    assert deprecated.json()["data"]["method"]["status"] == "deprecated"
    assert deprecated.json()["data"]["idempotent"] is False
    assert repeated_deprecation.json()["data"]["idempotent"] is True
    assert invalid_deprecation.status_code == 409
    assert invalid_deprecation.json()["message"]["code"] == "growth_state_conflict"
    assert cross_deprecation.status_code == 404
    assert reader_deprecation.status_code == 403

    assert filed.status_code == repeated_filing.status_code == 200
    assert filed.json()["data"]["output"]["status"] == "filed"
    assert filed.json()["data"]["idempotent"] is False
    assert repeated_filing.json()["data"]["idempotent"] is True
    target = (
        Path(settings.OBSIDIAN_VAULT_ROOT)
        / "projects"
        / "project-a"
        / Path(filed.json()["data"]["output"]["vault_path"])
    )
    assert target.read_bytes() == b"project-a-accepted"
    assert {
        key: repo.get_output("project-a", accepted["id"])[key]
        for key in immutable_before
    } == immutable_before
    assert invalid_filing.status_code == 409
    assert invalid_filing.json()["message"]["code"] == "growth_state_conflict"
    assert cross_filing.status_code == 404
    assert reader_filing.status_code == 403
    assert missing_reason.status_code == 422

    lifecycle_runs = {
        run["run_type"]: run
        for run in repo.list_runs("project-a", limit=500)
        if run["run_type"] in {"method_deprecate", "output_file"}
    }
    assert set(lifecycle_runs) == {"method_deprecate", "output_file"}
    assert lifecycle_runs["method_deprecate"]["input_refs"]["reason"] == (
        "superseded by the reviewed workflow"
    )
    assert lifecycle_runs["output_file"]["input_refs"]["reason"] == (
        "approved for the durable output collection"
    )
    assert lifecycle_runs["method_deprecate"]["actor_id"]
    assert lifecycle_runs["output_file"]["actor_id"]


def test_output_content_preview_is_hash_verified_and_project_scoped(growth_api):
    client, repo = growth_api
    output = _output(repo, "project-a", "preview", status="accepted")

    preview = client.get(
        f"/knowledge/projects/project-a/outputs/{output['id']}/content",
        headers=_headers("growth-reader-key"),
    )
    cross = client.get(
        f"/knowledge/projects/project-b/outputs/{output['id']}/content",
        headers=_headers(),
    )

    assert preview.status_code == 200, preview.text
    descriptor = preview.json()["data"]["content"]
    assert descriptor["render_mode"] == "text"
    assert descriptor["content"] == "project-a-preview"
    assert descriptor["content_hash"] == output["content_hash"]
    assert cross.status_code == 404


def test_lineage_returns_exact_endpoint_types_and_review_total(growth_api):
    client, repo = growth_api
    source = _capture(repo, "project-a")
    output = _output(repo, "project-a", "typed-lineage", status="accepted")
    repo.add_lineage_edge(
        KnowledgeLineageEdge(
            project_id="project-a",
            from_type="source",
            from_id=source["id"],
            to_type="output",
            to_id=output["id"],
            relation="output_used_source",
        )
    )
    repo.add_output_feedback(
        OutputFeedback(
            project_id="project-a",
            output_id=output["id"],
            feedback_type=FeedbackType.ACCEPTED,
        )
    )

    lineage = client.get(
        "/knowledge/projects/project-a/growth/lineage",
        headers=_headers(),
    )
    summary = client.get(
        "/knowledge/projects/project-a/growth/summary",
        headers=_headers(),
    )

    assert lineage.status_code == 200, lineage.text
    edge = next(
        item
        for item in lineage.json()["data"]["edges"]
        if item["edge_type"] == "output_used_source"
    )
    assert (edge["from_type"], edge["to_type"]) == ("source", "output")
    assert summary.json()["data"]["counts"]["review_records"] == 1


def test_schedules_runs_and_distillations_are_truthful(growth_api, monkeypatch):
    client, repo = growth_api
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)

    schedules = client.get("/knowledge/projects/project-a/schedules", headers=_headers())
    create_schedule = client.post(
        "/knowledge/projects/project-a/schedules",
        headers=_headers(),
        json={"job_type": "growth_daily", "cron": "0 17 * * *", "timezone": "Asia/Shanghai"},
    )
    run = client.post(
        "/knowledge/projects/project-a/runs",
        headers=_headers(),
        json={"job_type": "growth_daily", "idempotency_key": "manual-1"},
    )
    assert schedules.status_code == 200
    assert schedules.json()["data"]["availability"]["scheduler"] is False
    assert create_schedule.status_code == 503
    assert create_schedule.json()["message"]["code"] == "growth_dependency_unavailable"
    assert run.status_code == 200
    assert run.json()["data"]["run"]["status"] == "unavailable"
    assert repo.get_run("project-a", run.json()["data"]["run"]["run_id"])["status"] == "unavailable"


def test_disabled_route_and_invalid_encoding_use_stable_errors(growth_api, monkeypatch):
    client, _repo = growth_api
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", False)
    disabled = client.get("/knowledge/projects/project-a/profile", headers=_headers())
    assert disabled.status_code == 503
    assert disabled.json()["message"] == {
        "code": "knowledge_growth_disabled",
        "message": "Knowledge growth is disabled by configuration",
        "availability": {"growth": False},
    }

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    invalid = client.post(
        "/knowledge/projects/project-a/outputs",
        headers=_headers(),
        json={
            "kind": "report",
            "content_hash": "0" * 64,
            "vault_path": "outputs/test.md",
            "idempotency_key": "invalid-base64",
            "content_base64": "!not-base64!",
        },
    )
    assert invalid.status_code == 400
    assert invalid.json()["message"]["code"] == "invalid_output_encoding"
