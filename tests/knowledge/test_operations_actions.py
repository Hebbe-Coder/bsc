from app.artifacts import (
    ArtifactGraphStore,
    AssumptionArtifact,
    ExecutionResultArtifact,
    GapArtifact,
    GapCategory,
    RiskArtifact,
    Severity,
    TaskVerificationArtifact,
)
from app.knowledge.growth_contracts import MethodProposal
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsScope
from app.knowledge.operations_service import KnowledgeOperationsService
from app.repositories.knowledge_repository import KnowledgeRepository


def _project_repository(repository: GrowthRepository) -> KnowledgeRepository:
    project_repository = KnowledgeRepository(backend=repository._get_connection())
    project_repository._owns_connection = False
    return project_repository


def test_actions_are_deterministic_scoped_and_point_to_durable_evidence(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "actions.db"))
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
        repository.save_method_proposal(
            MethodProposal(
                id="proposal-a",
                project_id="project-a",
                operation="create",
                body="A proposal requires human review before it becomes a method.",
            )
        )
        store.add(
            RiskArtifact(
                project_id="project-a",
                artifact_id="risk-a",
                risk_statement="Critical unresolved risk",
                severity=Severity.CRITICAL,
                created_at="2026-07-23T00:00:00+00:00",
            )
        )
        store.add(
            GapArtifact(
                project_id="project-a",
                artifact_id="gap-a",
                gap_statement="Evidence is missing",
                category=GapCategory.EVIDENCE_MISSING,
                severity=Severity.HIGH,
                created_at="2026-07-23T01:00:00+00:00",
            )
        )
        store.add(
            TaskVerificationArtifact(
                project_id="project-a",
                artifact_id="verification-failed",
                mission_id="mission-a",
                execution_id="execution-verified",
                verification_status="failed",
                created_at="2026-07-23T02:00:00+00:00",
            )
        )
        store.add(
            ExecutionResultArtifact(
                project_id="project-a",
                artifact_id="execution-unverified",
                execution_id="execution-unverified",
                mission_id="mission-a",
                execution_status="completed",
                created_at="2026-07-23T03:00:00+00:00",
            )
        )
        store.add(
            AssumptionArtifact(
                project_id="project-a",
                artifact_id="assumption-a",
                statement="Critical assumption",
                criticality=Severity.CRITICAL,
                validated=False,
                created_at="2026-07-23T04:00:00+00:00",
            )
        )

        service = KnowledgeOperationsService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: store,
        )
        scope = OperationsScope(tenant_id="tenant-a", role="tenant_admin")
        first = service.overview(scope)["actions"]
        second = service.overview(scope)["actions"]

        assert first == second
        assert [action["kind"] for action in first[:6]] == [
            "unresolved_risk",
            "evidence_gap",
            "failed_verification",
            "unverified_execution",
            "unvalidated_assumption",
            "pending_proposal",
        ]
        assert all(action["project_id"] == "project-a" for action in first)
        assert all(action["source_refs"] for action in first)
        assert first[0]["drilldown"] == {
            "surface": "dbos",
            "entity_id": "risk-a",
            "mission_id": "",
        }
    finally:
        repository.close()
