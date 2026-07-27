from __future__ import annotations

import asyncio

from app.artifacts import ArtifactGraphStore, MemoryArtifact
from app.dbos.memory import KnowledgeMemoryAdapter
from app.dbos.service import DBOSService
from app.knowledge.growth_contracts import MethodAsset, MethodRevision, MethodStatus, OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def test_dbos_sop_planning_context_keeps_governed_pages_and_excludes_raw_sources():
    sections = (
        "## [profile:3]\nKnowledge-system profile.",
        "## [rules:abc]\nPublished Wiki rules.",
        "## [task:request]\nCreate a cited knowledge SOP.",
        "## [page:page-a@revision-a]\nPublished knowledge concept.",
        "## [source:source-a@hash-a]\nRaw Horizon source body must not enter the SOP prompt.",
        "## [output:output-a@revision-a]\nAn old output must not become a new template.",
    )

    rendered = KnowledgeMemoryAdapter._sop_planning_context(sections)

    assert "Knowledge-system profile" in rendered
    assert "Published Wiki rules" in rendered
    assert "Published knowledge concept" in rendered
    assert "Raw Horizon source body" not in rendered
    assert "old output" not in rendered


def test_dbos_reads_only_same_project_approved_methods_and_writes_feedback_memory(tmp_path):
    knowledge = GrowthRepository(db_path=str(tmp_path / "growth.db"))
    store = ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a")
    try:
        knowledge.create_method(MethodAsset(
            id="published-a", project_id="project-a", slug="conversion-experiment", name="Conversion experiment method",
            applicability=["ecommerce", "conversion_experiment"], status=MethodStatus.PUBLISHED,
        ))
        knowledge.create_method(MethodAsset(
            id="candidate-a", project_id="project-a", slug="draft-method", name="Draft method",
            applicability=["conversion_experiment"], status=MethodStatus.CANDIDATE,
        ))
        knowledge.create_method(MethodAsset(
            id="published-other", project_id="project-b", slug="other-method", name="Other project method",
            applicability=["conversion_experiment"], status=MethodStatus.PUBLISHED,
        ))
        service = DBOSService(store=store, knowledge_repository=knowledge)
        mission = service.create_mission(
            project_id="project-a",
            title="618 recovery",
            intake_mode="business",
            intent="Recover conversion in 30 days",
            context={
                "role": "ecommerce operations lead",
                "industry": "ecommerce",
                "organization_stage": "growth",
                "goal": "recover conversion",
            },
        )

        flow = service.diagnose_and_compile(mission.artifact_id)
        conversion = next(item for item in flow.selection.selected if item.task_family == "conversion_experiment")

        assert flow.selection.metadata["knowledge_context"]["method_ids"] == ["published-a"]
        assert any("Conversion experiment method" in reason for reason in conversion.reasons)
        service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[conversion.capability_name])
        task = next(
            task
            for phase in flow.sop.phases
            for task in phase.tasks
            if task.capability_name == conversion.capability_name
        )
        service.record_decision(
            mission.artifact_id,
            task_id=task.task_id,
            statement="Approve the constrained conversion experiment review.",
            rationale="Only the published same-project method supports this work.",
            alternatives=[],
            actor_id="owner",
        )
        execution = asyncio.run(service.execute(
            mission.artifact_id,
            conversion.capability_name,
            executor=lambda _name, _context: {"effect": "experiment reviewed"},
        ))

        memory = service.record_feedback_memory(
            mission.artifact_id,
            execution.artifact_id,
            statement="Keep the weekly experiment review for limited-budget campaigns.",
            feedback_kind="corrected",
        )

        assert isinstance(memory, MemoryArtifact)
        assert memory.parent_ids == [execution.artifact_id]
        assert memory.source_refs == [execution.artifact_id]
        assert memory.governance_status == "candidate"
        assert store.get(memory.artifact_id) is not None
    finally:
        knowledge.close()


def test_dbos_method_memory_honors_published_method_negative_trigger_contract(tmp_path):
    knowledge = GrowthRepository(db_path=str(tmp_path / "routing.db"))
    try:
        method = knowledge.create_method(MethodAsset(
            id="method-a", project_id="project-a", slug="conversion-experiment", name="Conversion experiment",
            applicability=["conversion experiment"], exclusions=["quick social post"], status=MethodStatus.PUBLISHED,
            active_revision_id="revision-a",
        ))
        knowledge.save_method_revision(MethodRevision(
            id="revision-a", project_id="project-a", method_id=method["id"], version=1, body="# Conversion experiment",
            status=MethodStatus.PUBLISHED,
            manifest={"trigger_contract": {"positive_signals": ["conversion experiment"], "negative_signals": ["quick social post"]}},
        ))
        memory = KnowledgeMemoryAdapter(repository=knowledge)
        context = memory.snapshot("project-a")

        assert [item["slug"] for item in memory.matching_methods(context, "conversion_experiment")] == ["conversion-experiment"]
        assert memory.matching_methods(context, "conversion experiment quick social post") == []
    finally:
        knowledge.close()


def test_dbos_compiles_from_governed_knowledge_signals_without_reading_bodies(tmp_path):
    """A/B/D metadata can affect a task only through an approved, scoped signal."""
    knowledge = GrowthRepository(db_path=str(tmp_path / "knowledge-signals.db"))
    store = ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a")
    try:
        knowledge.create_source(SourceRecord(
            id="conversion-signal-a",
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://example.test/conversion",
            content_hash="a" * 64,
            raw_content="This raw source body must never enter a DBOS artifact.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            metadata={"task_families": ["conversion experiment"], "ai_tags": ["conversion experiment"]},
        ))
        knowledge.create_source(SourceRecord(
            id="conversion-signal-other-project",
            project_id="project-b",
            source_type="manual_upload",
            content_hash="b" * 64,
            raw_content="Cross-project evidence must be invisible.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            metadata={"task_families": ["conversion experiment"]},
        ))
        knowledge.record_publication(
            project_id="project-a",
            contents={
                "wiki/sops/conversion-experiment.md": "---\n"
                "kind: sop\n"
                "task_families:\n"
                "  - conversion experiment\n"
                "---\n"
                "# Conversion experiment\n"
                "This Wiki body must never enter a DBOS artifact. [source:conversion-signal-a]\n",
            },
            source_ids=[],
        )
        page_id = knowledge.list_pages("project-a")[0]["id"]
        knowledge.register_output(OutputAsset(
            id="verified-conversion-output",
            project_id="project-a",
            kind="experiment_report",
            title="Prior conversion experiment",
            content_hash="c" * 64,
            vault_path="outputs/conversion-report.md",
            source_refs=["conversion-signal-a"],
            idempotency_key="verified-conversion-output",
            metadata={"task_family": "conversion experiment"},
        ))
        knowledge._execute(
            "UPDATE knowledge_outputs SET status='accepted',quality_json=? WHERE project_id=? AND id=?",
            ('{"quality": 92}', "project-a", "verified-conversion-output"),
        )
        knowledge._commit()

        service = DBOSService(store=store, knowledge_repository=knowledge)
        mission = service.create_mission(
            project_id="project-a",
            title="Conversion recovery with bounded reuse",
            intake_mode="business",
            intent="Recover ecommerce conversion before the campaign window closes.",
            context={
                "role": "ecommerce operations lead",
                "industry": "ecommerce",
                "organization_stage": "growth",
                "goal": "restore conversion",
                # This scenario verifies deterministic knowledge-signal
                # lineage, not model refinement. Keep it isolated from a
                # developer's configured live SOP provider.
                "sop_generation_mode": "deterministic",
            },
        )

        flow = service.diagnose_and_compile(mission.artifact_id)
        conversion = next(item for item in flow.selection.selected if item.task_family == "conversion_experiment")
        conversion_task = next(
            task
            for phase in flow.sop.phases
            for task in phase.tasks
            if task.task_family == "conversion_experiment"
        )
        center = service.control_center(mission.artifact_id)

        signals = flow.selection.metadata["knowledge_context"]["signals"]["by_task_family"]["conversion_experiment"]
        assert signals["source_ids"] == ["conversion-signal-a"]
        assert signals["page_ids"] == [page_id]
        assert signals["output_ids"] == ["verified-conversion-output"]
        assert "conversion-signal-other-project" not in str(flow.selection.metadata)
        assert conversion.score_components["knowledge_evidence"] > 0
        assert any("Governed knowledge evidence" in reason for reason in conversion.reasons)
        assert {"conversion-signal-a", page_id, "verified-conversion-output"} <= set(conversion_task.parent_refs)
        assert any("governed knowledge signals" in gate.lower() for gate in flow.sop.quality_gates)
        assert "This raw source body" not in str(flow.selection.model_dump())
        assert "This Wiki body" not in str(flow.selection.model_dump())
        assert "This raw source body" not in str(center["runtime_context"])
    finally:
        knowledge.close()
