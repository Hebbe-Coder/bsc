from datetime import datetime, timezone

from app.artifacts import (
    ArtifactGraphStore,
    ExecutionResultArtifact,
    MemoryArtifact,
    RuntimeContextArtifact,
    SOPRoutingEvaluationArtifact,
    TaskVerificationArtifact,
)
from app.knowledge.growth_contracts import (
    MethodAsset,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputStatus,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsMetricState, OperationsScope
from app.knowledge.operations_service import MINIMUM_AGENT_SAMPLE_SIZE, KnowledgeOperationsService
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.repositories.knowledge_repository import KnowledgeRepository


def _project_repository(repository: GrowthRepository) -> KnowledgeRepository:
    project_repository = KnowledgeRepository(backend=repository._get_connection())
    project_repository._owns_connection = False
    return project_repository


def test_operations_overview_uses_real_scoped_growth_and_dbos_records(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "operations.db"))
    project_repository = _project_repository(repository)
    artifact_root = tmp_path / "artifacts"
    stores: dict[tuple[str, str], ArtifactGraphStore] = {}

    def store_for(project_id: str, tenant_id: str) -> ArtifactGraphStore:
        return stores[(tenant_id, project_id)]

    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        project_repository.create_project("project-b", "Project B", tenant_id="tenant-b")

        captured_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
        repository.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="immutable source material must not leak into operations output",
                status=SourceStatus.ELIGIBLE,
                captured_at=captured_at,
                updated_at=captured_at,
            )
        )
        method = repository.create_method(
            MethodAsset(
                id="method-a",
                project_id="project-a",
                slug="evidence-review",
                name="Evidence review",
                status=MethodStatus.PUBLISHED,
                active_revision_id="revision-a",
                created_at=captured_at,
                updated_at=captured_at,
            )
        )
        repository.save_method_revision(
            MethodRevision(
                id="revision-a",
                method_id=method["id"],
                project_id="project-a",
                version=1,
                body="A governed method body lives outside the operations projection.",
                status=MethodStatus.PUBLISHED,
                created_at=captured_at,
            )
        )
        repository.register_output(
            OutputAsset(
                id="output-a",
                project_id="project-a",
                kind="report",
                title="Verified report",
                content_hash="b" * 64,
                vault_path="outputs/2026/verified-report.md",
                idempotency_key="output-a",
                method_revision_id="revision-a",
                source_refs=["source-a"],
                status=OutputStatus.ACCEPTED,
                created_at=captured_at,
                updated_at=captured_at,
            )
        )

        stores[("tenant-a", "project-a")] = ArtifactGraphStore(
            str(artifact_root / "tenant-a" / "project-a"),
            tenant_id="tenant-a",
            project_id="project-a",
            session_id="dbos",
        )
        store = stores[("tenant-a", "project-a")]
        store.add(MemoryArtifact(project_id="project-a", artifact_id="memory-a", governance_status="accepted"))
        store.add(
            ExecutionResultArtifact(
                project_id="project-a",
                artifact_id="execution-a",
                execution_id="execution-a",
                mission_id="mission-a",
                execution_status="completed",
                attempt=2,
                created_at="2026-07-21T00:00:00+00:00",
            )
        )
        store.add(
            TaskVerificationArtifact(
                project_id="project-a",
                artifact_id="verification-a",
                mission_id="mission-a",
                execution_id="execution-a",
                verification_status="passed",
                created_at="2026-07-21T01:00:00+00:00",
            )
        )
        store.add(
            RuntimeContextArtifact(
                project_id="project-a",
                artifact_id="context-a",
                mission_id="mission-a",
                method_ids=["method-a"],
            )
        )
        store.add(
            SOPRoutingEvaluationArtifact(
                project_id="project-a",
                artifact_id="routing-a",
                mission_id="mission-a",
                evaluation_status="completed",
                holdout_case_count=4,
                holdout_passed=True,
                created_at="2026-07-21T01:00:00+00:00",
            )
        )
        store.add(
            ExecutionResultArtifact(
                project_id="project-a",
                artifact_id="execution-b",
                execution_id="execution-b",
                mission_id="mission-a",
                execution_status="completed",
                attempt=3,
                created_at="2026-07-21T02:00:00+00:00",
            )
        )
        store.add(
            TaskVerificationArtifact(
                project_id="project-a",
                artifact_id="verification-b",
                mission_id="mission-a",
                execution_id="execution-b",
                verification_status="failed",
                created_at="2026-07-21T03:00:00+00:00",
            )
        )
        store.add(
            SOPRoutingEvaluationArtifact(
                project_id="project-a",
                artifact_id="routing-b",
                mission_id="mission-a",
                evaluation_status="completed",
                holdout_case_count=4,
                holdout_passed=False,
                created_at="2026-07-21T03:00:00+00:00",
            )
        )
        store.add(
            ExecutionResultArtifact(
                project_id="project-a",
                artifact_id="execution-c",
                execution_id="execution-c",
                mission_id="mission-a",
                execution_status="completed",
                attempt=1,
                created_at="2026-07-21T04:00:00+00:00",
            )
        )
        store.add(
            TaskVerificationArtifact(
                project_id="project-a",
                artifact_id="verification-c",
                mission_id="mission-a",
                execution_id="execution-c",
                verification_status="passed",
                created_at="2026-07-21T05:00:00+00:00",
            )
        )
        store.add(
            SOPRoutingEvaluationArtifact(
                project_id="project-a",
                artifact_id="routing-c",
                mission_id="mission-a",
                evaluation_status="completed",
                holdout_case_count=4,
                holdout_passed=True,
                created_at="2026-07-21T05:00:00+00:00",
            )
        )

        service = KnowledgeOperationsService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=store_for,
        )
        scope = OperationsScope(
            tenant_id="tenant-a",
            role="tenant_admin",
            project_ids=["project-a", "project-b"],
        )
        overview = service.overview(scope)
        contributors = service.metric_contributors(scope, "qualified_total", limit=3)

        assert overview["scope"]["project_ids"] == ["project-a"]
        assert overview["project_count"] == 1
        assert overview["metrics"]["assets"]["sources"]["value"] == 1
        assert overview["metrics"]["assets"]["methods"]["value"] == 1
        assert overview["metrics"]["assets"]["outputs"]["value"] == 1
        assert overview["metrics"]["assets"]["memories"]["value"] == 1
        assert overview["metrics"]["quality"]["verified"]["value"] == 4
        assert overview["metrics"]["reuse"]["durable_references"]["value"] == 2
        assert overview["metrics"]["agent_evolution"]["verification_pass_rate"]["value"] == 66.67
        assert overview["metrics"]["agent_evolution"]["median_execution_attempt"]["value"] == 2.0
        assert overview["metrics"]["agent_evolution"]["routing_holdout_pass_rate"]["value"] == 66.67
        assert contributors["metric"] == overview["metrics"]["assets"]["qualified_total"]
        assert contributors["total"] == 4
        assert len(contributors["contributors"]) == 3
        assert contributors["truncated"] is True
        assert {item["kind"] for item in contributors["contributors"]} <= {"source", "wiki_page", "method", "output", "memory"}
        assert "immutable source material" not in str(contributors)
        assert len(overview["project_summaries"]) == 1
        project_summary = overview["project_summaries"][0]
        assert project_summary["project_id"] == "project-a"
        assert project_summary["project_name"] == "Project A"
        assert project_summary["metrics"]["asset_count"]["value"] == 4
        assert project_summary["metrics"]["verified"]["value"] == 4
        assert project_summary["metrics"]["durable_references"]["value"] == 2
        assert project_summary["freshness"]["state"] == OperationsMetricState.AVAILABLE.value
        assert overview["trends"]["asset_growth"] == [
            {"date": "2026-07-20", "sources": 1, "methods": 1, "outputs": 1}
        ]
        assert overview["trends"]["agent_evolution"] == [
            {
                "date": "2026-07-21",
                "verification_pass_rate": 66.67,
                "verification_sample_count": 3,
                "median_execution_attempt": 2.0,
                "execution_sample_count": 3,
                "routing_holdout_pass_rate": 66.67,
                "routing_sample_count": 3,
            }
        ]
        assert "immutable source material" not in str(overview)
    finally:
        repository.close()


def test_operations_keeps_unqualified_assets_in_audit_and_action_queues(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "asset-states.db"))
    project_repository = _project_repository(repository)
    captured_at = datetime(2026, 7, 27, tzinfo=timezone.utc)
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        for source_id, status, content_hash in (
            ("source-eligible", SourceStatus.ELIGIBLE, "a" * 64),
            ("source-validated", SourceStatus.VALIDATED, "b" * 64),
            ("source-rejected", SourceStatus.REJECTED, "c" * 64),
        ):
            repository.create_source(SourceRecord(
                id=source_id,
                project_id="project-a",
                source_type="article",
                content_hash=content_hash,
                raw_content=f"{source_id} audit body",
                status=status,
                captured_at=captured_at,
                updated_at=captured_at,
            ))
        for method_id, status in (
            ("method-published", MethodStatus.PUBLISHED),
            ("method-candidate", MethodStatus.CANDIDATE),
            ("method-rejected", MethodStatus.REJECTED),
        ):
            repository.create_method(MethodAsset(
                id=method_id,
                project_id="project-a",
                slug=method_id,
                name=method_id,
                status=status,
                created_at=captured_at,
                updated_at=captured_at,
            ))
        for output_id, status, content_hash in (
            ("output-accepted", OutputStatus.ACCEPTED, "d" * 64),
            ("output-registered", OutputStatus.REGISTERED, "e" * 64),
            ("output-rejected", OutputStatus.REJECTED, "f" * 64),
        ):
            repository.register_output(OutputAsset(
                id=output_id,
                project_id="project-a",
                kind="report",
                title=output_id,
                content_hash=content_hash,
                vault_path=f"04_Outputs/{output_id}.md",
                idempotency_key=output_id,
                status=status,
                created_at=captured_at,
                updated_at=captured_at,
            ))

        service = KnowledgeOperationsService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: ArtifactGraphStore(
                str(tmp_path / tenant_id / project_id),
                tenant_id=tenant_id,
                project_id=project_id,
                session_id="dbos",
            ),
        )
        scope = OperationsScope(tenant_id="tenant-a", role="tenant_admin")
        overview = service.overview(scope)
        pending = service.metric_contributors(scope, "pending_validation")
        attention = service.metric_contributors(scope, "requires_attention")

        assert overview["metrics"]["assets"]["qualified_total"]["value"] == 3
        assert overview["metrics"]["assets"]["sources"]["value"] == 1
        assert overview["metrics"]["assets"]["methods"]["value"] == 1
        assert overview["metrics"]["assets"]["outputs"]["value"] == 1
        assert overview["metrics"]["quality"]["verified"]["value"] == 3
        assert overview["metrics"]["quality"]["pending_validation"]["value"] == 3
        assert overview["metrics"]["quality"]["requires_attention"]["value"] == 3
        assert pending["metric"] == overview["metrics"]["quality"]["pending_validation"]
        assert {item["id"] for item in pending["contributors"]} == {"source-validated", "method-candidate", "output-registered"}
        assert attention["metric"] == overview["metrics"]["quality"]["requires_attention"]
        assert {item["id"] for item in attention["contributors"]} == {"source-rejected", "method-rejected", "output-rejected"}
        assert "audit body" not in str(pending)
        assert "audit body" not in str(attention)
        assert overview["coverage"]["record_count"] == 9
        assert overview["project_summaries"][0]["metrics"]["asset_count"]["value"] == 3
        assert {action["kind"] for action in overview["actions"]} == {
            "pending_output_evaluation",
            "rejected_output",
        }
    finally:
        repository.close()


def test_operations_marks_agent_metrics_as_insufficient_without_real_samples(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "empty.db"))
    project_repository = _project_repository(repository)
    try:
        project_repository.create_project("project-a", "Project A", tenant_id="tenant-a")
        service = KnowledgeOperationsService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: ArtifactGraphStore(
                str(tmp_path / tenant_id / project_id),
                tenant_id=tenant_id,
                project_id=project_id,
                session_id="dbos",
            ),
        )

        overview = service.overview(
            OperationsScope(tenant_id="tenant-a", role="tenant_admin")
        )

        metric = overview["metrics"]["agent_evolution"]["verification_pass_rate"]
        assert metric["state"] == OperationsMetricState.INSUFFICIENT_SAMPLE.value
        assert metric["value"] is None
        assert "no passed or failed task verifications" in metric["reason"]
    finally:
        repository.close()


def test_agent_metrics_require_three_persisted_observations_before_a_rate_is_available():
    """A single successful run is evidence, not an agent-quality conclusion."""
    insufficient = KnowledgeOperationsService._sample_metric(
        "verification_pass_rate",
        100.0,
        MINIMUM_AGENT_SAMPLE_SIZE - 1,
        "percent",
        "no passed or failed task verifications",
    )
    sufficient = KnowledgeOperationsService._sample_metric(
        "verification_pass_rate",
        66.67,
        MINIMUM_AGENT_SAMPLE_SIZE,
        "percent",
        "no passed or failed task verifications",
    )

    assert MINIMUM_AGENT_SAMPLE_SIZE == 3
    assert insufficient == {
        "key": "verification_pass_rate",
        "state": OperationsMetricState.INSUFFICIENT_SAMPLE.value,
        "value": None,
        "unit": "percent",
        "record_count": 2,
        "reason": "requires at least 3 persisted samples; 2 available",
    }
    assert sufficient["state"] == OperationsMetricState.AVAILABLE.value
    assert sufficient["value"] == 66.67
    assert sufficient["record_count"] == 3


def test_agent_evolution_trend_keeps_under_sampled_daily_rates_null():
    service = KnowledgeOperationsService(repository=None, project_repository=None)
    trend = service._agent_evolution_trend([{
        "verifications": [TaskVerificationArtifact(
            project_id="project-a", artifact_id="verification-a", verification_status="passed",
            created_at="2026-07-27T00:00:00+00:00",
        )],
        "executions": [ExecutionResultArtifact(
            project_id="project-a", artifact_id="execution-a", execution_id="execution-a", attempt=1,
            created_at="2026-07-27T00:00:00+00:00",
        )],
        "routing": [SOPRoutingEvaluationArtifact(
            project_id="project-a", artifact_id="routing-a", holdout_case_count=1, holdout_passed=True,
            created_at="2026-07-27T00:00:00+00:00",
        )],
    }])

    assert trend == [{
        "date": "2026-07-27",
        "verification_pass_rate": None,
        "verification_sample_count": 1,
        "median_execution_attempt": None,
        "execution_sample_count": 1,
        "routing_holdout_pass_rate": None,
        "routing_sample_count": 1,
    }]
