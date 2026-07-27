"""Tenant-scoped, metadata-only operations projection for knowledge assets."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable

from app.artifacts import (
    ArtifactGraphStore,
    AssumptionArtifact,
    ExecutionResultArtifact,
    GapArtifact,
    MemoryArtifact,
    RiskArtifact,
    RuntimeContextArtifact,
    SOPRoutingEvaluationArtifact,
    TaskVerificationArtifact,
)
from app.knowledge.growth_contracts import is_verified_output_status
from app.knowledge.operations_contracts import (
    OperationalAction,
    OperationsCoverage,
    OperationsFreshness,
    OperationsDrilldown,
    OperationsMetric,
    OperationsMetricState,
    OperationsProjectMetrics,
    OperationsProjectSummary,
    OperationsScope,
)


_ACTION_ORDER = {
    "unresolved_risk": 0,
    "evidence_gap": 1,
    "failed_verification": 2,
    "unverified_execution": 3,
    "unvalidated_assumption": 4,
    "pending_proposal": 5,
}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_PUBLISHABLE_SOURCE_STATUSES = {"eligible", "processed"}
_PENDING_METHOD_STATUSES = {"candidate", "validating", "approved"}
# A single completed run is useful evidence, but not a reliable performance rate.
MINIMUM_AGENT_SAMPLE_SIZE = 3


class KnowledgeOperationsService:
    """Build a bounded read model from project-scoped durable records only."""

    def __init__(
        self,
        *,
        repository: Any,
        project_repository: Any,
        dbos_store_factory: Callable[[str, str], ArtifactGraphStore] | None = None,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.dbos_store_factory = dbos_store_factory or self._default_dbos_store

    @staticmethod
    def _default_dbos_store(project_id: str, tenant_id: str) -> ArtifactGraphStore:
        """Resolve the shared tenant/project DBOS ledger for the read model."""
        from app.api.dbos_api import dbos_service_for

        return dbos_service_for(project_id, tenant_id=tenant_id).store

    def overview(self, scope: OperationsScope) -> dict[str, Any]:
        project_records = self._authorized_project_records(scope)
        projects = [str(project["id"]) for project in project_records]
        snapshots = [self._project_snapshot(project_id, scope.tenant_id, scope) for project_id in projects]
        actions = self._actions(snapshots)
        project_summaries = self._project_summaries(project_records, snapshots, actions)

        sources = sum(len(snapshot["sources"]) for snapshot in snapshots)
        pages = sum(len(snapshot["pages"]) for snapshot in snapshots)
        methods = sum(len(snapshot["methods"]) for snapshot in snapshots)
        outputs = sum(len(snapshot["outputs"]) for snapshot in snapshots)
        memories = sum(len(snapshot["memories"]) for snapshot in snapshots)
        verified = sum(snapshot["verified"] for snapshot in snapshots)
        pending = sum(snapshot["pending_validation"] for snapshot in snapshots)
        attention = sum(snapshot["requires_attention"] for snapshot in snapshots)
        durable_references = sum(snapshot["durable_references"] for snapshot in snapshots)
        record_count = sources + pages + methods + outputs + memories
        unavailable_dbos = [snapshot["project_id"] for snapshot in snapshots if snapshot["dbos_unavailable"]]
        coverage = OperationsCoverage(
            state=(OperationsMetricState.UNAVAILABLE if unavailable_dbos else OperationsMetricState.AVAILABLE),
            record_count=record_count,
            reason=(
                "DBOS lifecycle records are unavailable for: " + ", ".join(unavailable_dbos)
                if unavailable_dbos
                else ""
            ),
        ).model_dump(mode="json")

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "tenant_id": scope.tenant_id,
                "role": scope.role,
                "project_ids": projects,
                "selected_project_id": scope.selected_project_id,
                "mode": "portfolio" if scope.is_portfolio else "project",
            },
            "project_count": len(projects),
            "coverage": coverage,
            "metrics": {
                "assets": {
                    "sources": self._metric("sources", sources),
                    "pages": self._metric("pages", pages),
                    "methods": self._metric("methods", methods),
                    "outputs": self._metric("outputs", outputs),
                    "memories": self._metric("memories", memories),
                },
                "quality": {
                    "verified": self._metric("verified", verified),
                    "pending_validation": self._metric("pending_validation", pending),
                    "requires_attention": self._metric("requires_attention", attention),
                },
                "reuse": {
                    "durable_references": self._metric("durable_references", durable_references),
                },
                "agent_evolution": self._agent_metrics(snapshots),
            },
            "trends": {
                "asset_growth": self._asset_growth(snapshots),
                "agent_evolution": self._agent_evolution_trend(snapshots),
            },
            "project_summaries": project_summaries,
            "actions": actions,
        }

    def _authorized_projects(self, scope: OperationsScope) -> list[str]:
        return [str(project["id"]) for project in self._authorized_project_records(scope)]

    def _authorized_project_records(self, scope: OperationsScope) -> list[dict[str, Any]]:
        tenant_projects = {
            str(project["id"]): project
            for project in self.project_repository.list_projects_for_tenant(scope.tenant_id)
        }
        requested = set(scope.project_ids)
        permitted = set(tenant_projects) & requested if requested else set(tenant_projects)
        if scope.selected_project_id:
            permitted &= {scope.selected_project_id}
        return [tenant_projects[project_id] for project_id in sorted(permitted)]

    def _project_snapshot(self, project_id: str, tenant_id: str, scope: OperationsScope) -> dict[str, Any]:
        sources = self._within_interval(self.repository.list_sources(project_id), scope)
        pages = self._within_interval(self.repository.list_pages(project_id), scope)
        methods = self._within_interval(self.repository.list_methods(project_id, limit=500), scope)
        outputs = self._within_interval(self.repository.list_outputs(project_id, limit=500), scope)
        proposals = self._within_interval(self.repository.list_method_proposals(project_id, limit=500), scope)
        failures = self._within_interval(self.repository.list_failure_records(project_id, limit=500), scope)
        artifacts, dbos_unavailable = self._artifacts(project_id, tenant_id)

        memories = [artifact for artifact in artifacts if isinstance(artifact, MemoryArtifact)]
        contexts = [artifact for artifact in artifacts if isinstance(artifact, RuntimeContextArtifact)]
        executions = [artifact for artifact in artifacts if isinstance(artifact, ExecutionResultArtifact)]
        verifications = [artifact for artifact in artifacts if isinstance(artifact, TaskVerificationArtifact)]
        routing = [artifact for artifact in artifacts if isinstance(artifact, SOPRoutingEvaluationArtifact)]
        verified_execution_ids = {
            artifact.execution_id
            for artifact in verifications
            if artifact.execution_id
        }

        verified = (
            sum(str(source.get("status") or "") in _PUBLISHABLE_SOURCE_STATUSES for source in sources)
            + sum(str(method.get("status") or "") == "published" for method in methods)
            + sum(is_verified_output_status(output.get("status")) for output in outputs)
        )
        pending_validation = (
            sum(str(source.get("status") or "") == "validated" for source in sources)
            + sum(str(method.get("status") or "") in {"candidate", "validating"} for method in methods)
            + sum(str(output.get("status") or "") in {"registered", "evaluating"} for output in outputs)
        )
        requires_attention = (
            sum(str(source.get("status") or "") in {"rejected", "superseded"} for source in sources)
            + len([failure for failure in failures if str(failure.get("status") or "") != "resolved"])
            + sum(
                isinstance(artifact, RiskArtifact) and self._severity(artifact.severity) in {"critical", "high"}
                or isinstance(artifact, GapArtifact) and not artifact.resolved
                or isinstance(artifact, TaskVerificationArtifact) and artifact.verification_status == "failed"
                or isinstance(artifact, ExecutionResultArtifact)
                and artifact.execution_status == "completed"
                and artifact.execution_id not in verified_execution_ids
                or isinstance(artifact, AssumptionArtifact)
                and not artifact.validated
                and self._severity(artifact.criticality) == "critical"
                for artifact in artifacts
            )
        )
        durable_references = sum(bool(output.get("method_revision_id")) for output in outputs)
        durable_references += sum(len(context.method_ids) for context in contexts)

        return {
            "project_id": project_id,
            "sources": sources,
            "pages": pages,
            "methods": methods,
            "outputs": outputs,
            "proposals": proposals,
            "artifacts": artifacts,
            "memories": memories,
            "executions": executions,
            "verifications": verifications,
            "routing": routing,
            "verified": verified,
            "pending_validation": pending_validation,
            "requires_attention": requires_attention,
            "durable_references": durable_references,
            "dbos_unavailable": dbos_unavailable,
        }

    def _project_summaries(
        self,
        project_records: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        snapshots_by_id = {str(snapshot["project_id"]): snapshot for snapshot in snapshots}
        actions_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for action in actions:
            actions_by_project[str(action["project_id"])].append(action)
        return [
            self._project_summary(
                project,
                snapshots_by_id[str(project["id"])],
                actions_by_project.get(str(project["id"]), []),
            )
            for project in project_records
        ]

    def _project_summary(
        self,
        project: dict[str, Any],
        snapshot: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        project_id = str(project["id"])
        asset_count = len(snapshot["sources"]) + len(snapshot["pages"]) + len(snapshot["methods"]) + len(snapshot["outputs"]) + len(snapshot["memories"])
        coverage = OperationsCoverage(
            state=OperationsMetricState.UNAVAILABLE if snapshot["dbos_unavailable"] else OperationsMetricState.AVAILABLE,
            record_count=asset_count,
            reason="DBOS lifecycle records are unavailable for this authorized project." if snapshot["dbos_unavailable"] else "",
        )
        summary = OperationsProjectSummary(
            project_id=project_id,
            project_name=str(project.get("name") or project_id).strip() or project_id,
            coverage=coverage,
            freshness=self._project_freshness(snapshot),
            metrics=OperationsProjectMetrics(
                asset_count=OperationsMetric(key="asset_count", state=OperationsMetricState.AVAILABLE, value=asset_count, record_count=asset_count),
                verified=OperationsMetric(key="verified", state=OperationsMetricState.AVAILABLE, value=snapshot["verified"], record_count=snapshot["verified"]),
                pending_validation=OperationsMetric(key="pending_validation", state=OperationsMetricState.AVAILABLE, value=snapshot["pending_validation"], record_count=snapshot["pending_validation"]),
                risk_debt=OperationsMetric(key="risk_debt", state=OperationsMetricState.AVAILABLE, value=snapshot["requires_attention"], record_count=snapshot["requires_attention"]),
                durable_references=OperationsMetric(key="durable_references", state=OperationsMetricState.AVAILABLE, value=snapshot["durable_references"], record_count=snapshot["durable_references"]),
            ),
            highest_priority_action=OperationalAction.model_validate(actions[0]) if actions else None,
        )
        return summary.model_dump(mode="json")

    def _project_freshness(self, snapshot: dict[str, Any]) -> OperationsFreshness:
        activities: list[datetime] = []
        for records, keys in (
            (snapshot["sources"], ("updated_at", "captured_at", "created_at")),
            (snapshot["pages"], ("updated_at", "created_at")),
            (snapshot["methods"], ("updated_at", "created_at")),
            (snapshot["outputs"], ("updated_at", "created_at")),
        ):
            for record in records:
                value = next((record.get(key) for key in keys if record.get(key)), None)
                if value:
                    activities.append(self._timestamp(value))
        activities.extend(self._timestamp(getattr(artifact, "created_at", None)) for artifact in snapshot["artifacts"] if getattr(artifact, "created_at", None))
        if not activities:
            return OperationsFreshness(
                state=OperationsMetricState.INSUFFICIENT_SAMPLE,
                record_count=0,
                reason="no persisted activity timestamp is available for this project",
            )
        return OperationsFreshness(
            state=OperationsMetricState.AVAILABLE,
            latest_activity_at=max(activities),
            record_count=len(activities),
        )

    def _artifacts(self, project_id: str, tenant_id: str) -> tuple[list[Any], bool]:
        try:
            return self.dbos_store_factory(project_id, tenant_id).get_by_project(project_id), False
        except (OSError, ValueError, KeyError):
            return [], True

    def _agent_metrics(self, snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        verifications = [artifact for snapshot in snapshots for artifact in snapshot["verifications"]]
        completed = [artifact for artifact in verifications if artifact.verification_status in {"passed", "failed"}]
        passed = [artifact for artifact in completed if artifact.verification_status == "passed"]
        attempts = [artifact.attempt for snapshot in snapshots for artifact in snapshot["executions"]]
        routing = [artifact for snapshot in snapshots for artifact in snapshot["routing"] if artifact.holdout_case_count > 0]
        routing_passed = [artifact for artifact in routing if artifact.holdout_passed]

        return {
            "verification_pass_rate": self._sample_metric(
                "verification_pass_rate", len(passed) * 100.0 / len(completed) if completed else None,
                len(completed), "percent", "no passed or failed task verifications"
            ),
            "median_execution_attempt": self._sample_metric(
                "median_execution_attempt", float(median(attempts)) if attempts else None,
                len(attempts), "attempts", "no persisted execution attempts"
            ),
            "routing_holdout_pass_rate": self._sample_metric(
                "routing_holdout_pass_rate", len(routing_passed) * 100.0 / len(routing) if routing else None,
                len(routing), "percent", "no routing holdout evaluations"
            ),
        }

    def _asset_growth(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"sources": 0, "methods": 0, "outputs": 0})
        for snapshot in snapshots:
            for source in snapshot["sources"]:
                self._increment_bucket(buckets, source.get("captured_at") or source.get("created_at"), "sources")
            for method in snapshot["methods"]:
                self._increment_bucket(buckets, method.get("created_at"), "methods")
            for output in snapshot["outputs"]:
                self._increment_bucket(buckets, output.get("created_at"), "outputs")
        return [{"date": date, **buckets[date]} for date in sorted(buckets)]

    def _agent_evolution_trend(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expose only date buckets supported by persisted agent evidence."""
        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "verification_total": 0,
                "verification_passed": 0,
                "attempts": [],
                "routing_total": 0,
                "routing_passed": 0,
            }
        )
        for snapshot in snapshots:
            for artifact in snapshot["verifications"]:
                if artifact.verification_status not in {"passed", "failed"}:
                    continue
                bucket = buckets[self._timestamp(artifact.created_at).date().isoformat()]
                bucket["verification_total"] += 1
                bucket["verification_passed"] += artifact.verification_status == "passed"
            for artifact in snapshot["executions"]:
                bucket = buckets[self._timestamp(artifact.created_at).date().isoformat()]
                bucket["attempts"].append(artifact.attempt)
            for artifact in snapshot["routing"]:
                if artifact.holdout_case_count <= 0:
                    continue
                bucket = buckets[self._timestamp(artifact.created_at).date().isoformat()]
                bucket["routing_total"] += 1
                bucket["routing_passed"] += artifact.holdout_passed

        return [
            {
                "date": date,
                "verification_pass_rate": round(bucket["verification_passed"] * 100.0 / bucket["verification_total"], 2)
                if bucket["verification_total"] >= MINIMUM_AGENT_SAMPLE_SIZE else None,
                "verification_sample_count": bucket["verification_total"],
                "median_execution_attempt": round(float(median(bucket["attempts"])), 2)
                if len(bucket["attempts"]) >= MINIMUM_AGENT_SAMPLE_SIZE else None,
                "execution_sample_count": len(bucket["attempts"]),
                "routing_holdout_pass_rate": round(bucket["routing_passed"] * 100.0 / bucket["routing_total"], 2)
                if bucket["routing_total"] >= MINIMUM_AGENT_SAMPLE_SIZE else None,
                "routing_sample_count": bucket["routing_total"],
            }
            for date, bucket in sorted(buckets.items())
        ]

    def _actions(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actions: list[OperationalAction] = []
        for snapshot in snapshots:
            project_id = snapshot["project_id"]
            artifacts = snapshot["artifacts"]
            verified_execution_ids = {
                artifact.execution_id
                for artifact in snapshot["verifications"]
                if artifact.execution_id
            }
            for artifact in artifacts:
                if isinstance(artifact, RiskArtifact) and self._severity(artifact.severity) in {"critical", "high"}:
                    actions.append(self._artifact_action(project_id, "unresolved_risk", self._severity(artifact.severity), artifact, "Review the unresolved risk and its existing mitigation."))
                elif isinstance(artifact, GapArtifact) and not artifact.resolved:
                    actions.append(self._artifact_action(project_id, "evidence_gap", self._severity(artifact.severity), artifact, "Collect or review the missing evidence before advancing the decision."))
                elif isinstance(artifact, TaskVerificationArtifact) and artifact.verification_status == "failed":
                    actions.append(self._artifact_action(project_id, "failed_verification", "high", artifact, "Inspect the failed verification and run the existing correction workflow."))
                elif isinstance(artifact, ExecutionResultArtifact) and artifact.execution_status == "completed" and artifact.execution_id not in verified_execution_ids:
                    actions.append(self._artifact_action(project_id, "unverified_execution", "medium", artifact, "Verify the completed execution before treating it as reusable evidence."))
                elif isinstance(artifact, AssumptionArtifact) and not artifact.validated and self._severity(artifact.criticality) == "critical":
                    actions.append(self._artifact_action(project_id, "unvalidated_assumption", "critical", artifact, "Validate the critical assumption or record its decision impact."))
            for proposal in snapshot["proposals"]:
                if str(proposal.get("status") or "") not in _PENDING_METHOD_STATUSES:
                    continue
                proposal_id = str(proposal["id"])
                actions.append(OperationalAction(
                    id=f"action:pending_proposal:{proposal_id}",
                    project_id=project_id,
                    kind="pending_proposal",
                    severity="medium",
                    source_refs=(f"method_proposal:{proposal_id}",),
                    recommendation="Review the governed method proposal before it can change the reusable method library.",
                    created_at=self._timestamp(proposal.get("created_at")),
                    drilldown=OperationsDrilldown(surface="growth", entity_id=proposal_id),
                ))
        actions.sort(key=lambda action: (
            _ACTION_ORDER.get(action.kind, len(_ACTION_ORDER)),
            _SEVERITY_ORDER.get(action.severity, _SEVERITY_ORDER["info"]),
            action.created_at.timestamp(),
            action.id,
        ))
        return [action.model_dump(mode="json") for action in actions]

    def _artifact_action(self, project_id: str, kind: str, severity: str, artifact: Any, recommendation: str) -> OperationalAction:
        return OperationalAction(
            id=f"action:{kind}:{artifact.artifact_id}",
            project_id=project_id,
            kind=kind,
            severity=severity,
            source_refs=(f"artifact:{artifact.artifact_id}",),
            recommendation=recommendation,
            created_at=self._timestamp(artifact.created_at),
            drilldown=OperationsDrilldown(
                surface="dbos",
                entity_id=artifact.artifact_id,
                mission_id=str(getattr(artifact, "mission_id", "") or ""),
            ),
        )

    @staticmethod
    def _metric(key: str, value: int) -> dict[str, Any]:
        return OperationsMetric(
            key=key,
            state=OperationsMetricState.AVAILABLE,
            value=value,
            record_count=value,
        ).model_dump(mode="json")

    @staticmethod
    def _sample_metric(key: str, value: float | None, count: int, unit: str, reason: str) -> dict[str, Any]:
        if value is None:
            return OperationsMetric(
                key=key,
                state=OperationsMetricState.INSUFFICIENT_SAMPLE,
                value=None,
                unit=unit,
                record_count=0,
                reason=reason,
            ).model_dump(mode="json")
        if count < MINIMUM_AGENT_SAMPLE_SIZE:
            return OperationsMetric(
                key=key,
                state=OperationsMetricState.INSUFFICIENT_SAMPLE,
                value=None,
                unit=unit,
                record_count=count,
                reason=f"requires at least {MINIMUM_AGENT_SAMPLE_SIZE} persisted samples; {count} available",
            ).model_dump(mode="json")
        return OperationsMetric(
            key=key,
            state=OperationsMetricState.AVAILABLE,
            value=round(value, 2),
            unit=unit,
            record_count=count,
        ).model_dump(mode="json")

    @staticmethod
    def _severity(value: Any) -> str:
        return str(getattr(value, "value", value) or "medium").lower()

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _within_interval(self, records: list[dict[str, Any]], scope: OperationsScope) -> list[dict[str, Any]]:
        if scope.interval is None:
            return records
        return [
            record for record in records
            if scope.interval.start_at <= self._timestamp(record.get("created_at") or record.get("captured_at")) < scope.interval.end_at
        ]

    def _increment_bucket(self, buckets: dict[str, dict[str, Any]], value: Any, key: str) -> None:
        timestamp = self._timestamp(value)
        buckets[timestamp.date().isoformat()][key] += 1
