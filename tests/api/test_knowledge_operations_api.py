from fastapi.testclient import TestClient

from app.api.knowledge_operations_api import OperationsContext, get_operations_context
from app.artifacts import ArtifactGraphStore, MissionArtifact
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.main import app
from app.middleware import auth
from app.middleware.auth import AuthPrincipal
from app.repositories.knowledge_repository import KnowledgeRepository


def test_operations_rest_api_enforces_tenant_scope_and_returns_typed_read_models(tmp_path, monkeypatch):
    repository = GrowthRepository(db_path=str(tmp_path / "operations-api.db"))
    projects = KnowledgeRepository(backend=repository._get_connection())
    projects._owns_connection = False
    projects.create_project("project-a", "Project A", tenant_id="default")
    projects.create_project("project-c", "Project C", tenant_id="default")
    projects.create_project("project-b", "Project B", tenant_id="other-tenant")
    repository.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="article",
            content_hash="a" * 64,
            raw_content="private source body",
            status=SourceStatus.ELIGIBLE,
        )
    )
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"), tenant_id="default", project_id="project-a", session_id="dbos"
    )
    store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="Launch"))
    context = OperationsContext(repository, projects)
    context.service.dbos_store_factory = lambda project_id, tenant_id: store
    context.graph.dbos_store_factory = lambda project_id, tenant_id: store
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "operations-admin"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_operations_context] = lambda: context
    client = TestClient(app)
    headers = {"Authorization": "Bearer operations-admin"}
    try:
        portfolio = client.get("/knowledge/operations/portfolio", headers=headers)
        assert portfolio.status_code == 200
        data = portfolio.json()["data"]
        assert data["state"] == "available"
        assert data["scope"]["project_ids"] == ["project-a", "project-c"]
        assert data["metrics"]["assets"]["sources"]["value"] == 1
        assert [(item["project_id"], item["project_name"]) for item in data["project_summaries"]] == [
            ("project-a", "Project A"),
            ("project-c", "Project C"),
        ]
        assert "private source body" not in str(data)

        portfolio_contributors = client.get(
            "/knowledge/operations/portfolio/metrics/qualified_total",
            params={"limit": 1},
            headers=headers,
        )
        assert portfolio_contributors.status_code == 200
        contributor_data = portfolio_contributors.json()["data"]
        assert contributor_data["state"] == "available"
        assert contributor_data["metric"] == data["metrics"]["assets"]["qualified_total"]
        assert contributor_data["total"] == 1
        assert contributor_data["truncated"] is False
        contributor = contributor_data["contributors"][0]
        assert {key: contributor[key] for key in ("id", "project_id", "kind", "status", "reason", "drilldown")} == {
            "id": "source-a",
            "project_id": "project-a",
            "kind": "source",
            "status": "eligible",
            "reason": "",
            "drilldown": {"surface": "knowledge", "entity_id": "source-a", "mission_id": ""},
        }
        assert contributor["recorded_at"]
        assert "private source body" not in str(contributor_data)

        project = client.get("/knowledge/operations/projects/project-a", headers=headers)
        assert project.status_code == 200
        assert project.json()["data"]["scope"]["selected_project_id"] == "project-a"

        project_contributors = client.get(
            "/knowledge/operations/projects/project-a/metrics/qualified_total",
            headers=headers,
        )
        assert project_contributors.status_code == 200
        assert project_contributors.json()["data"]["scope"]["project_ids"] == ["project-a"]
        assert {item["project_id"] for item in project_contributors.json()["data"]["contributors"]} == {"project-a"}

        graph = client.get("/knowledge/operations/projects/project-a/graph", params={"mission_id": "mission-a", "limit": 10}, headers=headers)
        assert graph.status_code == 200
        assert graph.json()["data"]["state"] == "available"
        assert graph.json()["data"]["nodes"][0]["id"] == "mission-a"
        assert graph.json()["data"]["lifecycle_audit"] == {
            "scope": "filtered_graph",
            "risk_node_count": 0,
            "complete_risk_lineage_count": 0,
            "missing_lanes": [],
            "reason": "No persisted risk or constraint nodes are present in this graph.",
        }

        forbidden = client.get("/knowledge/operations/projects/project-b", headers=headers)
        assert forbidden.status_code == 403
        invalid_metric = client.get("/knowledge/operations/portfolio/metrics/not-a-metric", headers=headers)
        assert invalid_metric.status_code == 422
        assert invalid_metric.json()["message"]["code"] == "operations_invalid_metric"
        invalid_interval = client.get("/knowledge/operations/portfolio", params={"from": "2026-07-01T00:00:00+00:00"}, headers=headers)
        assert invalid_interval.status_code == 422
        assert invalid_interval.json()["message"]["code"] == "operations_invalid_interval"
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()


def test_operations_rest_project_key_cannot_enumerate_or_escape_its_project(tmp_path, monkeypatch):
    repository = GrowthRepository(db_path=str(tmp_path / "operations-project-key.db"))
    projects = KnowledgeRepository(backend=repository._get_connection())
    projects._owns_connection = False
    projects.create_project("project-a", "Project A", tenant_id="default")
    projects.create_project("project-c", "Project C", tenant_id="default")
    projects.create_project("project-b", "Project B", tenant_id="other-tenant")
    context = OperationsContext(repository, projects)
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"), tenant_id="default", project_id="project-a", session_id="dbos"
    )
    store.add(MissionArtifact(project_id="project-a", artifact_id="mission-a", mission_id="mission-a", title="Launch"))
    context.service.dbos_store_factory = lambda _project_id, _tenant_id: store
    context.graph.dbos_store_factory = lambda _project_id, _tenant_id: store
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.KNOWLEDGE_WIKI_ENABLED = True
    monkeypatch.setattr(
        auth,
        "_principal_from_bearer",
        lambda key: AuthPrincipal("project_reader", "default", "project-a", "project-key", "") if key == "project-key" else None,
    )
    app.dependency_overrides[get_operations_context] = lambda: context
    client = TestClient(app)
    headers = {"Authorization": "Bearer project-key"}
    try:
        portfolio = client.get("/knowledge/operations/portfolio", headers=headers)
        own_project = client.get("/knowledge/operations/projects/project-a", headers=headers)
        own_contributors = client.get("/knowledge/operations/projects/project-a/metrics/qualified_total", headers=headers)
        same_tenant_other = client.get("/knowledge/operations/projects/project-c", headers=headers)
        same_tenant_other_contributors = client.get("/knowledge/operations/projects/project-c/metrics/qualified_total", headers=headers)
        cross_tenant_other = client.get("/knowledge/operations/projects/project-b/graph", headers=headers)

        assert portfolio.status_code == 403
        assert "project-c" not in portfolio.text and "project-b" not in portfolio.text
        assert own_project.status_code == 200
        assert own_project.json()["data"]["scope"]["project_ids"] == ["project-a"]
        assert own_contributors.status_code == 200
        assert own_contributors.json()["data"]["scope"]["project_ids"] == ["project-a"]
        assert same_tenant_other.status_code == same_tenant_other_contributors.status_code == cross_tenant_other.status_code == 403
    finally:
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()
