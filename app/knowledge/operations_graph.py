"""Bounded, metadata-only lifecycle graph projection for knowledge operations."""

from __future__ import annotations

import base64
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from app.artifacts import (
    ArtifactGraphStore,
    AssumptionArtifact,
    BaseArtifact,
    CapabilitySelectionArtifact,
    ConstraintArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    EvidenceArtifact,
    ExecutionResultArtifact,
    GapArtifact,
    MemoryArtifact,
    MissionArtifact,
    RiskArtifact,
    RuntimeContextArtifact,
    TaskVerificationArtifact,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsInterval, OperationsScope
from app.repositories.knowledge_repository import KnowledgeRepository


_LANES = (
    ("evidence_source", "Evidence", 0),
    ("mission", "Business problem", 1),
    ("assumption", "Assumptions", 2),
    ("risk_constraint", "Risks and constraints", 3),
    ("method_sop", "Methods and SOPs", 4),
    ("validation", "Validation", 5),
    ("memory_feedback", "Memory and feedback", 6),
)
_LANE_ORDER = {lane: order for lane, _label, order in _LANES}


def _at(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cursor_for(lane_order: int, created_at: str, node_id: str) -> str:
    raw = f"{lane_order}|{created_at}|{node_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _parse_cursor(value: str) -> tuple[int, str, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        lane_order, created_at, node_id = decoded.split("|", 2)
        parsed_order = int(lane_order)
    except Exception:
        raise ValueError("invalid lifecycle graph cursor") from None
    if not created_at or not node_id:
        raise ValueError("invalid lifecycle graph cursor")
    return parsed_order, created_at, node_id


class KnowledgeOperationsGraphService:
    """Create a visual projection without changing either graph's persistence."""

    def __init__(
        self,
        *,
        repository: GrowthRepository,
        project_repository: KnowledgeRepository,
        dbos_store_factory: Callable[[str, str], ArtifactGraphStore] | None = None,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.dbos_store_factory = dbos_store_factory or self._default_dbos_store

    @staticmethod
    def _default_dbos_store(project_id: str, tenant_id: str) -> ArtifactGraphStore:
        from app.api.dbos_api import dbos_service_for

        return dbos_service_for(project_id, tenant_id=tenant_id).store

    def project_graph(
        self,
        scope: OperationsScope,
        *,
        project_id: str,
        mission_id: str = "",
        node_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        relations: Iterable[str] = (),
        interval: OperationsInterval | None = None,
        limit: int = 200,
        cursor: str = "",
    ) -> dict[str, Any]:
        self._require_project(scope, project_id)
        bounded_limit = max(1, min(int(limit), 500))
        requested_types = {str(value).strip() for value in node_types if str(value).strip()}
        requested_statuses = {str(value).strip() for value in statuses if str(value).strip()}
        requested_relations = {str(value).strip() for value in relations if str(value).strip()}
        if len(requested_types) > 50 or len(requested_statuses) > 50 or len(requested_relations) > 50:
            raise ValueError("lifecycle graph filters exceed the maximum of 50 values")

        store = self.dbos_store_factory(project_id, scope.tenant_id)
        artifacts = store.get_by_project(project_id)
        if mission_id:
            artifacts = self._mission_slice(artifacts, mission_id)
        nodes, edges, missing_endpoints = self._build_projection(project_id, artifacts, mission_id)

        filtered_nodes = {
            node_id: node
            for node_id, node in nodes.items()
            if self._matches_node(node, requested_types, requested_statuses, interval)
        }
        filtered_edges = [
            edge
            for edge in edges
            if edge["source"] in filtered_nodes
            and edge["target"] in filtered_nodes
            and (not requested_relations or edge["relation"] in requested_relations)
        ]
        if requested_relations:
            related_ids = {endpoint for edge in filtered_edges for endpoint in (edge["source"], edge["target"])}
            filtered_nodes = {node_id: node for node_id, node in filtered_nodes.items() if node_id in related_ids}

        ordered_nodes = sorted(filtered_nodes.values(), key=self._node_sort_key)
        position = _parse_cursor(cursor)
        if position:
            ordered_nodes = [node for node in ordered_nodes if self._node_sort_key(node) > position]
        visible_nodes = ordered_nodes[:bounded_limit]
        visible_ids = {node["id"] for node in visible_nodes}
        visible_edges = [
            edge for edge in filtered_edges if edge["source"] in visible_ids and edge["target"] in visible_ids
        ]
        omitted_node_count = max(len(ordered_nodes) - len(visible_nodes), 0)
        omitted_endpoint_count = missing_endpoints + sum(
            1
            for edge in filtered_edges
            if edge["source"] not in visible_ids or edge["target"] not in visible_ids
        )
        next_cursor = (
            _cursor_for(
                _LANE_ORDER.get(str(visible_nodes[-1]["lane"]), 99),
                str(visible_nodes[-1]["created_at"]),
                str(visible_nodes[-1]["id"]),
            )
            if len(ordered_nodes) > len(visible_nodes) and visible_nodes
            else None
        )
        lifecycle_audit = self._lifecycle_audit(
            visible_nodes,
            visible_edges,
            scope="visible_page" if next_cursor is not None else "filtered_graph",
        )
        return {
            "project_id": project_id,
            "mission_id": mission_id,
            "lanes": [
                {"id": lane, "label": label, "order": order}
                for lane, label, order in _LANES
            ],
            "nodes": visible_nodes,
            "edges": sorted(visible_edges, key=lambda edge: (edge["relation"], edge["source"], edge["target"], edge["id"])),
            "pagination": {
                "limit": bounded_limit,
                "next_cursor": next_cursor,
                "truncated": next_cursor is not None,
                "omitted_node_count": omitted_node_count,
                "omitted_endpoint_count": omitted_endpoint_count,
            },
            "lifecycle_audit": lifecycle_audit,
        }

    def _require_project(self, scope: OperationsScope, project_id: str) -> None:
        if scope.project_ids and project_id not in scope.project_ids:
            raise PermissionError("project is outside the authorized operations scope")
        if not self.project_repository.get_project_for_tenant(project_id, scope.tenant_id):
            raise PermissionError("project is outside the tenant scope")

    def _build_projection(
        self, project_id: str, artifacts: list[BaseArtifact], mission_id: str
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], int]:
        nodes = {artifact.artifact_id: self._artifact_node(artifact) for artifact in artifacts}
        edges: list[dict[str, str]] = []
        missing_endpoints = 0
        for artifact in artifacts:
            for parent_id in artifact.parent_ids:
                if parent_id not in nodes:
                    missing_endpoints += 1
                    continue
                edges.append(
                    self._edge(
                        edge_id=f"dbos-parent:{parent_id}:{artifact.artifact_id}",
                        source=parent_id,
                        target=artifact.artifact_id,
                        relation="artifact_parent",
                        domain="dbos",
                        source_ref=artifact.artifact_id,
                    )
                )

        # DBOS persists mission ownership separately from graph parentage. Some
        # records (for example an execution or SOP) belong to a mission without
        # making the mission an immediate artifact parent. Project that durable
        # relationship so the read model can trace one business lifecycle
        # without deriving links from labels or generated content.
        mission_ids = {
            artifact.artifact_id
            for artifact in artifacts
            if isinstance(artifact, MissionArtifact)
        }
        for artifact in artifacts:
            artifact_mission_id = str(getattr(artifact, "mission_id", "") or "")
            if artifact_mission_id and artifact_mission_id in mission_ids and artifact_mission_id != artifact.artifact_id:
                edges.append(
                    self._edge(
                        edge_id=f"mission-membership:{artifact_mission_id}:{artifact.artifact_id}",
                        source=artifact_mission_id,
                        target=artifact.artifact_id,
                        relation="mission_membership",
                        domain="dbos",
                        source_ref=artifact.artifact_id,
                    )
                )

        runtime_contexts = [artifact for artifact in artifacts if isinstance(artifact, RuntimeContextArtifact)]
        growth_edges = self.repository.list_lineage(project_id, limit=500)
        growth_edges = self._related_growth_edges(growth_edges, runtime_contexts, mission_id)
        endpoint_ids = {
            str(edge.get(endpoint) or "")
            for edge in growth_edges
            for endpoint in ("from_id", "to_id")
            if str(edge.get(endpoint) or "")
        }
        for context in runtime_contexts:
            endpoint_ids.update(str(value) for value in context.source_ids if str(value))
            endpoint_ids.update(str(value) for value in context.method_ids if str(value))
        endpoints = self.repository.lineage_endpoints(project_id, endpoint_ids)
        for endpoint in endpoints.values():
            nodes.setdefault(str(endpoint["id"]), self._growth_node(endpoint))

        for edge in growth_edges:
            source = str(edge.get("from_id") or "")
            target = str(edge.get("to_id") or "")
            if not source or not target or source not in nodes or target not in nodes:
                missing_endpoints += 1
                continue
            edges.append(
                self._edge(
                    edge_id=f"growth:{edge.get('id')}",
                    source=source,
                    target=target,
                    relation=str(edge.get("edge_type") or "recorded_relation"),
                    domain="growth",
                    source_ref=str(edge.get("id") or ""),
                )
            )
        for context in runtime_contexts:
            for endpoint_id in context.source_ids:
                if endpoint_id not in nodes:
                    missing_endpoints += 1
                    continue
                edges.append(
                    self._edge(
                        edge_id=f"runtime-source:{context.artifact_id}:{endpoint_id}",
                        source=endpoint_id,
                        target=context.artifact_id,
                        relation="runtime_uses_source",
                        domain="cross_domain",
                        source_ref=context.artifact_id,
                    )
                )
            for endpoint_id in context.method_ids:
                if endpoint_id not in nodes:
                    missing_endpoints += 1
                    continue
                edges.append(
                    self._edge(
                        edge_id=f"runtime-method:{context.artifact_id}:{endpoint_id}",
                        source=endpoint_id,
                        target=context.artifact_id,
                        relation="runtime_uses_method",
                        domain="cross_domain",
                        source_ref=context.artifact_id,
                    )
                )
        return nodes, edges, missing_endpoints

    @staticmethod
    def _related_growth_edges(
        edges: list[dict[str, Any]], contexts: list[RuntimeContextArtifact], mission_id: str
    ) -> list[dict[str, Any]]:
        if not mission_id:
            return edges
        seeds = {
            str(value)
            for context in contexts
            for value in (*context.source_ids, *context.method_ids)
            if str(value)
        }
        if not seeds:
            return []
        related = list(edges)
        changed = True
        while changed:
            changed = False
            for edge in edges:
                source = str(edge.get("from_id") or "")
                target = str(edge.get("to_id") or "")
                if source in seeds or target in seeds:
                    if source not in seeds or target not in seeds:
                        changed = True
                    seeds.update((source, target))
        return [
            edge
            for edge in related
            if str(edge.get("from_id") or "") in seeds or str(edge.get("to_id") or "") in seeds
        ]

    @staticmethod
    def _mission_slice(artifacts: list[BaseArtifact], mission_id: str) -> list[BaseArtifact]:
        roots = {
            artifact.artifact_id
            for artifact in artifacts
            if artifact.artifact_id == mission_id or getattr(artifact, "mission_id", "") == mission_id
        }
        if not roots:
            return []
        adjacent: dict[str, set[str]] = defaultdict(set)
        for artifact in artifacts:
            for parent_id in artifact.parent_ids:
                adjacent[artifact.artifact_id].add(parent_id)
                adjacent[parent_id].add(artifact.artifact_id)
        selected: set[str] = set()
        queue = deque(sorted(roots))
        while queue:
            current = queue.popleft()
            if current in selected:
                continue
            selected.add(current)
            queue.extend(sorted(adjacent.get(current, set()) - selected))
        # Some DBOS records are deliberately related by the persisted mission
        # field rather than a direct Artifact Graph parent edge. Include those
        # members before traversing their authored parent links. This remains a
        # project-local, durable relation and never falls back to labels.
        mission_members = {
            artifact.artifact_id
            for artifact in artifacts
            if str(getattr(artifact, "mission_id", "") or "") == mission_id
        }
        if mission_members - selected:
            queue.extend(sorted(mission_members - selected))
            while queue:
                current = queue.popleft()
                if current in selected:
                    continue
                selected.add(current)
                queue.extend(sorted(adjacent.get(current, set()) - selected))
        return [artifact for artifact in artifacts if artifact.artifact_id in selected]

    @staticmethod
    def _artifact_node(artifact: BaseArtifact) -> dict[str, Any]:
        artifact_type = artifact.artifact_type.value
        return {
            "id": artifact.artifact_id,
            "domain": "dbos",
            "type": artifact_type,
            "lane": KnowledgeOperationsGraphService._artifact_lane(artifact),
            "label": KnowledgeOperationsGraphService._artifact_label(artifact),
            "status": KnowledgeOperationsGraphService._artifact_status(artifact),
            "created_at": str(artifact.created_at),
            "confidence": artifact.confidence,
            "drilldown": {"surface": "dbos", "entity_id": artifact.artifact_id, "mission_id": str(getattr(artifact, "mission_id", ""))},
        }

    @staticmethod
    def _growth_node(endpoint: dict[str, str]) -> dict[str, Any]:
        endpoint_type = str(endpoint.get("type") or "recorded")
        return {
            "id": str(endpoint["id"]),
            "domain": "growth",
            "type": endpoint_type,
            "lane": KnowledgeOperationsGraphService._growth_lane(endpoint_type),
            "label": str(endpoint.get("label") or endpoint_type.replace("_", " ").title()),
            "status": str(endpoint.get("status") or "recorded"),
            "created_at": str(endpoint.get("created_at") or ""),
            "confidence": None,
            "drilldown": {"surface": "growth", "entity_id": str(endpoint["id"]), "mission_id": ""},
        }

    @staticmethod
    def _edge(*, edge_id: str, source: str, target: str, relation: str, domain: str, source_ref: str) -> dict[str, str]:
        return {"id": edge_id, "source": source, "target": target, "relation": relation, "domain": domain, "source_ref": source_ref}

    @staticmethod
    def _lifecycle_audit(
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        *,
        scope: str,
    ) -> dict[str, Any]:
        """Report durable lifecycle reachability without manufacturing health."""
        required_lanes = {"mission", "evidence_source", "method_sop", "validation", "memory_feedback"}
        node_by_id = {str(node["id"]): node for node in nodes}
        risk_ids = sorted(
            node_id for node_id, node in node_by_id.items() if str(node.get("lane") or "") == "risk_constraint"
        )
        if not risk_ids:
            return {
                "scope": scope,
                "risk_node_count": 0,
                "complete_risk_lineage_count": 0,
                "missing_lanes": [],
                "reason": "No persisted risk or constraint nodes are present in this graph.",
            }

        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source in node_by_id and target in node_by_id:
                adjacency[source].add(target)
                adjacency[target].add(source)

        complete_count = 0
        missing_lanes: set[str] = set()
        for risk_id in risk_ids:
            seen = {risk_id}
            queue = deque([risk_id])
            while queue:
                current = queue.popleft()
                for neighbor in sorted(adjacency.get(current, set())):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        queue.append(neighbor)
            reached_lanes = {str(node_by_id[node_id].get("lane") or "") for node_id in seen}
            missing = required_lanes - reached_lanes
            if missing:
                missing_lanes.update(missing)
            else:
                complete_count += 1

        ordered_missing = [lane for lane, _label, _order in _LANES if lane in missing_lanes]
        if complete_count:
            reason = f"{complete_count} persisted risk node(s) reach every required lifecycle lane."
        elif scope == "visible_page":
            reason = "No visible risk node reaches every required lifecycle lane; additional graph pages may contain related records."
        else:
            reason = "No persisted risk node reaches every required lifecycle lane in this graph."
        return {
            "scope": scope,
            "risk_node_count": len(risk_ids),
            "complete_risk_lineage_count": complete_count,
            "missing_lanes": ordered_missing,
            "reason": reason,
        }

    @staticmethod
    def _artifact_lane(artifact: BaseArtifact) -> str:
        if isinstance(artifact, MissionArtifact):
            return "mission"
        if isinstance(artifact, AssumptionArtifact):
            return "assumption"
        if isinstance(artifact, (RiskArtifact, ConstraintArtifact, GapArtifact)):
            return "risk_constraint"
        if isinstance(artifact, EvidenceArtifact):
            return "evidence_source"
        if isinstance(artifact, (TaskVerificationArtifact, ExecutionResultArtifact)):
            return "validation"
        if isinstance(artifact, MemoryArtifact):
            return "memory_feedback"
        if isinstance(artifact, (DiagnosisArtifact, CapabilitySelectionArtifact, DynamicSOPArtifact, RuntimeContextArtifact)):
            return "method_sop"
        return "method_sop"

    @staticmethod
    def _growth_lane(endpoint_type: str) -> str:
        if endpoint_type in {"source", "page", "candidate"}:
            return "evidence_source"
        if endpoint_type in {"output", "run"}:
            return "validation"
        if endpoint_type == "feedback":
            return "memory_feedback"
        return "method_sop"

    @staticmethod
    def _artifact_label(artifact: BaseArtifact) -> str:
        if isinstance(artifact, MissionArtifact):
            return artifact.title or artifact.label or "Mission"
        if isinstance(artifact, DynamicSOPArtifact):
            return artifact.title or artifact.label or "Dynamic SOP"
        labels = {
            AssumptionArtifact: "Assumption",
            RiskArtifact: "Risk",
            ConstraintArtifact: "Constraint",
            GapArtifact: "Evidence gap",
            EvidenceArtifact: "Evidence",
            TaskVerificationArtifact: "Task verification",
            ExecutionResultArtifact: "Execution result",
            MemoryArtifact: "Memory",
            RuntimeContextArtifact: "Runtime context",
            DiagnosisArtifact: "Diagnosis",
            CapabilitySelectionArtifact: "Capability selection",
        }
        for artifact_class, label in labels.items():
            if isinstance(artifact, artifact_class):
                return label
        return artifact.artifact_type.value.replace("_", " ").title()

    @staticmethod
    def _artifact_status(artifact: BaseArtifact) -> str:
        if isinstance(artifact, MissionArtifact):
            return artifact.mission_status
        if isinstance(artifact, ExecutionResultArtifact):
            return artifact.execution_status
        if isinstance(artifact, TaskVerificationArtifact):
            return artifact.verification_status
        return artifact.status.value

    @staticmethod
    def _matches_node(
        node: dict[str, Any], node_types: set[str], statuses: set[str], interval: OperationsInterval | None
    ) -> bool:
        if node_types and node["type"] not in node_types:
            return False
        if statuses and node["status"] not in statuses:
            return False
        if interval:
            at = _at(node["created_at"])
            if at == datetime(1970, 1, 1, tzinfo=timezone.utc) or not (interval.start_at <= at < interval.end_at):
                return False
        return True

    @staticmethod
    def _node_sort_key(node: dict[str, Any]) -> tuple[int, str, str]:
        return (_LANE_ORDER.get(str(node["lane"]), 99), str(node["created_at"]), str(node["id"]))
