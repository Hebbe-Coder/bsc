from __future__ import annotations

from types import SimpleNamespace

from app.artifacts import (
    ArtifactGraphStore,
    CapabilitySelectionArtifact,
    CapabilitySelectionItem,
    DiagnosisArtifact,
    EvidenceArtifact,
)
from app.dbos.adaptive_compiler import AdaptiveSOPCompiler
from app.dbos.compiler import DynamicSOPCompiler
from app.dbos.service import DBOSService


class RecordingPromptOps:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            run_id="prompt-adaptive-1",
            provider="test-provider",
            model="test-model",
            agent_manifest=SimpleNamespace(manifest_fingerprint="a" * 64),
            usage=SimpleNamespace(
                provider_calls=2,
                reported_calls=2,
                complete=True,
                latency_ms=123,
                prompt_tokens=30,
                completion_tokens=70,
                total_tokens=100,
                cached_tokens=0,
                reasoning_tokens=20,
            ),
            attempt_count=2,
            retry_count=1,
            retry_categories=("server_error", "credential_rejected"),
            output=self.output,
        )


def _baseline():
    diagnosis = DiagnosisArtifact(
        project_id="project-a",
        mission_id="mission-a",
        label="Diagnosis: conversion recovery",
        role="ecommerce operations lead",
        industry="ecommerce",
        organization_stage="growth",
        goal="recover cart conversion before 618",
        time_horizon="30 days",
        constraints=["do not increase acquisition spend"],
        stakeholders=["merchandising lead"],
        decision_rights=["operations director"],
        success_metrics=["cart conversion returns to the prior four-week baseline"],
        operating_hypotheses=["Product-view-to-cart loss is the largest controllable bottleneck."],
        risk_summary=["Demand, inventory, conversion, and promotion economics can move together."],
        diagnostic_dimensions=["demand", "funnel", "merchandising"],
    )
    selection = CapabilitySelectionArtifact(
        project_id="project-a",
        mission_id="mission-a",
        diagnosis_id=diagnosis.artifact_id,
        label="Selection",
        selected=[
            CapabilitySelectionItem(
                capability_name="optimization_recommendations",
                task_family="conversion_experiment",
                score=0.9,
                executable=True,
            ),
            CapabilitySelectionItem(
                capability_name="risk_analysis",
                task_family="risk_control",
                score=0.8,
                executable=True,
            ),
        ],
    )
    evidence = [
        EvidenceArtifact(
            project_id="project-a",
            label="Trading dashboard",
            source="weekly trading dashboard",
            finding="Product-view to cart conversion fell 12 percent in the last two weeks.",
        )
    ]
    return diagnosis, selection, evidence, DynamicSOPCompiler().compile(diagnosis, selection)


def test_adaptive_compiler_customizes_content_but_cannot_change_task_graph():
    diagnosis, selection, evidence, baseline = _baseline()
    task_by_id = {task.task_id: task for phase in baseline.phases for task in phase.tasks}
    output = {
        "title": "618 Cart Recovery: Zero-Acquisition-Spend Operating System",
        "diagnostic_summary": "The plan isolates the 12 percent cart-loss signal before increasing spend and assigns the operations director the reversal decision.",
        "quality_gates": ["Compare the proposed variant against the four-week cart-conversion baseline before the operations director approves rollout."],
        "phases": [
            {
                "phase_id": phase.phase_id,
                "title": f"618 cart recovery: {phase.phase_id} the 12 percent loss",
                "objective": f"Use the declared dashboard signal and zero-acquisition-spend constraint to govern {phase.phase_id} work.",
            }
            for phase in baseline.phases
        ],
        "tasks": [
            {
                "task_id": task_id,
                "title": f"Custom task for {task.task_family}",
                "deliverable": f"Reviewed {task.task_family} decision record",
                "metric": "Cart conversion comparison is recorded with source and measurement window.",
                "trigger": "Start after the baseline and variant are available.",
                "decision_point": "Operations director accepts or reverses the bounded next action.",
                "risk": "Do not trade margin or inventory availability for an unverified conversion lift.",
                "check": "Inspect the dashboard source and the experiment comparison before marking complete.",
                "retrospect": "Record the observed lift, rejected hypothesis, and reusable decision condition.",
            }
            for task_id, task in task_by_id.items()
        ],
    }
    promptops = RecordingPromptOps(output)

    refined = AdaptiveSOPCompiler(promptops).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={
            "planning_context": {
                "availability": "available",
                "context_pack_id": "pack-1",
                "refs": ["context-pack:pack-1", "source:source-1"],
                "rendered": "[UNTRUSTED_CONTEXT source-1] A reviewed promotion constraint applies.",
            }
        },
    )

    refined_tasks = {task.task_id: task for phase in refined.phases for task in phase.tasks}
    assert refined.title.startswith("618 Cart Recovery")
    assert set(refined_tasks) == set(task_by_id)
    assert all(refined_tasks[key].capability_name == task_by_id[key].capability_name for key in task_by_id)
    assert all(refined_tasks[key].task_family == task_by_id[key].task_family for key in task_by_id)
    assert all(refined_tasks[key].parent_refs == task_by_id[key].parent_refs for key in task_by_id)
    assert [phase.phase_id for phase in refined.phases] == [phase.phase_id for phase in baseline.phases]
    assert all(refined_phase.title != baseline_phase.title for refined_phase, baseline_phase in zip(refined.phases, baseline.phases))
    assert all(refined_phase.objective != baseline_phase.objective for refined_phase, baseline_phase in zip(refined.phases, baseline.phases))
    assert refined.quality_gates == output["quality_gates"]
    assert refined.metadata["adaptive_compilation"]["status"] == "completed"
    assert refined.metadata["adaptive_compilation"]["context_pack_id"] == "pack-1"
    assert "source:source-1" in promptops.requests[0].context_refs
    assert "Product-view to cart conversion fell 12 percent" in promptops.requests[0].user_prompt
    assert promptops.requests[0].revision == "dbos-adaptive-sop-v4"
    assert '"response_contract"' in promptops.requests[0].user_prompt
    assert refined.metadata["adaptive_compilation"]["specificity"]["status"] == "passed"
    assert refined.metadata["adaptive_compilation"]["model_run"] == {
        "run_id": "prompt-adaptive-1",
        "task": "sop_composition",
        "revision": "dbos-adaptive-sop-v4",
        "provider": "test-provider",
        "model": "test-model",
        "agent_manifest_fingerprint": "a" * 64,
        "provider_calls": 2,
        "reported_calls": 2,
        "usage_complete": True,
        "latency_ms": 123,
        "prompt_tokens": 30,
        "completion_tokens": 70,
        "total_tokens": 100,
        "cached_tokens": 0,
        "reasoning_tokens": 20,
        "attempt_count": 2,
        "retry_count": 1,
        "retry_categories": ["server_error"],
    }


def test_adaptive_compiler_falls_back_when_response_changes_the_task_contract():
    diagnosis, selection, evidence, baseline = _baseline()
    promptops = RecordingPromptOps({"title": "Unsafe", "tasks": [{"task_id": "not-a-real-task"}]})

    refined = AdaptiveSOPCompiler(promptops).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={},
    )

    assert refined.phases == baseline.phases
    assert refined.metadata["adaptive_compilation"]["status"] == "fallback"
    assert refined.metadata["adaptive_compilation"]["reason"] == "model_output_not_contextual"


def test_adaptive_compiler_rejects_a_model_that_only_repeats_the_template():
    diagnosis, selection, evidence, baseline = _baseline()
    copied_tasks = [
        {"task_id": task.task_id, **{field: getattr(task, field) for field in (
            "title", "deliverable", "metric", "trigger", "decision_point", "risk", "check", "retrospect",
        )}}
        for phase in baseline.phases
        for task in phase.tasks
    ]
    promptops = RecordingPromptOps({
        "title": "A different but insufficient title",
        "diagnostic_summary": "The task details were copied from a baseline.",
        "phases": [
            {"phase_id": phase.phase_id, "title": phase.title, "objective": phase.objective}
            for phase in baseline.phases
        ],
        "tasks": copied_tasks,
    })

    refined = AdaptiveSOPCompiler(promptops).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={},
    )

    assert refined.phases == baseline.phases
    assert refined.metadata["adaptive_compilation"]["status"] == "fallback"
    assert refined.metadata["adaptive_compilation"]["reason"] == "model_output_not_contextual"


def test_adaptive_compiler_rejects_fluent_but_generic_rewrites_without_mission_anchors():
    diagnosis, selection, evidence, baseline = _baseline()
    output = {
        "title": "Operational Improvement Plan",
        "diagnostic_summary": "The team will coordinate a measured sequence of work and review progress weekly.",
        "quality_gates": ["Review the outcome before expanding the work."],
        "phases": [
            {
                "phase_id": phase.phase_id,
                "title": f"Phase {index + 1}: coordinated improvement",
                "objective": "Complete the next reviewed action with accountable owners.",
            }
            for index, phase in enumerate(baseline.phases)
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "title": f"Coordinate {task.task_family} work",
                "deliverable": "A reviewed operating record for the next decision.",
                "metric": "The agreed measurement is recorded for review.",
                "decision_point": "The responsible leader accepts or adjusts the next action.",
                "risk": "Do not proceed when the required review is incomplete.",
            }
            for phase in baseline.phases
            for task in phase.tasks
        ],
    }

    refined = AdaptiveSOPCompiler(RecordingPromptOps(output)).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={},
    )

    metadata = refined.metadata["adaptive_compilation"]
    assert metadata["status"] == "fallback"
    assert metadata["reason"] == "model_output_not_grounded"
    assert metadata["specificity"]["status"] == "failed"
    assert metadata["specificity"]["unmatched_phase_ids"]
    assert metadata["specificity"]["unmatched_task_ids"]
    assert metadata["model_run"]["run_id"] == "prompt-adaptive-1"
    assert metadata["model_run"]["retry_categories"] == ["server_error"]


def test_adaptive_compiler_falls_back_when_phase_contract_is_missing_or_changed():
    diagnosis, selection, evidence, baseline = _baseline()
    task_by_id = {task.task_id: task for phase in baseline.phases for task in phase.tasks}
    output = {
        "phases": [
            {"phase_id": "unapproved-phase", "title": "Unsafe phase", "objective": "Change the task graph"},
        ],
        "tasks": [
            {
                "task_id": task_id,
                "title": f"Specific {task.task_family}",
                "deliverable": "Reviewed evidence-backed deliverable",
                "metric": "Cart conversion baseline is compared.",
                "trigger": "Use the declared 30-day window.",
                "decision_point": "Operations director reviews the outcome.",
                "risk": "Do not increase acquisition spend.",
                "check": "Inspect the dashboard evidence.",
                "retrospect": "Record the result and the rejected hypothesis.",
            }
            for task_id, task in task_by_id.items()
        ],
    }

    refined = AdaptiveSOPCompiler(RecordingPromptOps(output)).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={},
    )

    assert refined.phases == baseline.phases
    assert refined.metadata["adaptive_compilation"]["status"] == "fallback"


def test_adaptive_compiler_accepts_compact_task_output_and_keeps_stable_governance_text():
    diagnosis, selection, evidence, baseline = _baseline()
    output = {
        "phases": [
            {
                "phase_id": phase.phase_id,
                "title": f"618 conversion recovery {phase.phase_id}",
                "objective": "Use the cart-loss evidence and no-spend boundary for the next reviewed decision.",
            }
            for phase in baseline.phases
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "title": f"Recover the 12 percent cart loss through {task.task_family}",
                "deliverable": f"Reviewed {task.task_family} record for the 618 recovery decision",
                "metric": "Cart conversion is compared with the four-week baseline.",
                "decision_point": "The operations director accepts or reverses the bounded next action.",
                "risk": "No acquisition spend or inventory trade-off is allowed without review.",
            }
            for phase in baseline.phases
            for task in phase.tasks
        ],
    }

    refined = AdaptiveSOPCompiler(RecordingPromptOps(output)).refine(
        baseline,
        diagnosis=diagnosis,
        selection=selection,
        evidence=evidence,
        knowledge_context={},
    )

    baseline_by_id = {task.task_id: task for phase in baseline.phases for task in phase.tasks}
    refined_by_id = {task.task_id: task for phase in refined.phases for task in phase.tasks}
    assert refined.metadata["adaptive_compilation"]["status"] == "completed"
    assert all(refined_by_id[key].title != baseline_by_id[key].title for key in baseline_by_id)
    assert all(refined_by_id[key].trigger == baseline_by_id[key].trigger for key in baseline_by_id)
    assert all(refined_by_id[key].check == baseline_by_id[key].check for key in baseline_by_id)


def test_service_uses_adaptive_compilation_only_when_the_mission_requests_it(tmp_path):
    class RecordingAdaptiveCompiler:
        def __init__(self):
            self.calls = []

        def refine(self, baseline, **kwargs):
            self.calls.append(kwargs)
            return baseline.model_copy(update={
                "metadata": {"adaptive_compilation": {"status": "completed", "run_id": "fake"}},
            })

    store = ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a", session_id="dbos")
    adaptive = RecordingAdaptiveCompiler()
    service = DBOSService(store=store, adaptive_compiler=adaptive)
    mission = service.create_mission(
        project_id="project-a",
        title="Specific product launch",
        intake_mode="business",
        intent="Prepare an evidence-backed launch decision for the new AI onboarding flow.",
        context={
            "role": "product lead",
            "industry": "AI SaaS",
            "organization_stage": "growth",
            "goal": "increase activation",
            "sop_generation_mode": "adaptive",
        },
    )

    flow = service.diagnose_and_compile(mission.artifact_id)

    assert len(adaptive.calls) == 1
    assert flow.sop.metadata["adaptive_compilation"]["status"] == "completed"
