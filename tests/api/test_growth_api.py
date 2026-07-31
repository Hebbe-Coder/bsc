import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.growth_api as growth_api_module
from app.api.growth_api import _start_run, get_growth_repository
from app.core.config import settings
from app.knowledge.growth_contracts import (
    CandidateEvidenceAnchor,
    FeedbackType,
    KnowledgeCandidate,
    KnowledgeCandidateStatus,
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
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceRecord, SourceStatus
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


def test_project_sop_generation_endpoint_requires_writer_and_returns_durable_result(growth_api, monkeypatch):
    client, _repo = growth_api
    calls = []

    class FakeProjectSopService:
        def __init__(self, repo, vault_root):
            assert repo is _repo
            assert Path(vault_root) == Path(settings.OBSIDIAN_VAULT_ROOT)

        def generate(self, *, project_id, request, actor_id, trigger="http"):
            calls.append((project_id, request, actor_id, trigger))
            return {
                "run": {"id": "sop-run", "project_id": project_id, "status": "completed"},
                "output": {"id": "sop-output", "project_id": project_id, "status": "registered"},
                "idempotent": False,
            }

    monkeypatch.setattr(growth_api_module, "ProjectSopGenerationService", FakeProjectSopService)
    payload = {
        "prd_source_id": "prd-source",
        "goal": "Create a governed SOP for the active project delivery.",
        "audience": "project operators",
        "idempotency_key": "sop-api-test",
    }
    denied = client.post(
        "/knowledge/projects/project-a/outputs/generate-sop",
        headers=_headers("growth-reader-key"),
        json=payload,
    )
    created = client.post(
        "/knowledge/projects/project-a/outputs/generate-sop",
        headers=_headers(),
        json=payload,
    )

    assert denied.status_code == 403
    assert created.status_code == 201, created.text
    assert created.json()["data"]["output"]["status"] == "registered"
    assert calls[0][0] == "project-a"
    assert calls[0][1].prd_source_id == "prd-source"


def test_profile_source_policy_is_validated_revisioned_and_returned_by_the_api(growth_api):
    client, _repo = growth_api
    response = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={
            "expected_revision": 0,
            "source_policy": {
                "primary_origin_prefixes": ["https://research.example/"],
                "trusted_origin_prefixes": ["https://news.example/"],
                "community_origin_prefixes": ["https://community.example/"],
                "blocked_origin_prefixes": ["https://blocked.example/"],
                "trusted_source_types": ["manual_upload"],
                "require_triage_source_types": ["horizon_signal"],
                "primary_retention_days": 730,
                "trusted_retention_days": 365,
                "community_retention_days": 30,
                "untrusted_retention_days": 14,
            },
        },
    )

    assert response.status_code == 200, response.text
    profile = response.json()["data"]["profile"]
    assert profile["revision"] == 1
    assert profile["source_policy"]["primary_origin_prefixes"] == ["https://research.example/"]
    assert profile["source_policy"]["untrusted_retention_days"] == 14

    invalid = client.patch(
        "/knowledge/projects/project-a/profile",
        headers=_headers(),
        json={"expected_revision": 1, "source_policy": {"community_retention_days": 0}},
    )
    assert invalid.status_code == 422


def test_publish_api_cannot_bypass_a_failed_method_update_holdout(growth_api):
    client, repo = growth_api
    method = repo.create_method(MethodAsset(
        id="method-update-api",
        project_id="project-a",
        slug="weekly-report",
        name="Weekly report",
    ))
    proposal = repo.save_method_proposal(MethodProposal(
        id="method-update-proposal-api",
        project_id="project-a",
        method_id=method["id"],
        operation="update",
        body="# Candidate update",
        manifest={"task_family": "weekly-report", "prompt_only": True},
    ))
    repo.update_method_proposal_evaluation(
        "project-a",
        proposal["id"],
        {"eligible": True, "evolution": {"passed": False}, "findings": []},
        "approved",
    )

    response = client.post(
        f"/knowledge/projects/project-a/methods/proposals/{proposal['id']}/publish",
        headers=_headers(),
        json={},
    )

    assert response.status_code == 400
    assert "holdout" in response.json()["message"]["message"]
    audit = next(run for run in repo.list_runs("project-a") if run["run_type"] == "method_publish")
    assert audit["status"] == "failed"


def test_filed_outputs_remain_verified_in_summary_and_method_proposals(growth_api):
    client, repo = growth_api
    accepted = _output(repo, "project-a", "accepted", status="accepted")
    filed = _output(repo, "project-a", "filed", status="filed")
    second_accepted = _output(repo, "project-a", "accepted-two", status="accepted")
    _output(repo, "project-a", "rejected", status="rejected")

    summary = client.get("/knowledge/projects/project-a/growth/summary", headers=_headers())
    proposal = client.post(
        "/knowledge/projects/project-a/methods",
        headers=_headers(),
        json={
            "slug": "filed-output-method",
            "body": "# Verified method\nUse durable evidence.",
            "source_output_ids": [accepted["id"], filed["id"], second_accepted["id"]],
        },
    )

    assert summary.status_code == 200
    assert proposal.status_code == 201
    assert summary.json()["data"]["counts"]["outputs"] == 4
    assert summary.json()["data"]["counts"]["accepted_outputs"] == 3
    assert summary.json()["data"]["counts"]["rejected_outputs"] == 1
    assert filed["id"] in proposal.json()["data"]["proposal"]["source_output_ids"]


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


def test_source_method_distillation_endpoint_submits_a_project_scoped_detached_proposal_run(growth_api, monkeypatch):
    client, repo = growth_api
    source = repo.create_source(SourceRecord(
        id="source-distill-a",
        project_id="project-a",
        source_type="meeting_notes",
        origin="obsidian://project-a/note",
        content_hash="a" * 64,
        raw_content="Raw evidence must never return in the API response.",
        trust_level="reviewed",
        status=SourceStatus.ELIGIBLE,
    ))

    class FakeDistiller:
        def __init__(self, repository):
            self.repository = repository

        def submit(self, *, project_id, source_id, actor_id, trigger, candidate_ids):
            assert project_id == "project-a"
            assert source_id == source["id"]
            assert actor_id
            assert trigger == "http"
            assert candidate_ids == ["accepted-candidate-a"]
            return self.repository.create_run(KnowledgeRun(
                id="source-distillation-run",
                project_id=project_id,
                run_type="source_method_distillation",
                trigger=trigger,
                status=RunStatus.QUEUED,
                actor_id=actor_id,
            ))

    dispatched = []
    monkeypatch.setattr(growth_api_module, "SourceMethodDistillationService", FakeDistiller)
    monkeypatch.setattr(
        growth_api_module,
        "dispatch_source_method_distillation",
        lambda project_id, run_id, **_kwargs: dispatched.append((project_id, run_id)) or {"execution": "in_process", "task_id": "in-process:test"},
    )
    response = client.post(
        "/knowledge/projects/project-a/methods/distill",
        headers=_headers(),
        json={"source_id": source["id"], "candidate_ids": ["accepted-candidate-a"]},
    )
    denied = client.post(
        "/knowledge/projects/project-a/methods/distill",
        headers=_headers("growth-reader-key"),
        json={"source_id": source["id"], "candidate_ids": ["accepted-candidate-a"]},
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["publication_status"] == "proposal_only"
    assert data["run"]["id"] == "source-distillation-run"
    assert data["run"]["status"] == "queued"
    assert data["proposals"] == []
    assert data["execution"] == {"execution": "in_process", "task_id": "in-process:test"}
    assert dispatched == [("project-a", "source-distillation-run")]
    assert "Raw evidence" not in response.text
    assert denied.status_code == 403

    runs = client.get("/knowledge/projects/project-a/runs", headers=_headers())
    assert runs.status_code == 200
    assert runs.json()["data"]["runs"][0]["id"] == "source-distillation-run"


def test_candidate_extraction_endpoint_and_candidate_review_are_project_scoped(growth_api, monkeypatch):
    client, repo = growth_api
    raw_content = "An evidence ladder compares reliability before a decision is made."
    source = repo.create_source(SourceRecord(
        id="source-candidate-a",
        project_id="project-a",
        source_type="meeting_notes",
        origin="obsidian://project-a/candidate-note",
        content_hash=hashlib.sha256(raw_content.encode()).hexdigest(),
        raw_content=raw_content,
        trust_level="reviewed",
        status=SourceStatus.ELIGIBLE,
    ))

    class FakeExtractor:
        def __init__(self, repository):
            self.repository = repository

        def submit(self, *, project_id, source_id, actor_id, trigger):
            assert project_id == "project-a"
            assert source_id == source["id"]
            assert actor_id
            assert trigger == "http"
            return self.repository.create_run(KnowledgeRun(
                id="candidate-extraction-run",
                project_id=project_id,
                run_type="cangjie_candidate_extraction",
                trigger=trigger,
                status=RunStatus.QUEUED,
                actor_id=actor_id,
            ))

    dispatched = []
    monkeypatch.setattr(growth_api_module, "SourceCandidateExtractionService", FakeExtractor)
    monkeypatch.setattr(
        growth_api_module,
        "dispatch_source_candidate_extraction",
        lambda project_id, run_id, **_kwargs: dispatched.append((project_id, run_id)) or {
            "execution": "in_process", "task_name": "knowledge.candidate_extraction.execute", "task_id": "in-process:test"
        },
    )
    response = client.post(
        "/knowledge/projects/project-a/candidates/extract",
        headers=_headers(),
        json={"source_id": source["id"]},
    )
    denied = client.post(
        "/knowledge/projects/project-a/candidates/extract",
        headers=_headers("growth-reader-key"),
        json={"source_id": source["id"]},
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["publication_status"] == "review_only"
    assert response.json()["data"]["candidates"] == []
    assert dispatched == [("project-a", "candidate-extraction-run")]
    assert raw_content not in response.text
    assert denied.status_code == 403

    candidate = repo.save_candidate(KnowledgeCandidate(
        id="candidate-a",
        project_id="project-a",
        source_id=source["id"],
        source_content_hash=source["content_hash"],
        extraction_run_id="candidate-extraction-run",
        candidate_type="framework",
        title="Evidence ladder",
        claim="Compare source reliability before selecting a decision path.",
        evidence=[CandidateEvidenceAnchor(
            source_id=source["id"],
            content_hash=source["content_hash"],
            anchor="paragraph-1",
            quote=raw_content,
        )],
        fingerprint="b" * 64,
    ))
    listed = client.get("/knowledge/projects/project-a/candidates", headers=_headers("growth-reader-key"))
    detail = client.get(f"/knowledge/projects/project-a/candidates/{candidate['id']}", headers=_headers())
    summary = client.get("/knowledge/projects/project-a/growth/summary", headers=_headers())
    assert listed.status_code == detail.status_code == summary.status_code == 200
    assert listed.json()["data"]["candidates"][0]["id"] == candidate["id"]
    assert "evidence" not in listed.json()["data"]["candidates"][0]
    assert detail.json()["data"]["candidate"]["evidence"][0]["quote"] == raw_content
    assert summary.json()["data"]["counts"]["pending_candidates"] == 1

    reviewed = client.post(
        f"/knowledge/projects/project-a/candidates/{candidate['id']}/review",
        headers=_headers(),
        json={"decision": "accepted", "review_note": "Keep for later method selection."},
    )
    reader_review = client.post(
        f"/knowledge/projects/project-a/candidates/{candidate['id']}/review",
        headers=_headers("growth-reader-key"),
        json={"decision": "rejected"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["candidate"]["status"] == KnowledgeCandidateStatus.ACCEPTED.value
    assert reviewed.json()["data"]["publication_status"] == "review_only"
    assert reader_review.status_code == 403
    assert repo.list_methods("project-a") == []


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


def test_lineage_response_projects_readable_typed_nodes_without_evidence_bodies(growth_api):
    client, repo = growth_api
    source = _capture(repo, "project-a", "private immutable evidence body")
    repo.update_source_status("project-a", source["id"], SourceStatus.ELIGIBLE)
    output = _output(repo, "project-a", "lineage-node", status="registered")
    linked = client.post(
        f"/knowledge/projects/project-a/outputs/{output['id']}/evidence",
        headers=_headers(),
        json={"source_ids": [source["id"]], "page_ids": []},
    )
    assert linked.status_code == 200, linked.text

    response = client.get("/knowledge/growth/project-a/lineage", headers=_headers())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    nodes = {node["id"]: node for node in data["nodes"]}
    assert nodes[source["id"]] == {
        "id": source["id"],
        "type": "source",
        "label": "example.test signal",
        "status": "eligible",
    }
    assert nodes[output["id"]]["type"] == "output"
    assert nodes[output["id"]]["label"].endswith("/lineage-node.md")
    assert any(
        edge["from_id"] == source["id"]
        and edge["to_id"] == output["id"]
        and edge["from_type"] == "source"
        and edge["to_type"] == "output"
        for edge in data["edges"]
    )
    serialized = str(data)
    assert "private immutable evidence body" not in serialized
    assert "must-not-leak" not in serialized


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


def test_scheduler_availability_cache_is_scoped_to_broker_runtime_and_probes(monkeypatch):
    first_runtime = object()
    second_runtime = object()
    probes: list[str] = []

    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", True)
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://first.test:6379/0")
    monkeypatch.setattr(growth_api_module, "get_celery_app", lambda: first_runtime)
    monkeypatch.setattr(growth_api_module, "is_celery_real", lambda: True)
    monkeypatch.setattr(
        growth_api_module,
        "is_celery_broker_available",
        lambda: probes.append("first") or True,
    )
    growth_api_module._reset_scheduler_availability_cache()
    try:
        assert growth_api_module._scheduler_available() is True
        assert growth_api_module._scheduler_available() is True
        assert probes == ["first"]

        monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://second.test:6379/0")
        assert growth_api_module._scheduler_available() is True
        assert probes == ["first", "first"]

        monkeypatch.setattr(growth_api_module, "get_celery_app", lambda: second_runtime)
        assert growth_api_module._scheduler_available() is True
        assert probes == ["first", "first", "first"]

        monkeypatch.setattr(
            growth_api_module,
            "is_celery_broker_available",
            lambda: probes.append("replacement") or False,
        )
        assert growth_api_module._scheduler_available() is False
        assert probes == ["first", "first", "first", "replacement"]
    finally:
        growth_api_module._reset_scheduler_availability_cache()


def test_growth_distillation_api_shows_current_revision_until_history_is_requested(growth_api):
    client, repo = growth_api
    repo.configure_vault("project-a", "projects/project-a")
    path = "distillations/weekly/2026-W30/summary.md"
    old_hash = "a" * 64
    current_hash = "b" * 64
    FilesystemWikiVault(settings.OBSIDIAN_VAULT_ROOT, "project-a", "projects/project-a").commit({
        path: "# Current summary\n",
        "distillations/weekly/2026-W30/manifest.json": json.dumps({"input_hash": current_hash}),
        f"distillations/weekly/2026-W30/revisions/{old_hash}/summary.md": "# Archived summary\n",
    })
    old = repo.record_growth_distillation(
        project_id="project-a", period="2026-W30", kind="weekly", input_hash=old_hash, paths=[path], manifest={}
    )
    current = repo.record_growth_distillation(
        project_id="project-a", period="2026-W30", kind="weekly", input_hash=current_hash, paths=[path], manifest={}
    )

    listed = client.get("/knowledge/growth/project-a/distillations", headers=_headers())
    history = client.get("/knowledge/growth/project-a/distillations?include_history=true", headers=_headers())
    archived_detail = client.get(f"/knowledge/growth/project-a/distillations/{old['id']}", headers=_headers())
    current_detail = client.get(f"/knowledge/growth/project-a/distillations/{current['id']}", headers=_headers())

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["distillations"]] == [current["id"]]
    assert listed.json()["data"]["distillations"][0]["revision_count"] == 2
    assert history.status_code == 200
    history_by_id = {item["id"]: item for item in history.json()["data"]["distillations"]}
    assert set(history_by_id) == {old["id"], current["id"]}
    assert history_by_id[old["id"]]["current"] is False
    assert history_by_id[current["id"]]["current"] is True
    assert archived_detail.json()["data"]["distillation"]["current"] is False
    assert current_detail.json()["data"]["distillation"]["current"] is True


def test_idempotent_growth_run_persists_one_celery_assignment(monkeypatch, tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-idempotent-celery-assignment.db"))
    dispatched: list[list[str]] = []

    class QueuedTask:
        id = "growth-celery-task-123"

    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", True)
    monkeypatch.setattr(growth_api_module, "is_celery_real", lambda: True)
    monkeypatch.setattr(growth_api_module, "is_celery_broker_available", lambda: True)
    monkeypatch.setattr(
        "app.tasks.growth_tasks.growth_execute.apply_async",
        lambda args: dispatched.append(args) or QueuedTask(),
    )
    try:
        first = _start_run(
            repo,
            project_id="project-a",
            job_type="growth_daily",
            idempotency_key="growth-assignment-key",
            input_refs={"date": "2026-07-26"},
            actor_id="test-operator",
        )
        duplicate = _start_run(
            repo,
            project_id="project-a",
            job_type="growth_daily",
            idempotency_key="growth-assignment-key",
            input_refs={"date": "2026-07-26"},
            actor_id="test-operator",
        )

        assert first == {
            "status": "queued",
            "run_id": first["run_id"],
            "task_id": "growth-celery-task-123",
        }
        assert duplicate == {"status": "duplicate", "run_id": first["run_id"], "duplicate": True}
        assert dispatched == [["project-a", first["run_id"]]]
        events = repo.list_run_events(project_id="project-a", run_id=first["run_id"])
        assert [event["event_type"] for event in events] == [
            "knowledge.run.queued",
            "knowledge.run.execution_assigned",
            "knowledge.growth.dispatched",
        ]
        assert events[-1]["payload"] == {
            "execution": "celery",
            "task_name": "knowledge.growth.execute",
            "task_id": "growth-celery-task-123",
            "trigger": "http",
        }
    finally:
        repo.close()


def test_capture_attempt_ledger_is_project_scoped_and_excludes_raw_evidence(growth_api):
    client, repo = growth_api
    run = KnowledgeRun(project_id="project-a", run_type="horizon_capture", trigger="manual")
    repo.create_run(run)
    captured = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://news.example.test/agent-systems",
            raw_content="This raw evidence body must never be in the capture ledger API.",
            trust_level="trusted",
            capture_run_id=run.id,
        )
    )
    other_run = KnowledgeRun(project_id="project-b", run_type="horizon_capture", trigger="manual")
    repo.create_run(other_run)
    SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-b",
            source_type="horizon_signal",
            origin="https://news.example.test/other-project",
            raw_content="Other project evidence.",
            trust_level="trusted",
            capture_run_id=other_run.id,
        )
    )

    response = client.get(
        f"/knowledge/projects/project-a/capture-attempts?run_id={run.id}",
        headers=_headers(),
    )
    cross_project = client.get(
        f"/knowledge/projects/project-b/capture-attempts?run_id={run.id}",
        headers=_headers(),
    )
    runs = client.get("/knowledge/projects/project-a/runs", headers=_headers())

    assert response.status_code == cross_project.status_code == runs.status_code == 200
    payload = response.json()["data"]
    assert payload["pagination"]["count"] == 1
    attempt = payload["capture_attempts"][0]
    assert attempt["project_id"] == "project-a"
    assert attempt["run_id"] == run.id
    assert attempt["source_id"] == captured.source["id"]
    assert attempt["outcome"] == "captured"
    assert attempt["policy"]["reasons"] == ["explicit_trusted_source", "project_profile_triage_required"]
    assert attempt["policy"]["extraction_quality"] == "complete"
    assert "raw_content" not in attempt
    assert "This raw evidence body" not in response.text
    assert cross_project.json()["data"]["capture_attempts"] == []
    assert [item["id"] for item in runs.json()["data"]["runs"]] == [run.id]


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
