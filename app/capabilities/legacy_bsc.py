"""Legacy BSC pipeline compatibility adapter for BusinessRuntime."""

from __future__ import annotations

import asyncio
from typing import Any

from app.artifacts.types import (
    BusinessModelArtifact,
    DecisionArtifact,
    RiskArtifact,
    RiskDimension,
    Severity,
)


async def compile_to_business_system_async(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Resolve the legacy async compiler lazily for compatibility and tests."""
    from app.core.async_pipeline import compile_to_business_system_async as compile_async

    return await compile_async(*args, **kwargs)


def compile_to_business_system(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Resolve the legacy synchronous compiler lazily for compatibility and tests."""
    from app.core.bsc_pipeline import compile_to_business_system as compile_sync

    return compile_sync(*args, **kwargs)


async def run_legacy_bsc_compatibility(
    *,
    input_text: str,
    project_id: str = "",
    async_mode: bool = True,
    execution_context: dict[str, Any] | None = None,
    **_: Any,
) -> list[BusinessModelArtifact | RiskArtifact | DecisionArtifact]:
    """Run the legacy BSC compiler and project its result into typed artifacts."""
    context = execution_context or {}
    async_mode = bool(context.get("async_mode", async_mode))
    template_id = context.get("template_id") or None
    llm_service = context.get("llm_service")
    legacy_context = context.get("legacy_context") or None

    if async_mode:
        async_kwargs = {
            "llm_service": llm_service,
            "template_id": template_id,
        }
        if legacy_context:
            async_kwargs["context"] = legacy_context
        result = await compile_to_business_system_async(input_text, **async_kwargs)
    else:
        result = await asyncio.to_thread(
            compile_to_business_system,
            input_text,
            llm_service=llm_service,
            template_id=template_id,
        )
    return business_system_to_artifacts(
        result.get("business_system") or {},
        project_id=project_id,
        summary=result.get("summary", ""),
        pipeline=result.get("pipeline") or {},
        workspace=result.get("workspace") or {},
    )


async def run_legacy_bsc_stage_compatibility(
    *,
    input_text: str,
    project_id: str = "",
    execution_context: dict[str, Any] | None = None,
    **_: Any,
) -> DecisionArtifact:
    """Run one legacy stage while preserving Runtime ownership of execution."""
    stage_key = str((execution_context or {}).get("stage_key") or "")
    if not stage_key:
        raise ValueError("legacy stage key is required")
    from app.core.bsc_pipeline import BSC_PIPELINE

    result = await asyncio.to_thread(
        BSC_PIPELINE.execute_stage,
        stage_key,
        [{"chunk_id": "001", "content": input_text}],
    )
    return DecisionArtifact(
        project_id=project_id,
        label=f"Legacy BSC stage: {stage_key}",
        decision_statement=f"Legacy stage {stage_key} completed",
        source_agent="legacy_bsc_stage_compatibility",
        tags=["legacy", "compatibility", "bsc"],
        metadata={
            "legacy_stage_key": stage_key,
            "legacy_stage_result": result,
        },
    )


def business_system_to_artifacts(
    business_system: dict[str, Any],
    *,
    project_id: str,
    summary: str = "",
    pipeline: dict[str, Any] | None = None,
    workspace: dict[str, Any] | None = None,
) -> list[BusinessModelArtifact | RiskArtifact | DecisionArtifact]:
    """Convert legacy BSC business-system payloads into Artifact Graph records."""
    domain = str(business_system.get("business_domain", "") or "")
    objectives = _normalize_objectives(business_system.get("objectives"))
    workflow = _as_list(business_system.get("workflow"))
    roles = _as_list(business_system.get("roles"))
    responsibilities = _as_list(business_system.get("responsibilities"))
    sla = _as_list(business_system.get("sla"))
    metrics = _as_list(business_system.get("metrics"))
    kpi = _as_list(business_system.get("kpi"))

    business_model = BusinessModelArtifact(
        project_id=project_id,
        label=domain or "Legacy BSC Business Model",
        description=summary,
        domain=domain,
        objectives=objectives,
        key_activities=_extract_labels(workflow, ("name", "action")),
        key_resources=_extract_labels(roles, ("role", "name")),
        metadata={
            "workflow": workflow,
            "roles": roles,
            "responsibilities": responsibilities,
            "sla": sla,
            "metrics": metrics,
            "kpi": kpi,
            "legacy_business_system": business_system,
            "legacy_pipeline": pipeline or {},
            "legacy_workspace": workspace or {},
            "legacy_summary": summary,
        },
        source_agent="legacy_bsc_compatibility",
        tags=["legacy", "compatibility", "bsc"],
    )

    artifacts: list[BusinessModelArtifact | RiskArtifact | DecisionArtifact] = [business_model]

    for item in _as_list(business_system.get("risks")):
        if not isinstance(item, dict):
            continue
        artifacts.append(RiskArtifact(
            project_id=project_id,
            label=str(item.get("risk", "Legacy risk"))[:80],
            risk_statement=str(item.get("risk", "")),
            severity=_parse_severity(item.get("severity")),
            probability=_parse_severity(item.get("probability")),
            mitigation=str(item.get("mitigation", "")),
            parent_ids=[business_model.artifact_id],
            affected_artifact_ids=[business_model.artifact_id],
            source_agent="legacy_bsc_compatibility",
            tags=["legacy", "compatibility", "bsc"],
            dimension=_infer_risk_dimension(item),
        ))

    report = business_system.get("report") or {}
    decision_statement = ""
    if isinstance(report, dict):
        decision_statement = str(
            report.get("executive_summary")
            or report.get("title")
            or summary
        )
    if decision_statement:
        artifacts.append(DecisionArtifact(
            project_id=project_id,
            label="Legacy BSC Recommendation",
            decision_statement=decision_statement,
            rationale=str(summary or report.get("title", "")) if isinstance(report, dict) else str(summary),
            parent_ids=[business_model.artifact_id],
            source_agent="legacy_bsc_compatibility",
            tags=["legacy", "compatibility", "bsc"],
        ))

    return artifacts


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_objectives(value: Any) -> list[str]:
    normalized: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            objective = item.get("objective") or item.get("title") or item.get("name")
            if objective:
                normalized.append(str(objective))
        elif item:
            normalized.append(str(item))
    return normalized


def _extract_labels(items: list[Any], keys: tuple[str, ...]) -> list[str]:
    labels: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    labels.append(str(item[key]))
                    break
        elif item:
            labels.append(str(item))
    return labels


def _parse_severity(value: Any) -> Severity:
    raw = str(value or "medium").strip().lower()
    mapping = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    return mapping.get(raw, Severity.MEDIUM)


def _infer_risk_dimension(item: dict[str, Any]) -> RiskDimension:
    text = " ".join(
        str(item.get(key, ""))
        for key in ("dimension", "category", "group", "risk")
    ).lower()
    mapping = {
        "process": RiskDimension.PROCESS,
        "organization": RiskDimension.ORGANIZATION,
        "system": RiskDimension.SYSTEM,
        "compliance": RiskDimension.COMPLIANCE,
        "market": RiskDimension.MARKET,
        "financial": RiskDimension.FINANCIAL,
        "technology": RiskDimension.TECHNOLOGY,
        "legal": RiskDimension.LEGAL,
        "operational": RiskDimension.OPERATIONAL,
        "strategic": RiskDimension.STRATEGIC,
    }
    for key, dimension in mapping.items():
        if key in text:
            return dimension
    return RiskDimension.OPERATIONAL
