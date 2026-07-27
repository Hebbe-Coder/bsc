import asyncio

import pytest

from app.agent.state import ProjectDraft
from app.orchestrator.contracts import EventType
from app.orchestrator.runtime_engine import RuntimeOrchestratorEngine, runtime_response_to_project_state
from app.orchestrator.sse import SessionEventBus


def _success_response(project_id: str = "runtime-project") -> dict:
    return {
        "status": "completed",
        "project_id": project_id,
        "execution_id": "sess-rt",
        "mission": {"title": "Runtime Mission", "steps": 2, "mode": "template"},
        "artifacts": 4,
        "gaps": 0,
        "gap_details": [],
        "board": None,
        "runtime": {
            "status": "completed",
            "iterations": 1,
            "elapsed_ms": 8.5,
            "errors": [],
            "artifact_scope": "tmp/runtime-project/sess-rt",
            "capability_executions": [{
                "capability_name": "business_understanding",
                "status": "success",
                "artifacts_produced": ["artifact-1"],
                "elapsed_ms": 8.5,
                "backend": "nanobot",
                "retries": 1,
                "attempts": [
                    {"attempt": 1, "outcome": "failed", "retryable": True},
                    {"attempt": 2, "outcome": "success", "retryable": False},
                ],
            }],
        },
        "report": {
            "business_domain": "retail",
            "objectives": ["Improve conversion", "Reduce churn"],
            "workflow": [{"id": "wf-1", "name": "Lead intake"}],
            "roles": [{"id": "role-1", "name": "Operator"}],
            "risks": [{"risk": "Staff overload", "severity": "medium", "probability": "medium", "mitigation": "Shift planning"}],
            "_artifact_graph": {
                "total_artifacts": 4,
                "constraints": [
                    {
                        "artifact_id": "c-1",
                        "label": "Compliance policy",
                        "constraint_statement": "Need approval before launch",
                        "constraint_type": "regulatory",
                    }
                ],
                "coverages": [
                    {
                        "overall_coverage": 1.0,
                        "dimension_scores": {"ops": 1.0, "risk": 1.0},
                        "dimensions_missed": [],
                    }
                ],
                "risks": [],
                "gaps": [],
                "decisions": [
                    {
                        "artifact_id": "d-1",
                        "decision_statement": "Launch phased rollout",
                        "rationale": "Validate demand with low risk",
                    }
                ],
            },
        },
    }


def test_runtime_engine_persists_completed_and_emits_terminal(draft_repo):
    async def fake_runner(**kwargs):
        assert kwargs["project_id"] == "runtime-project"
        assert kwargs["execution_id"] == "rt-ok"
        return _success_response(project_id=kwargs["project_id"])

    draft_repo.save(ProjectDraft(
        session_id="rt-ok",
        tenant_id="tenant-a",
        project_id="runtime-project",
        owner_session_id="browser-a",
        idea="x",
        status="queued",
    ))
    created_at = draft_repo.get("rt-ok").created_at
    bus = SessionEventBus()
    engine = RuntimeOrchestratorEngine(repo=draft_repo, bus=bus, runner=fake_runner)

    state = asyncio.run(engine.run_pipeline(
        "rt-ok",
        "x",
        project_id="runtime-project",
        tenant_id="tenant-a",
        owner_session_id="browser-a",
    ))

    draft = draft_repo.get("rt-ok")
    assert draft.status == "completed"
    assert draft.tenant_id == "tenant-a"
    assert draft.project_id == "runtime-project"
    assert draft.owner_session_id == "browser-a"
    assert draft.created_at == created_at
    assert draft.current_stage == "runtime"
    assert draft.completed_at
    assert state["project"]["runtime_mode"] == "business_runtime"
    assert state["project"]["project_id"] == "runtime-project"
    assert state["business_model"]["domain"] == "retail"
    assert state["risk"]["gate"]["decision"] == "pass"
    events = list(bus._history["rt-ok"])
    capability_events = [
        event for event in events
        if event.type == EventType.CAPABILITY_COMPLETED
    ]
    assert len(capability_events) == 1
    assert capability_events[0].stage == "business_understanding"
    assert capability_events[0].data["parent_stage"] == "runtime"
    assert events[-1].type == EventType.PIPELINE_COMPLETED
    assert events[-1].terminal is True
    assert events[-1].data["runtime"]["capability_executions"][0]["retries"] == 1
    assert draft.event_seq == events[-1].seq


def test_runtime_engine_marks_failed_when_runtime_response_failed(draft_repo):
    async def fake_runner(**kwargs):
        return {
            **_success_response(project_id=kwargs["project_id"]),
            "status": "failed",
            "runtime": {
                "status": "error",
                "iterations": 1,
                "elapsed_ms": 3.0,
                "errors": ["runtime exploded"],
                "artifact_scope": "tmp/runtime-project/rt-bad",
            },
        }

    draft_repo.save(ProjectDraft(session_id="rt-bad", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = RuntimeOrchestratorEngine(repo=draft_repo, bus=bus, runner=fake_runner)

    with pytest.raises(RuntimeError, match="runtime exploded"):
        asyncio.run(engine.run_pipeline("rt-bad", "x", project_id="runtime-project"))

    draft = draft_repo.get("rt-bad")
    assert draft.status == "failed"
    assert draft.current_stage == "runtime"
    assert draft.error_code == "runtime_failed"
    assert draft.error_message == "Pipeline failed"
    assert draft.completed_at
    events = list(bus._history["rt-bad"])
    assert events[-1].type == EventType.PIPELINE_FAILED
    assert events[-1].terminal is True
    assert draft.event_seq == events[-1].seq


def test_runtime_engine_does_not_send_context_keywords_to_legacy_runner(draft_repo):
    captured = {}

    async def legacy_runner(input_text, domain, mode, project_id, execution_id):
        captured.update({
            "input_text": input_text,
            "domain": domain,
            "mode": mode,
            "project_id": project_id,
            "execution_id": execution_id,
        })
        return _success_response(project_id=project_id)

    draft_repo.save(ProjectDraft(session_id="rt-legacy", idea="x", status="queued"))
    engine = RuntimeOrchestratorEngine(
        repo=draft_repo,
        bus=SessionEventBus(),
        runner=legacy_runner,
    )

    asyncio.run(engine.run_pipeline(
        "rt-legacy",
        "x",
        project_id="runtime-project",
        context_policy="fork",
        context_items=[{"role": "user", "content": "parent"}],
    ))

    assert captured["project_id"] == "runtime-project"
    assert "context_policy" not in captured
    assert "context_items" not in captured


def test_runtime_projection_prefers_authored_sop_over_generic_workflow():
    response = _success_response()
    response["runtime"]["knowledge_context"] = {
        "context_pack_id": "context-1",
        "source_ids": ["source-primary-1"],
        "page_ids": ["page-decision-1"],
    }
    response["report"]["deliverables"] = [{
        "artifact_id": "deliverable-sop-1",
        "kind": "sop",
        "title": "Evidence-led Horizon intake SOP",
        "summary": "Capture primary evidence before durable publication.",
        "differentiators": ["A Horizon signal cannot author a Wiki page alone"],
        "sections": [{"title": "Primary capture", "details": ["Capture the official source"]}],
        "actions": [{
            "title": "Capture primary evidence",
            "owner": "Knowledge operator",
            "trigger": "Horizon candidate admitted",
            "action": "Capture and triage the public primary source",
            "output": "Reviewable primary evidence",
            "metric": "No Horizon-only publication",
            "timebox": "1 business day",
        }],
        "evidence_gaps": ["Official source is inaccessible"],
        "evidence_refs": ["source-primary-1"],
    }]

    state = runtime_response_to_project_state(
        session_id="projection-sop",
        idea="Build the evidence loop",
        response=response,
    )

    sop = state["sop"]["sops"]
    assert len(sop) == 1
    assert sop[0]["id"] == "deliverable-sop-1"
    assert sop[0]["title"] == "Evidence-led Horizon intake SOP"
    assert sop[0]["actions"][0]["trigger"] == "Horizon candidate admitted"
    assert sop[0]["source_ref"] == ["source-primary-1"]
    assert sop[0]["context_ref"] == {
        "context_pack_id": "context-1",
        "source_ids": ["source-primary-1"],
        "page_ids": ["page-decision-1"],
    }
    assert state["sop"]["_citation_coverage"] == {
        "coverage": 1.0,
        "covered": 1,
        "total": 1,
        "flagged": [],
    }
