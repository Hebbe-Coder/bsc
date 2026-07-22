"""End-to-end proof for the governed A -> B -> C -> D growth lifecycle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.feedback_router import FeedbackRouter
from app.knowledge.feishu_import import FeishuImportService
from app.knowledge.growth_context import GrowthContextBuilder
from app.knowledge.growth_contracts import FeedbackType, OutputAsset, OutputFeedback, ProjectKnowledgeProfile
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry
from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.horizon_run_store import HorizonRunStoreClient
from app.knowledge.knowledge_health import KnowledgeHealthService
from app.knowledge.output_evaluator import OutputEvaluator
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGate
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.main import app


FIXTURES = Path(__file__).parents[1] / "fixtures" / "abcd_growth"


def _fixture_json(relative: str) -> dict:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def _capture_primary_source(repo: GrowthRepository, project_id: str) -> tuple[dict, bool]:
    article = _fixture_json("sources/article.json")
    metadata = {
        **article["scores"],
        "published_at": article["published_at"],
        "title": article["title"],
        "source_revision": "article-v1",
    }
    service = SourceCaptureService(repo)
    first = service.capture(
        CapturedSourceInput(
            project_id=project_id,
            source_type="browser_clip",
            origin=article["origin"],
            raw_content=article["content"],
            trust_level="trusted",
            metadata=metadata,
        )
    )
    duplicate = service.capture(
        CapturedSourceInput(
            project_id=project_id,
            source_type="browser_clip",
            origin=article["origin"],
            raw_content=article["content"],
            trust_level="trusted",
            metadata=metadata,
        )
    )
    assert duplicate.source["id"] == first.source["id"]
    return first.source, duplicate.created


def _publish_wiki(repo: GrowthRepository, project_id: str, source_id: str, rules: str) -> tuple[dict, InMemoryWikiVault]:
    initial = {
        "AGENTS.md": rules,
        "wiki/overview.md": "---\ntitle: Overview\nkind: brief\nstatus: active\ncitations: []\n---\n# Overview\n",
        "wiki/index.md": "---\ntitle: Index\nkind: index\nstatus: active\ncitations: []\n---\n# Index\n",
        "wiki/log.md": "---\ntitle: Log\nkind: index\nstatus: active\ncitations: []\n---\n# Log\n",
    }
    repo.record_publication(project_id=project_id, contents=initial, source_ids=[])
    concept = (
        "---\n"
        "title: Evidence-led growth\n"
        "kind: concept\n"
        "status: active\n"
        f"citations: [{source_id}]\n"
        "---\n"
        "# Evidence-led growth\n\n"
        f"Project-specific evidence and governed feedback improve reusable methods. [source:{source_id}]\n"
    )
    proposal = WikiProposal(
        project_id=project_id,
        source_ids=[source_id],
        operations=[
            WikiOperation(operation=WikiOperationType.CREATE, path="wiki/concepts/evidence-led-growth.md", content=concept, source_ids=[source_id]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/overview.md", content=f"\n- [[wiki/concepts/evidence-led-growth.md]] [source:{source_id}]\n", source_ids=[source_id]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/index.md", content="\n- [[wiki/concepts/evidence-led-growth.md]]\n", source_ids=[source_id]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/log.md", content=f"\n- Added evidence-led growth. [source:{source_id}]\n", source_ids=[source_id]),
        ],
    )
    repo.create_proposal(proposal, actor_id="project-admin")
    WikiEvaluator(repo).save_case(
        project_id=project_id,
        case_id="growth-source-citation",
        case_type="citation",
        expected={"source_ids": [source_id]},
    )
    vault = InMemoryWikiVault(initial)
    result = ProposalGate(repo, vault).publish(
        proposal=proposal,
        rules_text=rules,
        actor_id="project-admin",
        actor_role="admin",
    )
    assert result["status"] == "published"
    return proposal.model_dump(mode="json"), vault


def _register_evaluated_output(
    repo: GrowthRepository,
    vault_root: Path,
    *,
    project_id: str,
    sequence: int,
    source_id: str,
    page_id: str,
    accepted: bool = True,
) -> dict:
    content = f"# Project-specific SOP {sequence}\n\nEvidence: [source:{source_id}]\n".encode()
    run_id = f"run-{sequence}"
    repo.create_run(KnowledgeRun(id=run_id, project_id=project_id, run_type="prd_to_sop", trigger="integration"))
    repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs={"kind": "sop"})
    output = OutputAsset(
        project_id=project_id,
        kind="sop",
        title=f"Project SOP {sequence}",
        content_hash=hashlib.sha256(content).hexdigest(),
        vault_path=f"outputs/2026/fixture-{sequence}/sop.md",
        run_id=run_id,
        context_revision=f"context-{sequence}",
        source_refs=[source_id],
        page_refs=[page_id],
        idempotency_key=f"run-{sequence}|sop",
        metadata={
            "task_family": "prd-to-sop",
            "goal": "Convert a project PRD into an evidence-backed SOP",
            "audience": "AI product operators",
            "channel": "Obsidian",
            "generator": "integration-fixture",
            "provider": "deterministic",
            "model": "fixture-v1",
            "prompt_revision": "prd-to-sop-v1",
            "method_candidate": {
                "body": "# Evidence-led PRD to SOP\n\n1. Load profile.\n2. Resolve evidence.\n3. Mark assumptions.\n",
                "manifest": {
                    "name": "Evidence-led PRD to SOP",
                    "prompt_only": True,
                    "task_family": "prd-to-sop",
                    "inputs": ["prd", "profile", "evidence"],
                    "outputs": ["sop"],
                    "evidence_rules": ["cite eligible A or published B"],
                    "failure_handling": ["emit research gap"],
                },
            },
        },
    )
    registered = OutputRegistry(repo, vault_root).register_content(output, content)
    components = (
        {"groundedness": 0.96, "task_fit": 0.93, "usefulness": 0.92, "coherence": 0.90, "format_quality": 0.88}
        if accepted
        else {"groundedness": 0.20, "task_fit": 0.40, "usefulness": 0.35, "coherence": 0.50, "format_quality": 0.60}
    )
    evaluation = OutputEvaluator(repo).evaluate(
        project_id=project_id,
        output_id=registered["id"],
        components=components,
        findings=[] if accepted else ["unsupported claims", "failed task fit"],
    )
    resolved = repo.get_output(project_id, registered["id"])
    assert resolved is not None
    assert resolved["status"] == ("accepted" if accepted else "rejected")
    assert evaluation["quality"] >= 85 if accepted else evaluation["quality"] < 60
    return resolved


def test_complete_project_specific_a_to_d_growth_lifecycle(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-e2e.db"))
    rules = (FIXTURES / "project-a" / "AGENTS.md").read_text(encoding="utf-8")
    try:
        repo.configure_vault("project-a", "projects/project-a", "project-admin")
        repo.configure_vault("project-b", "projects/project-b", "project-admin")
        profile = repo.save_profile(
            ProjectKnowledgeProfile(
                project_id="project-a",
                research_domains=["AI knowledge operations"],
                user_role="product operator",
                primary_output_types=["sop", "weekly_report"],
                target_audiences=["AI product operators"],
                preferred_channels=["Obsidian"],
                content_voice="evidence-led and operational",
            ),
            actor_id="project-admin",
        )
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-b", user_role="compliance reviewer"), actor_id="project-admin")

        source, duplicate_created = _capture_primary_source(repo, "project-a")
        assert duplicate_created is False
        triage = SourceTriageService(repo).triage_source("project-a", source["id"])
        assert triage["profile_revision"] == profile["revision"]
        assert triage["priority"] >= 80
        assert triage["reliability_pass"] in {1, True}
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"

        _publish_wiki(repo, "project-a", source["id"], rules)
        page = next(page for page in repo.list_pages("project-a") if page["path"].endswith("evidence-led-growth.md"))
        assert repo.list_citations("project-a", page["id"])[0]["source_id"] == source["id"]
        immutable_source = repo.get_source("project-a", source["id"])
        assert immutable_source["raw_content"] == _fixture_json("sources/article.json")["content"]
        assert immutable_source["status"] == "processed"

        outputs = [
            _register_evaluated_output(
                repo,
                vault_root,
                project_id="project-a",
                sequence=index,
                source_id=source["id"],
                page_id=page["id"],
            )
            for index in range(1, 4)
        ]
        rejected = _register_evaluated_output(
            repo,
            vault_root,
            project_id="project-a",
            sequence=9,
            source_id=source["id"],
            page_id=page["id"],
            accepted=False,
        )
        rejected_feedback = repo.add_output_feedback(
            OutputFeedback(
                project_id="project-a",
                output_id=rejected["id"],
                feedback_type=FeedbackType.REJECTED,
                actor_id="project-admin",
                comment="Do not reuse unsupported claims.",
            )
        )
        assert FeedbackRouter(repo).process("project-a", rejected_feedback["id"])["route"] == "failure_pattern"

        proposals = MethodDetector(repo).detect("project-a")
        assert len(proposals) == 1
        method_eval = MethodEvaluator(repo).evaluate(
            proposals[0],
            comparable_uses=3,
            average_quality=91,
            groundedness=0.96,
        )
        assert method_eval["eligible"] is True, method_eval
        method = MethodGate(repo, MethodRegistry(repo, vault_root)).publish_prompt_method(
            project_id="project-a",
            proposal_id=proposals[0]["id"],
            actor_id="system-admin",
            policy_allows=True,
        )
        revision = repo.get_method_revision("project-a", method["active_revision_id"])
        assert revision and revision["status"] == "published"

        page_content = repo.get_page_content("project-a", page["id"])
        context = GrowthContextBuilder().build(
            project_id="project-a",
            profile=repo.get_profile("project-a") or {},
            rules=rules,
            task="Convert the project PRD into a tailored operating SOP",
            pages=[{**page, "content": page_content["content"]}],
            sources=[repo.get_source("project-a", source["id"])],
            methods=[revision],
            outputs=outputs,
            evaluations=repo.list_output_evaluations("project-a"),
        )
        assert context.profile_revision == profile["revision"]
        assert f"source:{source['id']}" in context.provenance
        assert f"method:{revision['id']}" in context.provenance
        assert context.character_count <= 12_000

        final_content = b"# Tailored SOP\n\nUses the governed growth context and exact method revision.\n"
        repo.create_run(
            KnowledgeRun(
                id="run-final-sop",
                project_id="project-a",
                run_type="prd_to_sop",
                trigger="integration",
            )
        )
        repo.update_run_status(
            "project-a", "run-final-sop", RunStatus.COMPLETED, output_refs={"kind": "sop"}
        )
        final_output = OutputRegistry(repo, vault_root).register_content(
            OutputAsset(
                project_id="project-a",
                kind="sop",
                title="Tailored knowledge operations SOP",
                content_hash=hashlib.sha256(final_content).hexdigest(),
                vault_path="outputs/2026/final-sop/sop.md",
                run_id="run-final-sop",
                method_revision_id=revision["id"],
                context_revision=context.revision,
                source_refs=[source["id"]],
                page_refs=[page["id"]],
                idempotency_key="run-final-sop|sop",
                metadata={
                    "goal": "Convert PRD to project-specific SOP",
                    "audience": "AI product operators",
                    "channel": "Obsidian",
                    "generator": "growth-context",
                    "provider": "deterministic",
                    "model": "deterministic-fixture",
                    "prompt_revision": "growth-context-v1",
                    "assumptions": list(context.assumptions),
                    "context_hash": context.revision,
                },
            ),
            final_content,
        )
        assert final_output["method_revision_id"] == revision["id"]
        assert final_output["context_revision"] == context.revision
        assert len(repo.list_lineage("project-a")) >= 8
        assert repo.list_sources("project-a") == [immutable_source]

        monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
        monkeypatch.setattr(settings, "API_KEY", "growth-e2e-key")
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        app.dependency_overrides[get_growth_repository] = lambda: repo
        client = TestClient(app, headers={"Authorization": "Bearer growth-e2e-key"})
        summary = client.get("/knowledge/growth/project-a/summary")
        assets = client.get("/knowledge/growth/project-a/assets", params={"stage": "D", "limit": 100})
        assert summary.status_code == 200
        assert summary.json()["data"]["counts"]["accepted_outputs"] >= 3
        assert assets.status_code == 200
        assert any(item["id"] == final_output["id"] for item in assets.json()["data"]["items"])
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repo.close()


def test_binary_fixture_is_materialized_byte_for_byte_without_touching_original(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "binary.db"))
    original = FIXTURES / "binary" / "research-brief.pdf"
    before = original.read_bytes()
    try:
        repo.configure_vault("project-a", "projects/project-a", "project-admin")
        registered = OutputRegistry(repo, vault_root).register_content(
            OutputAsset(
                project_id="project-a",
                kind="presentation",
                title="Research brief",
                mime_type="application/pdf",
                content_hash=hashlib.sha256(before).hexdigest(),
                vault_path="outputs/2026/research-brief/research-brief.pdf",
                idempotency_key="fixture|research-brief-pdf",
                metadata={
                    "goal": "Preserve the original binary research brief",
                    "audience": "project reviewers",
                    "channel": "Obsidian",
                    "generator": "explicit-adoption",
                    "provider": "local",
                    "model": "none",
                    "prompt_revision": "not-applicable",
                },
            ),
            before,
            original_path=str(original),
        )
        materialized = vault_root / "projects" / "project-a" / registered["vault_path"]
        assert materialized.read_bytes() == before
        assert original.read_bytes() == before
    finally:
        repo.close()


def test_horizon_feishu_and_contradictions_enter_only_the_governed_a_layer(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "external-capture.db"))
    capture = SourceCaptureService(repo)
    try:
        primary = capture.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="fixture://primary-claim",
                raw_content=_fixture_json("sources/article.json")["content"],
                trust_level="trusted",
            )
        ).source

        run_store = HorizonRunStoreClient(runs_root=FIXTURES / "horizon" / "runs")
        stage = run_store.fetch_latest_stage()
        importer = HorizonImportService(repo, min_score=7.0)
        first_report = importer.import_items(
            project_id="project-a",
            run_id=stage.run_id,
            stage=stage.stage,
            items=stage.items,
        )
        retry_report = importer.import_items(
            project_id="project-a",
            run_id=stage.run_id,
            stage=stage.stage,
            items=stage.items,
        )
        assert first_report == {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 0}
        assert retry_report == {"accepted": 1, "created": 0, "duplicates": 1, "rejected": 0}
        horizon_source = next(source for source in repo.list_sources("project-a") if source["source_type"] == "horizon_signal")
        assert horizon_source["metadata"]["horizon_run_id"] == "run-001"
        assert horizon_source["metadata"]["horizon_stage"] == "enriched"
        assert repo.list_pages("project-a") == []
        assert repo.list_proposals("project-a") == []

        feishu_payload = _fixture_json("feishu/meeting-summary.json")
        feishu = FeishuImportService(repo).import_export(
            project_id="project-a",
            payload=feishu_payload,
            authorized=True,
        )
        feishu_retry = FeishuImportService(repo).import_export(
            project_id="project-a",
            payload=feishu_payload,
            authorized=True,
        )
        assert feishu.created is True
        assert feishu_retry.created is False
        assert feishu.source["source_type"] == "feishu_minutes"
        assert feishu.source["metadata"]["feishu_revision_id"] == "rev-2026-07-22-3"
        assert feishu.source["metadata"]["attachments"][0]["mime_type"] == "application/pdf"

        contradiction_fixture = _fixture_json("sources/contradiction.json")
        contradiction = capture.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="browser_clip",
                origin=contradiction_fixture["origin"],
                raw_content=contradiction_fixture["content"],
                trust_level="untrusted",
                metadata={
                    **contradiction_fixture["scores"],
                    "contradicts_source_ids": [primary["id"]],
                    "unanswered_question": True,
                },
            )
        ).source
        decision = SourceTriageService(repo).triage_source("project-a", contradiction["id"])
        assert decision["disposition"] == "research_topic"
        assert repo.get_source("project-a", contradiction["id"])["status"] == "validated"
        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")
        assert health["contradiction_count"] == 1
        assert sorted([primary["id"], contradiction["id"]]) in health["contradiction_pairs"]
        assert SourceTriageService(repo).list_research_topics("project-a")[0]["source_id"] == contradiction["id"]
        assert repo.list_pages("project-a") == []
        assert repo.list_proposals("project-a") == []
    finally:
        repo.close()
