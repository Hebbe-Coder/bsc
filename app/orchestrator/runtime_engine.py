from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable

from app.agent.state import ProjectDraft, ProjectDraftRepository
from app.capabilities.runner import run_business_runtime
from app.orchestrator.contracts import EventType, JobStatus
from app.orchestrator.sse import SessionEventBus


RuntimeRunner = Callable[..., Awaitable[dict[str, Any]]]


class RuntimeOrchestratorEngine:
    """Run BusinessRuntime behind the existing orchestrator lifecycle contract."""

    def __init__(
        self,
        *,
        repo: ProjectDraftRepository | None = None,
        bus: SessionEventBus | None = None,
        runner: RuntimeRunner = run_business_runtime,
    ) -> None:
        self.repo = repo or ProjectDraftRepository()
        self.bus = bus or SessionEventBus()
        self.runner = runner

    async def _emit(
        self,
        session_id: str,
        stage: str,
        status: str,
        message: str,
        *,
        event_type: EventType | None = None,
        terminal: bool = False,
        data: dict[str, Any] | None = None,
    ):
        event = await self.bus.publish(
            session_id,
            event_type or EventType.STAGE_COMPLETED,
            stage=stage,
            status=status,
            message=message,
            terminal=terminal,
            data=data,
        )
        if event is not None:
            self.repo.record_event(event)
        return event

    async def run_pipeline(
        self,
        session_id: str,
        idea: str,
        *,
        project_id: str = "",
        tenant_id: str = "",
        owner_session_id: str = "",
        context_policy: str = "fresh",
        context_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.repo.get(session_id) is None:
            self.repo.save(ProjectDraft(
                session_id=session_id,
                tenant_id=tenant_id,
                project_id=project_id or session_id,
                owner_session_id=owner_session_id,
                idea=idea,
                status=JobStatus.QUEUED.value,
            ))

        self.repo.transition(session_id, JobStatus.RUNNING)
        await self._emit(
            session_id,
            "pipeline",
            "running",
            "BusinessRuntime started",
            event_type=EventType.PIPELINE_STARTED,
            data={
                "context_policy": context_policy,
                "inherited_items": len(context_items or []),
            },
        )

        try:
            await self._emit(
                session_id,
                "runtime",
                "running",
                "Planning and executing shared BusinessRuntime",
                event_type=EventType.STAGE_STARTED,
            )
            runner_kwargs = {
                "input_text": idea,
                "domain": "",
                "mode": "template",
                "project_id": project_id or session_id,
                "execution_id": session_id,
            }
            if _accepts_keyword(self.runner, "tenant_id"):
                runner_kwargs["tenant_id"] = tenant_id
            if _accepts_keyword(self.runner, "context_policy"):
                runner_kwargs["context_policy"] = context_policy
            if _accepts_keyword(self.runner, "context_items"):
                runner_kwargs["context_items"] = context_items or []
            live_capability_events = 0

            async def emit_runtime_event(event: dict[str, Any]) -> None:
                nonlocal live_capability_events
                if event.get("kind") != "capability":
                    return
                live_capability_events += 1
                status = str(event.get("status") or "running")
                if status == "started":
                    event_type = EventType.CAPABILITY_STARTED
                elif status in {"failed", "error", "timeout"}:
                    event_type = EventType.CAPABILITY_FAILED
                else:
                    event_type = EventType.CAPABILITY_COMPLETED
                capability_name = str(event.get("capability_name") or "capability")
                await self._emit(
                    session_id,
                    capability_name,
                    status,
                    str(event.get("error") or f"{capability_name} {status}"),
                    event_type=event_type,
                    data={
                        "kind": "capability",
                        "parent_stage": "runtime",
                        "step_id": event.get("step_id", ""),
                        "iteration": event.get("iteration", 0),
                        "execution": event.get("execution", {}),
                    },
                )

            if _accepts_keyword(self.runner, "event_sink"):
                runner_kwargs["event_sink"] = emit_runtime_event
            result = await self.runner(**runner_kwargs)
            if live_capability_events == 0:
                for index, execution in enumerate(
                    _list(_dict(result.get("runtime")).get("capability_executions"))
                ):
                    capability = _dict(execution)
                    capability_name = str(
                        capability.get("capability_name") or f"capability-{index + 1}"
                    )
                    capability_status = str(capability.get("status") or "completed")
                    failed = capability_status in {"failed", "error", "timeout"}
                    await self._emit(
                        session_id,
                        capability_name,
                        capability_status,
                        capability.get("error")
                        or f"{capability_name} {capability_status}",
                        event_type=(
                            EventType.CAPABILITY_FAILED
                            if failed
                            else EventType.CAPABILITY_COMPLETED
                        ),
                        data={
                            "kind": "capability",
                            "parent_stage": "runtime",
                            "capability_index": index,
                            "execution": capability,
                        },
                    )
            state = runtime_response_to_project_state(
                session_id=session_id,
                idea=idea,
                response=result,
            )
            current_draft = self.repo.get(session_id)
            self.repo.save(_draft_from_state(
                session_id=session_id,
                idea=idea,
                state=state,
                status=JobStatus.RUNNING.value,
                tenant_id=tenant_id or (current_draft.tenant_id if current_draft else ""),
                project_id=(
                    project_id
                    or (current_draft.project_id if current_draft else "")
                    or session_id
                ),
                owner_session_id=(
                    owner_session_id
                    or (current_draft.owner_session_id if current_draft else "")
                ),
                current_stage=current_draft.current_stage if current_draft else "",
                event_seq=current_draft.event_seq if current_draft else 0,
                created_at=current_draft.created_at if current_draft else None,
            ))
            await self._emit(
                session_id,
                "runtime",
                "done",
                "BusinessRuntime execution finished",
                data={
                    "project_id": result.get("project_id", ""),
                    "runtime": result.get("runtime", {}),
                },
            )

            if _runtime_failed(result):
                raise RuntimeError(_runtime_error_message(result))

            self.repo.transition(session_id, JobStatus.COMPLETED)
            await self._emit(
                session_id,
                "pipeline",
                "completed",
                "Pipeline completed",
                event_type=EventType.PIPELINE_COMPLETED,
                terminal=True,
                data={"runtime": result.get("runtime", {})},
            )
            return state
        except asyncio.CancelledError:
            self.repo.transition(session_id, JobStatus.CANCELLED)
            await self._emit(
                session_id,
                "pipeline",
                "cancelled",
                "Pipeline cancelled",
                event_type=EventType.PIPELINE_CANCELLED,
                terminal=True,
            )
            raise
        except Exception:
            self.repo.transition(
                session_id,
                JobStatus.FAILED,
                error_code="runtime_failed",
                error_message="Pipeline failed",
            )
            await self._emit(
                session_id,
                "pipeline",
                "failed",
                "Pipeline failed",
                event_type=EventType.PIPELINE_FAILED,
                terminal=True,
            )
            raise


def runtime_response_to_project_state(
    *,
    session_id: str,
    idea: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    report = _dict(response.get("report"))
    graph = _dict(report.get("_artifact_graph"))
    mission = _dict(response.get("mission"))
    runtime = _dict(response.get("runtime"))
    risks = _list(report.get("risks")) or [
        _risk_projection(item) for item in _list(graph.get("risks"))
    ]
    constraints = [_constraint_projection(item) for item in _list(graph.get("constraints"))]
    decisions = [_decision_projection(item) for item in _list(graph.get("decisions"))]
    gaps = _list(response.get("gap_details")) or _list(graph.get("gaps"))

    objectives = _list(report.get("objectives"))
    project_name = mission.get("title") or report.get("business_domain") or idea[:48]
    business_model = {
        "domain": report.get("business_domain", ""),
        "objectives": objectives,
        "flows": _workflow_projection(report),
        "roles": _roles_projection(report),
        "rules": constraints,
        "_citation_coverage": _citation_coverage(
            _workflow_projection(report),
            _roles_projection(report),
            constraints,
        ),
        "_artifact_graph": graph,
        "_runtime": runtime,
    }
    sop_items = _sop_projection(report, decisions)

    return {
        "session_id": session_id,
        "idea": idea,
        "project": {
            "name": project_name,
            "project_id": response.get("project_id", ""),
            "execution_id": response.get("execution_id", ""),
            "runtime_mode": "business_runtime",
        },
        "requirements": [
            {"id": f"obj-{idx + 1}", "text": objective}
            for idx, objective in enumerate(objectives)
        ],
        "business_model": business_model,
        "sop": {
            "sops": sop_items,
            "_citation_coverage": _citation_coverage(sop_items),
            "_runtime": runtime,
        },
        "risk": {
            "overall_score": _risk_score(risks),
            "gate": {
                "decision": "review" if gaps or _runtime_failed(response) else "pass",
                "reasons": [g.get("gap_statement", str(g)) for g in gaps],
            },
            "coverage": _coverage_projection(graph),
            "risks": risks,
        },
        "review": {
            "approved": not gaps and not _runtime_failed(response),
            "gaps": gaps,
            "summary": _review_summary(response, gaps),
            "runtime": runtime,
        },
        "presentation": {
            "html_url": "",
            "ppt_path": "",
            "diagram_spec": {},
            "runtime_report": report,
        },
        "messages": [{
            "type": "runtime",
            "project_id": response.get("project_id", ""),
            "execution_id": response.get("execution_id", ""),
            "runtime": runtime,
        }],
    }


def _draft_from_state(
    *,
    session_id: str,
    idea: str,
    state: dict[str, Any],
    status: str,
    tenant_id: str,
    project_id: str,
    owner_session_id: str,
    current_stage: str,
    event_seq: int,
    created_at: str | None,
) -> ProjectDraft:
    return ProjectDraft(
        session_id=session_id,
        tenant_id=tenant_id,
        project_id=project_id,
        owner_session_id=owner_session_id,
        idea=idea,
        project=_dict(state.get("project")),
        requirements=_list(state.get("requirements")),
        business_model=_dict(state.get("business_model")),
        sop=_dict(state.get("sop")),
        risk=_dict(state.get("risk")),
        review=_dict(state.get("review")),
        presentation=_dict(state.get("presentation")),
        status=status,
        messages=_list(state.get("messages")),
        current_stage=current_stage,
        event_seq=event_seq,
        created_at=created_at,
    )


def _runtime_failed(response: dict[str, Any]) -> bool:
    runtime = _dict(response.get("runtime"))
    return bool(
        response.get("status") == "failed"
        or runtime.get("status") == "error"
        or runtime.get("errors")
    )


def _runtime_error_message(response: dict[str, Any]) -> str:
    runtime = _dict(response.get("runtime"))
    errors = _list(runtime.get("errors"))
    if errors:
        return str(errors[0])
    return "BusinessRuntime failed"


def _workflow_projection(report: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = _list(report.get("workflow"))
    if workflow:
        return [
            item
            if isinstance(item, dict)
            else {"id": f"flow-{idx + 1}", "name": str(item), "source_ref": []}
            for idx, item in enumerate(workflow)
        ]
    objectives = _list(report.get("objectives"))
    return [
        {
            "id": f"flow-{idx + 1}",
            "name": objective,
            "steps": [],
            "source_ref": [],
        }
        for idx, objective in enumerate(objectives)
    ]


def _roles_projection(report: dict[str, Any]) -> list[dict[str, Any]]:
    roles = _list(report.get("roles"))
    return [
        item
        if isinstance(item, dict)
        else {"id": f"role-{idx + 1}", "name": str(item), "source_ref": []}
        for idx, item in enumerate(roles)
    ]


def _sop_projection(
    report: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    workflow = _workflow_projection(report)
    if workflow:
        return workflow
    return [
        {
            "id": decision.get("id", f"decision-{idx + 1}"),
            "title": decision.get("decision", "Runtime decision"),
            "steps": [decision.get("rationale", "")] if decision.get("rationale") else [],
            "source_ref": [decision.get("id")] if decision.get("id") else [],
        }
        for idx, decision in enumerate(decisions)
    ]


def _constraint_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("artifact_id", ""),
        "name": item.get("label") or item.get("constraint_statement", ""),
        "description": item.get("constraint_statement", ""),
        "type": item.get("constraint_type", ""),
        "source_ref": [item.get("artifact_id", "")] if item.get("artifact_id") else [],
    }


def _risk_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk": item.get("risk_statement", item.get("risk", "")),
        "severity": _enum_value(item.get("severity", "medium")),
        "probability": _enum_value(item.get("probability", "medium")),
        "mitigation": item.get("mitigation", ""),
    }


def _decision_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("artifact_id", ""),
        "decision": item.get("decision_statement", item.get("label", "")),
        "rationale": item.get("rationale", ""),
    }


def _coverage_projection(graph: dict[str, Any]) -> dict[str, Any]:
    coverages = _list(graph.get("coverages"))
    if not coverages:
        return {
            "total": 0,
            "covered": 0,
            "coverage_pct": 0,
            "uncovered_ids": [],
        }
    coverage = coverages[0]
    missed = _list(coverage.get("dimensions_missed"))
    scores = _dict(coverage.get("dimension_scores"))
    dimensions = {str(name) for name in scores} | {str(name) for name in missed}
    coverage_pct = round(float(coverage.get("overall_coverage", 0)) * 100, 1)
    total = len(dimensions)
    return {
        "total": total,
        "covered": round(total * coverage_pct / 100) if total else 0,
        "coverage_pct": coverage_pct,
        "uncovered_ids": missed,
    }


def _risk_score(risks: list[dict[str, Any]]) -> str:
    severities = {_enum_value(risk.get("severity", "")) for risk in risks}
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _review_summary(response: dict[str, Any], gaps: list[Any]) -> str:
    runtime = _dict(response.get("runtime"))
    if _runtime_failed(response):
        return "BusinessRuntime failed"
    if gaps:
        return f"BusinessRuntime completed with {len(gaps)} gap(s)"
    status = runtime.get("status", "completed")
    iterations = runtime.get("iterations", 0)
    return f"BusinessRuntime {status} after {iterations} iteration(s)"


def _citation_coverage(*groups: list[dict[str, Any]]) -> dict[str, Any]:
    items = [item for group in groups for item in group if isinstance(item, dict)]
    total = len(items)
    covered = sum(
        1 for item in items
        if isinstance(item.get("source_ref"), list) and bool(item.get("source_ref"))
    )
    coverage = round((covered / total), 3) if total else 0.0
    flagged = [
        item.get("id", "")
        for item in items
        if not (isinstance(item.get("source_ref"), list) and item.get("source_ref"))
    ]
    return {
        "coverage": coverage,
        "covered": covered,
        "total": total,
        "flagged": [value for value in flagged if value],
    }


def _enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    parameters = inspect.signature(callable_obj).parameters.values()
    return any(
        parameter.name == keyword or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
