from datetime import datetime, timezone

import pytest

from app.artifacts import (
    ArtifactGraphStore,
    AssumptionArtifact,
    DynamicSOPArtifact,
    MemoryArtifact,
    MissionArtifact,
    RiskArtifact,
    RuntimeContextArtifact,
    Severity,
    TaskVerificationArtifact,
)
from app.knowledge.growth_contracts import KnowledgeLineageEdge, MethodAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsScope
from app.knowledge.operations_graph import KnowledgeOperationsGraphService
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.repositories.knowledge_repository import KnowledgeRepository


def _project_repository(repository: GrowthRepository) -> KnowledgeRepository:
    project_repository = KnowledgeRepository(backend=repository._get_connection())
    project_repository._owns_connection = False
    return project_repository


def test_lifecycle_graph_projects_only_persisted_scoped_edges_and_redacts_bodies(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "graph.db"))
    project_repository = _project_repository(repository)
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        repository.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="sensitive raw source body must never appear in the lifecycle graph",
                status=SourceStatus.ELIGIBLE,
                captured_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            )
        )
        repository.create_method(
            MethodAsset(
                id="method-a",
                project_id="project-a",
                slug="research-method",
                name="Research method",
            )
        )
        repository.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id="project-a",
                from_type="source",
                from_id="source-a",
                to_type="method",
                to_id="method-a",
                relation="source_distills_method_proposal",
            )
        )

        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="Launch"))
        store.add(
            AssumptionArtifact(
                project_id="project-a",
                artifact_id="assumption-a",
                parent_ids=["mission-a"],
                statement="An assumption is safe to label but not expose source bodies.",
                criticality=Severity.HIGH,
            )
        )
        store.add(
            RiskArtifact(
                project_id="project-a",
                artifact_id="risk-a",
                parent_ids=["assumption-a"],
                risk_statement="Risk",
                severity=Severity.HIGH,
            )
        )
        store.add(DynamicSOPArtifact(project_id="project-a", artifact_id="sop-a", mission_id="mission-a", parent_ids=["mission-a"], title="Launch SOP"))
        store.add(
            RuntimeContextArtifact(
                project_id="project-a",
                artifact_id="context-a",
                mission_id="mission-a",
                parent_ids=["sop-a"],
                source_ids=["source-a"],
                method_ids=["method-a"],
                context_fields=["project_profile"],
            )
        )
        store.add(
            TaskVerificationArtifact(
                project_id="project-a",
                artifact_id="verification-a",
                mission_id="mission-a",
                parent_ids=["context-a"],
                verification_status="passed",
            )
        )
        store.add(
            MemoryArtifact(
                project_id="project-a",
                artifact_id="memory-a",
                parent_ids=["verification-a"],
                statement="A memory is not exported through this graph label.",
            )
        )

        graph = KnowledgeOperationsGraphService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: store,
        ).project_graph(
            OperationsScope(tenant_id="tenant-a", role="tenant_admin", project_ids=["project-a"]),
            project_id="project-a",
            mission_id="mission-a",
        )

        nodes = {node["id"]: node for node in graph["nodes"]}
        assert nodes["mission-a"]["lane"] == "mission"
        assert nodes["assumption-a"]["lane"] == "assumption"
        assert nodes["risk-a"]["lane"] == "risk_constraint"
        assert nodes["sop-a"]["lane"] == "method_sop"
        assert nodes["verification-a"]["lane"] == "validation"
        assert nodes["memory-a"]["lane"] == "memory_feedback"
        assert nodes["source-a"]["lane"] == "evidence_source"
        assert nodes["method-a"]["lane"] == "method_sop"
        assert any(edge["domain"] == "growth" and edge["source_ref"] for edge in graph["edges"])
        assert any(edge["relation"] == "runtime_uses_source" for edge in graph["edges"])
        assert any(edge["relation"] == "runtime_uses_method" for edge in graph["edges"])
        assert {
            (edge["source"], edge["target"])
            for edge in graph["edges"]
            if edge["relation"] == "mission_membership"
        } == {
            ("mission-a", "sop-a"),
            ("mission-a", "context-a"),
            ("mission-a", "verification-a"),
        }
        assert graph["lifecycle_audit"] == {
            "scope": "filtered_graph",
            "risk_node_count": 1,
            "complete_risk_lineage_count": 1,
            "missing_lanes": [],
            "reason": "1 persisted risk node(s) reach every required lifecycle lane.",
        }
        assert "sensitive raw source body" not in str(graph)
        assert "project_profile" not in str(graph)
    finally:
        repository.close()


def test_lifecycle_graph_joins_only_durable_members_of_the_same_mission(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "mission-membership.db"))
    project_repository = _project_repository(repository)
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="A"))
        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-b", mission_id="mission-b", title="B"))
        store.add(DynamicSOPArtifact(project_id="project-a", artifact_id="sop-a", mission_id="mission-a", title="A SOP"))
        store.add(DynamicSOPArtifact(project_id="project-a", artifact_id="sop-b", mission_id="mission-b", title="B SOP"))

        graph = KnowledgeOperationsGraphService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: store,
        ).project_graph(
            OperationsScope(tenant_id="tenant-a", role="tenant_admin", project_ids=["project-a"]),
            project_id="project-a",
        )

        membership = {
            (edge["source"], edge["target"])
            for edge in graph["edges"]
            if edge["relation"] == "mission_membership"
        }
        assert membership == {("mission-a", "sop-a"), ("mission-b", "sop-b")}
        assert ("mission-a", "sop-b") not in membership
        assert ("mission-b", "sop-a") not in membership
    finally:
        repository.close()


def test_mission_graph_slice_includes_only_durable_mission_members_without_parent_edges(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "mission-slice.db"))
    project_repository = _project_repository(repository)
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="A"))
        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-b", mission_id="mission-b", title="B"))
        store.add(DynamicSOPArtifact(project_id="project-a", artifact_id="sop-a", mission_id="mission-a", title="A SOP"))
        store.add(DynamicSOPArtifact(project_id="project-a", artifact_id="sop-b", mission_id="mission-b", title="B SOP"))

        graph = KnowledgeOperationsGraphService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: store,
        ).project_graph(
            OperationsScope(tenant_id="tenant-a", role="tenant_admin", project_ids=["project-a"]),
            project_id="project-a",
            mission_id="mission-a",
        )

        assert {node["id"] for node in graph["nodes"]} == {"mission-a", "sop-a"}
        assert [
            (edge["source"], edge["target"])
            for edge in graph["edges"]
            if edge["relation"] == "mission_membership"
        ] == [("mission-a", "sop-a")]
        assert graph["lifecycle_audit"] == {
            "scope": "filtered_graph",
            "risk_node_count": 0,
            "complete_risk_lineage_count": 0,
            "missing_lanes": [],
            "reason": "No persisted risk or constraint nodes are present in this graph.",
        }
    finally:
        repository.close()


def test_lifecycle_graph_enforces_tenant_scope_and_declares_bounded_pages(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "graph-bounds.db"))
    project_repository = _project_repository(repository)
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        project_repository.create_project("project-b", "Project B", tenant_id="tenant-b")
        store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="A"))
        for index in range(4):
            store.add(
                AssumptionArtifact(
                    project_id="project-a",
                    artifact_id=f"assumption-{index}",
                    parent_ids=["mission-a"],
                    statement=f"Assumption {index}",
                    created_at=f"2026-07-2{index}T00:00:00+00:00",
                )
            )
        service = KnowledgeOperationsGraphService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: store,
        )
        scope = OperationsScope(tenant_id="tenant-a", role="tenant_admin", project_ids=["project-a"])

        first = service.project_graph(scope, project_id="project-a", limit=2)
        second = service.project_graph(scope, project_id="project-a", limit=2, cursor=first["pagination"]["next_cursor"])

        assert first["pagination"]["truncated"] is True
        assert first["pagination"]["omitted_node_count"] == 3
        assert first["lifecycle_audit"]["scope"] == "visible_page"
        assert len(first["nodes"]) == len(second["nodes"]) == 2
        assert {node["id"] for node in first["nodes"]}.isdisjoint({node["id"] for node in second["nodes"]})
        with pytest.raises(PermissionError):
            service.project_graph(scope, project_id="project-b")
    finally:
        repository.close()
