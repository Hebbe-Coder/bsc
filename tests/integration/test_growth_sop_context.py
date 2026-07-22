from app.knowledge.generation_provenance import (
    ClaimStatus,
    GenerationClaim,
    GenerationReference,
    build_generation_manifest,
    legacy_generation_metadata,
)
from app.knowledge.growth_context import GrowthContextBuilder


def _pack(project_id: str, audience: str, fact: str):
    return GrowthContextBuilder(max_characters=2_000).build(
        project_id=project_id,
        profile={"revision": 2, "user_role": "operator", "target_audiences": [audience]},
        rules="Use evidence and expose assumptions.",
        rules_revision="rules-2",
        task="Turn this PRD into a project-specific SOP",
        pages=[{
            "id": f"page-{project_id}",
            "project_id": project_id,
            "revision": "page-r2",
            "status": "published",
            "content": fact,
        }],
        sources=[{
            "id": f"source-{project_id}",
            "project_id": project_id,
            "revision": "source-r1",
            "status": "eligible",
            "raw_content": f"Evidence: {fact}",
        }],
        methods=[{
            "id": f"method-{project_id}",
            "project_id": project_id,
            "revision": "method-r3",
            "status": "published",
            "body": "Escalate blocked approvals after one business day.",
        }],
        source_cutoff="2026-07-24T09:00:00Z",
        creation_run_id="run-sop",
    )


def test_sop_context_is_profile_specific_cited_and_cross_project_free():
    project_a = _pack("project-a", "finance operators", "Finance must approve refunds.")
    project_b = _pack("project-b", "content editors", "Editors approve publication.")

    assert "finance operators" in project_a.rendered
    assert "Finance must approve refunds" in project_a.rendered
    assert "Editors approve publication" not in project_a.rendered
    assert project_a.context_hash != project_b.context_hash
    assert project_a.source_ids == ("source-project-a",)
    assert project_a.page_ids == ("page-project-a",)
    assert project_a.method_revision_ids == ("method-r3",)


def test_sop_generation_metadata_carries_context_method_assumption_and_gap():
    pack = _pack("project-a", "finance operators", "Finance must approve refunds.")
    manifest = build_generation_manifest(
        project_id="project-a",
        context_id=pack.revision,
        context_hash=pack.context_hash,
        profile_revision=pack.profile_revision,
        rules_revision=pack.rules_revision,
        source_cutoff=pack.source_cutoff,
        generator_revision="prd-to-sop-v2",
        model_revision="model-v1",
        creation_run_id=pack.creation_run_id,
        claims=[
            GenerationClaim(
                claim_id="approval-step",
                text="Finance must approve refunds.",
                status=ClaimStatus.FACT,
                references=(GenerationReference(
                    project_id="project-a", kind="source", ref_id="source-project-a", revision="source-r1"
                ),),
            ),
            GenerationClaim(claim_id="sla", text="A one-day SLA may be appropriate.", status=ClaimStatus.ASSUMPTION),
            GenerationClaim(claim_id="benchmark", text="No SLA benchmark is available.", status=ClaimStatus.RESEARCH_GAP),
        ],
    )

    metadata = manifest.to_generation_metadata()
    assert metadata["context_hash"] == pack.context_hash
    assert metadata["method_revision_ids"] == []
    assert metadata["assumptions"] == ["A one-day SLA may be appropriate."]
    assert metadata["research_gaps"] == ["No SLA benchmark is available."]


def test_legacy_generation_explicitly_reports_that_growth_context_was_not_used():
    assert legacy_generation_metadata() == {
        "knowledge_context_used": False,
        "context_id": "",
        "context_hash": "",
        "source_refs": [],
        "page_refs": [],
        "method_revision_ids": [],
        "assumptions": [],
        "research_gaps": [],
        "context_omissions": ["growth_context_unavailable"],
    }
