"""Shared construction and response mapping for BusinessRuntime executions."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.artifacts import ArtifactGraphStore
from app.capabilities import (
    BusinessRuntime,
    MissionGraph,
    MissionPlanner,
    MissionStep,
    MultiAgentBoard,
    RuntimeResult,
    build_default_registry,
)
from app.core.context_policy import ContextItem, ContextManager, ContextPolicy


def new_project_id(prefix: str = "agent") -> str:
    """Create a request-scoped project id instead of using global placeholders."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def scoped_artifact_dir(
    data_dir: str,
    project_id: str,
    execution_id: str,
    tenant_id: str = "",
) -> str:
    """Return the tenant/project/execution directory for artifact isolation."""
    root = Path(data_dir)
    if tenant_id:
        root = root / _safe_path_segment(tenant_id)
    return str(root / _safe_path_segment(project_id) / _safe_path_segment(execution_id))


async def run_business_runtime(
    *,
    input_text: str,
    domain: str = "",
    mode: str = "template",
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    board: bool = False,
    data_dir: str = "./data/artifacts",
    executor_backend: str = "nanobot",
    max_iterations: int = 3,
    context_policy: ContextPolicy | str = ContextPolicy.FRESH,
    context_items: list[ContextItem | dict[str, Any]] | None = None,
    knowledge_context_provider: Callable[[str, str], dict[str, Any]] | None = None,
    context_max_tokens: int = 12_000,
    event_sink: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """Execute the shared BusinessRuntime and map it to the Agent OS API shape."""
    scoped_project_id = project_id.strip() if project_id else new_project_id()
    scoped_execution_id = execution_id.strip() if execution_id else new_project_id("run")
    artifact_scope = scoped_artifact_dir(
        data_dir,
        scoped_project_id,
        scoped_execution_id,
        tenant_id,
    )
    store = ArtifactGraphStore(
        data_dir=artifact_scope,
        tenant_id=tenant_id,
        project_id=scoped_project_id,
        session_id=scoped_execution_id,
    )
    registry = build_default_registry()
    planner = MissionPlanner(registry=registry, mode=mode)
    runtime_kwargs = {
        "store": store,
        "registry": registry,
        "planner": planner,
        "max_iterations": max_iterations,
        "executor_backend": executor_backend,
    }
    if event_sink is not None and _accepts_keyword(BusinessRuntime, "event_sink"):
        runtime_kwargs["event_sink"] = event_sink
    runtime = BusinessRuntime(
        **runtime_kwargs,
    )

    knowledge_context = (
        knowledge_context_provider(scoped_project_id, input_text)
        if knowledge_context_provider is not None
        else _retrieve_project_knowledge_context(scoped_project_id, input_text)
    )
    project_context_items: list[ContextItem] = []
    context_block = str(knowledge_context.get("context_block") or "").strip()
    if knowledge_context.get("knowledge_context_used") and context_block:
        project_context_items.append(ContextItem(
            role="project_knowledge",
            content=context_block,
            source_session_id=str(knowledge_context.get("context_pack_id") or ""),
            priority=100,
        ))

    context_packet = ContextManager(max_tokens=context_max_tokens).build(
        input_text,
        policy=context_policy,
        inherited_items=context_items or [],
        persistent_items=project_context_items,
    )
    result = await runtime.run(
        prd_text=context_packet.rendered_input,
        domain_hint=domain,
        project_id=scoped_project_id,
    )

    board_payload = None
    if board:
        board_result = await MultiAgentBoard(store).convene(project_id=scoped_project_id)
        board_payload = {
            "verdict": board_result.final_verdict,
            "consensus": board_result.consensus,
            "votes": board_result.votes,
        }

    output_registration = _register_growth_deliverables(
        result=result,
        project_id=scoped_project_id,
        execution_id=scoped_execution_id,
        knowledge_context=knowledge_context,
    )

    return _runtime_result_to_agent_response(
        result=result,
        project_id=scoped_project_id,
        execution_id=scoped_execution_id,
        artifact_scope=artifact_scope,
        board=board_payload,
        context_usage=context_packet.usage.model_dump(mode="json"),
        knowledge_context=_public_knowledge_context(knowledge_context),
        knowledge_output_registration=output_registration,
    )


class _LegacyBSCCompatibilityPlanner:
    """Fixed one-step plan that makes the legacy compiler a Runtime capability."""

    def __init__(self, capability_name: str) -> None:
        self._capability_name = capability_name

    async def plan(
        self, prd_text: str, domain_hint: str = "", goals: Any = None
    ) -> MissionGraph:
        del prd_text, goals
        return MissionGraph(
            mission_id=f"compatibility_{self._capability_name}",
            mission="legacy_bsc_compatibility",
            title="Legacy BSC Compatibility",
            domain=domain_hint,
            planning_mode="compatibility",
            steps=[
                MissionStep(
                    step_id=self._capability_name,
                    capability_name=self._capability_name,
                    parallel_group=0,
                )
            ],
            required_capabilities=[self._capability_name],
        )


async def run_legacy_bsc_runtime(
    *,
    input_text: str,
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    template_id: str | None = None,
    async_mode: bool = True,
    llm_service: Any = None,
    legacy_context: dict[str, Any] | None = None,
    data_dir: str = "./data/artifacts",
) -> dict[str, Any]:
    """Execute the legacy compiler as a scoped BusinessRuntime capability."""
    result = await _run_legacy_runtime(
        input_text=input_text,
        project_id=project_id,
        execution_id=execution_id,
        tenant_id=tenant_id,
        data_dir=data_dir,
        capability_name="legacy_bsc_compatibility",
        execution_context={
            "template_id": template_id or "",
            "async_mode": async_mode,
            "llm_service": llm_service,
            "legacy_context": legacy_context or {},
        },
    )
    if result.errors:
        raise RuntimeError(result.errors[0])
    return _legacy_compile_payload(result)


def run_legacy_bsc_runtime_sync(**kwargs: Any) -> dict[str, Any]:
    """Run the Runtime compatibility path from synchronous legacy callers."""
    return _run_awaitable_sync(run_legacy_bsc_runtime(**kwargs))


async def run_legacy_bsc_stage_runtime(
    *,
    input_text: str,
    stage_key: str,
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    data_dir: str = "./data/artifacts",
) -> dict[str, Any]:
    """Execute a legacy single-stage operation through BusinessRuntime."""
    result = await _run_legacy_runtime(
        input_text=input_text,
        project_id=project_id,
        execution_id=execution_id,
        tenant_id=tenant_id,
        data_dir=data_dir,
        capability_name="legacy_bsc_stage_compatibility",
        execution_context={"stage_key": stage_key},
    )
    if result.errors:
        raise ValueError(result.errors[0])
    for artifact in result.export.get("_artifact_graph", {}).get("decisions", []):
        metadata = artifact.get("metadata") or {}
        if artifact.get("source_agent") == "legacy_bsc_stage_compatibility":
            return metadata.get("legacy_stage_result") or {}
    raise RuntimeError("legacy stage did not produce a compatibility artifact")


async def _run_legacy_runtime(
    *,
    input_text: str,
    project_id: str,
    execution_id: str,
    tenant_id: str,
    data_dir: str,
    capability_name: str,
    execution_context: dict[str, Any],
) -> RuntimeResult:
    scoped_project_id = project_id.strip() if project_id else new_project_id("legacy")
    scoped_execution_id = execution_id.strip() if execution_id else new_project_id("legacy_run")
    artifact_scope = scoped_artifact_dir(
        data_dir,
        scoped_project_id,
        scoped_execution_id,
        tenant_id,
    )
    store = ArtifactGraphStore(
        data_dir=artifact_scope,
        tenant_id=tenant_id,
        project_id=scoped_project_id,
        session_id=scoped_execution_id,
    )
    registry = build_default_registry()
    runtime = BusinessRuntime(
        store=store,
        registry=registry,
        planner=_LegacyBSCCompatibilityPlanner(capability_name),
        max_iterations=1,
        executor_backend="nanobot",
        execution_context=execution_context,
    )
    return await runtime.run(
        prd_text=input_text,
        project_id=scoped_project_id,
    )


def _legacy_compile_payload(result: RuntimeResult) -> dict[str, Any]:
    business_models = result.export.get("_artifact_graph", {}).get("biz_models", [])
    for artifact in business_models:
        if artifact.get("source_agent") != "legacy_bsc_compatibility":
            continue
        metadata = artifact.get("metadata") or {}
        return {
            "business_system": metadata.get("legacy_business_system") or {},
            "pipeline": metadata.get("legacy_pipeline") or {},
            "workspace": metadata.get("legacy_workspace") or {},
            "summary": str(metadata.get("legacy_summary") or ""),
        }
    raise RuntimeError("legacy compiler did not produce a compatibility artifact")


def _runtime_result_to_agent_response(
    *,
    result: RuntimeResult,
    project_id: str,
    execution_id: str,
    artifact_scope: str,
    board: dict[str, Any] | None,
    context_usage: dict[str, Any] | None = None,
    knowledge_context: dict[str, Any] | None = None,
    knowledge_output_registration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    export = result.export or {}
    graph = export.get("_artifact_graph", {})
    gaps = [_gap_payload(gap) for gap in graph.get("gaps", [])]
    board_payload = _board_payload(board)

    return {
        "status": "failed" if result.errors else "completed",
        "project_id": project_id,
        "execution_id": execution_id,
        "mission": _mission_payload(result),
        "artifacts": _artifact_count(result, graph),
        "gaps": len(gaps),
        "gap_details": gaps,
        "board": board_payload,
        "board_verdict": board_payload["verdict"] if board_payload else "",
        "board_consensus": board_payload["consensus"] if board_payload else "",
        "board_votes": board_payload["votes"] if board_payload else {},
        "runtime": {
            "status": result.status,
            "execution_id": execution_id,
            "artifact_scope": artifact_scope,
            "iterations": result.iterations,
            "elapsed_ms": result.elapsed_ms,
            "errors": result.errors,
            "stage_modes": result.stage_modes,
            "degraded": any(mode == "fallback" for mode in result.stage_modes.values()),
            "capability_executions": result.capability_executions,
            "context": context_usage or {},
            "knowledge_context": knowledge_context or _empty_knowledge_context(),
            "knowledge_output_registration": (
                knowledge_output_registration or _empty_output_registration()
            ),
        },
        "report": export,
    }


def _empty_knowledge_context(*, availability: str = "unavailable") -> dict[str, Any]:
    return {
        "knowledge_context_used": False,
        "context_type": "",
        "availability": availability,
        "context_pack_id": "",
        "profile_revision": 0,
        "rules_revision": "",
        "page_ids": [],
        "source_ids": [],
        "method_revision_ids": [],
        "output_ids": [],
        "rejected_output_ids": [],
        "evaluation_ids": [],
        "feedback_ids": [],
        "assumptions": [],
        "research_gaps": [],
        "omitted_refs": [],
    }


def _empty_output_registration(status: str = "not_attempted") -> dict[str, Any]:
    return {
        "status": status,
        "attempted": 0,
        "registered": 0,
        "output_ids": [],
        "audit_run_ids": [],
        "errors": [],
    }


def _register_growth_deliverables(
    *,
    result: RuntimeResult,
    project_id: str,
    execution_id: str,
    knowledge_context: dict[str, Any],
) -> dict[str, Any]:
    """Stage completed structured deliverables for the project D-layer.

    This is intentionally a registration-only bridge: no Agent OS response is
    accepted or fed back into future context until the existing evaluation and
    feedback lifecycle approves it.  The function is best-effort so a Vault
    issue never rewrites the completed Runtime result.
    """
    if not _runtime_completed(result):
        return _empty_output_registration("not_registered_runtime_incomplete")
    if not knowledge_context.get("knowledge_context_used"):
        return _empty_output_registration("not_registered_without_context")
    if knowledge_context.get("context_type") != "growth":
        return _empty_output_registration("not_registered_non_growth_context")

    deliverables = _runtime_deliverables(result)
    if not deliverables:
        return _empty_output_registration("not_registered_no_deliverables")

    try:
        from app.core.config import settings
        from app.knowledge.growth_repository import GrowthRepository
        from app.knowledge.output_bridges import OutputCompletionBridge

        if not settings.KNOWLEDGE_GROWTH_ENABLED:
            return _empty_output_registration("not_registered_growth_disabled")
        vault_root = Path(settings.OBSIDIAN_VAULT_ROOT)
        if not settings.OBSIDIAN_VAULT_ROOT or not vault_root.is_dir():
            return _empty_output_registration("not_registered_vault_unavailable")

        repository = GrowthRepository()
        if not repository.get_vault(project_id):
            return _empty_output_registration("not_registered_vault_unmapped")
        bridge = OutputCompletionBridge(repository, vault_root)
    except Exception as exc:
        response = _empty_output_registration("not_registered_unavailable")
        response["errors"] = [_registration_error(exc)]
        return response

    response = _empty_output_registration("registration_failed")
    response["attempted"] = len(deliverables)
    for deliverable in deliverables:
        artifact_id = str(deliverable.get("artifact_id") or "").strip()
        if not artifact_id:
            response["errors"].append("deliverable missing artifact id")
            continue
        rendered = _render_deliverable_markdown(deliverable)
        if not rendered:
            response["errors"].append(f"{artifact_id}: deliverable had no reviewable content")
            continue
        bridge_result = bridge.register_agent_runtime_deliverable(
            execution_id=execution_id,
            deliverable_id=artifact_id,
            status="completed",
            result=rendered,
            filename=_deliverable_filename(deliverable, artifact_id),
            context={
                "project_id": project_id,
                "goal": "Project-specific Agent OS deliverable",
                "audience": "project reviewer",
                "channel": "agent_os",
                "provider": "agent_os_runtime",
                "model": "capability_runtime",
                "prompt_revision": "agent-os-deliverable-v1",
                "kind": str(deliverable.get("kind") or "deliverable"),
                "title": _redact_sensitive_text(str(deliverable.get("title") or "")),
                "method_revision_id": _first_context_ref(
                    knowledge_context, "method_revision_ids"
                ),
                "context_revision": str(knowledge_context.get("context_pack_id") or ""),
                "source_refs": _context_refs(knowledge_context, "source_ids"),
                "page_refs": _context_refs(knowledge_context, "page_ids"),
                "metadata": {
                    "artifact_id": artifact_id,
                    "deliverable_kind": str(deliverable.get("kind") or ""),
                    "context_pack_id": str(knowledge_context.get("context_pack_id") or ""),
                    "origin": "agent_os_runtime",
                },
            },
        )
        if bridge_result.output_id:
            response["registered"] += 1
            response["output_ids"].append(bridge_result.output_id)
        if bridge_result.audit_run_id:
            response["audit_run_ids"].append(bridge_result.audit_run_id)
        if bridge_result.error:
            response["errors"].append(_registration_error(Exception(bridge_result.error)))

    if response["registered"] == response["attempted"]:
        response["status"] = "registered"
    elif response["registered"]:
        response["status"] = "partially_registered"
    return response


def _runtime_completed(result: RuntimeResult) -> bool:
    status = str(getattr(result.status, "value", result.status)).lower()
    return status == "completed" and not result.errors


def _runtime_deliverables(result: RuntimeResult) -> list[dict[str, Any]]:
    graph = (result.export or {}).get("_artifact_graph", {})
    candidates = graph.get("deliverables", []) if isinstance(graph, dict) else []
    return [item for item in candidates if isinstance(item, dict)]


def _context_refs(context: dict[str, Any], field_name: str) -> list[str]:
    values = context.get(field_name) or []
    return [str(value) for value in values if str(value).strip()]


def _first_context_ref(context: dict[str, Any], field_name: str) -> str:
    values = _context_refs(context, field_name)
    return values[0] if values else ""


def _deliverable_filename(deliverable: dict[str, Any], artifact_id: str) -> str:
    kind = re.sub(r"[^a-z0-9]+", "-", str(deliverable.get("kind") or "deliverable").lower())
    kind = kind.strip("-") or "deliverable"
    return f"{kind}-{artifact_id[:24]}.md"


def _render_deliverable_markdown(deliverable: dict[str, Any]) -> str:
    """Render only structured work-product fields, never the original prompt."""
    title = _redact_sensitive_text(str(deliverable.get("title") or "").strip())
    summary = _redact_sensitive_text(str(deliverable.get("summary") or "").strip())
    differentiators = _redacted_strings(deliverable.get("differentiators"))
    evidence_gaps = _redacted_strings(deliverable.get("evidence_gaps"))
    sections = deliverable.get("sections") if isinstance(deliverable.get("sections"), list) else []
    actions = deliverable.get("actions") if isinstance(deliverable.get("actions"), list) else []
    if not any((title, summary, differentiators, evidence_gaps, sections, actions)):
        return ""

    lines = [f"# {title or 'Project deliverable'}"]
    if summary:
        lines.extend(["", "## Summary", summary])
    if differentiators:
        lines.extend(["", "## Project-specific differentiators"])
        lines.extend(f"- {item}" for item in differentiators)
    if sections:
        lines.extend(["", "## Work product"])
        for index, section in enumerate(sections, start=1):
            lines.extend(_render_structured_block(section, f"Section {index}"))
    if actions:
        lines.extend(["", "## Recommended actions"])
        for index, action in enumerate(actions, start=1):
            lines.extend(_render_structured_block(action, f"Action {index}", level="###"))
    if evidence_gaps:
        lines.extend(["", "## Evidence gaps before acceptance"])
        lines.extend(f"- {item}" for item in evidence_gaps)
    return "\n".join(lines).strip() + "\n"


def _render_structured_block(value: Any, fallback_heading: str, *, level: str = "###") -> list[str]:
    if not isinstance(value, dict):
        text = _redact_sensitive_text(str(value).strip())
        return [f"{level} {fallback_heading}", text] if text else []
    heading = _redact_sensitive_text(
        str(value.get("title") or value.get("heading") or value.get("name") or fallback_heading)
    )
    body = value.get("content") or value.get("body") or value.get("description") or value.get("detail")
    lines = [f"{level} {heading}"]
    if body:
        lines.append(_redact_sensitive_text(str(body)))
    other_fields = {
        str(key): item
        for key, item in value.items()
        if key not in {"title", "heading", "name", "content", "body", "description", "detail"}
        and item not in (None, "", [], {})
    }
    if other_fields:
        for key, item in other_fields.items():
            rendered = _redact_sensitive_text(
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                if isinstance(item, (dict, list))
                else str(item)
            )
            lines.append(f"- **{key.replace('_', ' ')}:** {rendered}")
    return lines


def _redacted_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        text for text in (_redact_sensitive_text(str(item).strip()) for item in value)
        if text
    ]


_SENSITIVE_OUTPUT_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|secret|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[^\s,;]+"),
)


def _redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_OUTPUT_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _registration_error(exc: Exception) -> str:
    detail = _redact_sensitive_text(str(exc).replace("\n", " ").strip())[:180]
    return f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__


def _retrieve_project_knowledge_context(project_id: str, query: str) -> dict[str, Any]:
    """Prefer growth context, then the legacy Wiki context, without cross-project reads."""
    empty = _empty_knowledge_context()
    if not project_id:
        return empty
    try:
        from app.orchestrator.methodology import MethodologyBridge

        bridge = MethodologyBridge()
        growth = bridge.retrieve_growth_context(project_id, query)
        if growth.get("knowledge_context_used"):
            return {**empty, **growth, "context_type": "growth", "availability": "available"}
        wiki = bridge.retrieve_wiki_context(project_id, query)
        if wiki.get("knowledge_context_used"):
            return {
                **empty,
                **wiki,
                "context_type": "wiki",
                "availability": "available",
                "research_gaps": list(growth.get("research_gaps") or []),
                "omitted_refs": list(wiki.get("omitted_refs") or []),
            }
        return {**empty, **growth}
    except Exception as exc:
        return {**empty, "availability": "unavailable", "error": type(exc).__name__}


def _public_knowledge_context(context: dict[str, Any]) -> dict[str, Any]:
    """Expose provenance and availability, never the Vault text injected into a prompt."""
    allowed = set(_empty_knowledge_context())
    return {
        key: value
        for key, value in context.items()
        if key in allowed
    } | {
        key: value
        for key, value in _empty_knowledge_context().items()
        if key not in context
    }


def _artifact_count(result: RuntimeResult, graph: dict[str, Any]) -> int:
    if result.artifact_graph is not None:
        return result.artifact_graph.count()
    total = graph.get("total_artifacts")
    return total if isinstance(total, int) else 0


def _mission_payload(result: RuntimeResult) -> dict[str, Any]:
    mission = getattr(result, "mission", None)
    if isinstance(mission, dict):
        return {
            "title": mission.get("title", ""),
            "steps": mission.get("steps", 0),
            "mode": mission.get("mode", ""),
        }
    return {"title": "", "steps": 0, "mode": ""}


def _board_payload(board: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(board, dict):
        return None
    return {
        "verdict": str(board.get("verdict", "") or ""),
        "consensus": str(board.get("consensus", "") or ""),
        "votes": board.get("votes", {}) if isinstance(board.get("votes"), dict) else {},
    }


def _gap_payload(gap: Any) -> dict[str, str]:
    if not isinstance(gap, dict):
        return {
            "description": str(gap),
            "category": "",
            "severity": "",
        }
    return {
        "description": str(
            gap.get("description")
            or gap.get("gap_statement")
            or gap.get("gap")
            or gap.get("label")
            or ""
        ),
        "category": str(gap.get("category", "") or ""),
        "severity": str(gap.get("severity", "") or ""),
    }


def _safe_path_segment(value: str) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
        for ch in value.strip()
    )
    return (safe[:96] or "default")


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    parameters = inspect.signature(callable_obj).parameters.values()
    return any(
        parameter.name == keyword or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _run_awaitable_sync(awaitable):
    """Bridge synchronous compatibility APIs without bypassing BusinessRuntime."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def run_in_worker() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # Re-raise the original compatibility failure.
            error.append(exc)

    worker = threading.Thread(target=run_in_worker, daemon=False)
    worker.start()
    worker.join()
    if error:
        raise error[0]
    return result["value"]
