import asyncio

import pytest

from app.agent.state import ProjectDraft
from app.orchestrator.contracts import EventType
from app.orchestrator.runtime_engine import RuntimeOrchestratorEngine
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

    draft_repo.save(ProjectDraft(session_id="rt-ok", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = RuntimeOrchestratorEngine(repo=draft_repo, bus=bus, runner=fake_runner)

    state = asyncio.run(engine.run_pipeline("rt-ok", "x", project_id="runtime-project"))

    draft = draft_repo.get("rt-ok")
    assert draft.status == "completed"
    assert draft.current_stage == "runtime"
    assert draft.completed_at
    assert state["project"]["runtime_mode"] == "business_runtime"
    assert state["project"]["project_id"] == "runtime-project"
    assert state["business_model"]["domain"] == "retail"
    assert state["risk"]["gate"]["decision"] == "pass"
    events = list(bus._history["rt-ok"])
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
