"""Exercise the knowledge-operations HTTP read model with isolated durable data.

This release check never opens the configured Vault or production database. It
constructs a temporary A/B/C/D plus DBOS lifecycle, then verifies that the
deployed FastAPI route can expose a complete, redacted risk lineage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.knowledge_operations_api import OperationsContext, get_operations_context
from app.artifacts import (
    ArtifactGraphStore,
    AssumptionArtifact,
    DynamicSOPArtifact,
    ExecutionResultArtifact,
    MemoryArtifact,
    MissionArtifact,
    RiskArtifact,
    RuntimeContextArtifact,
    Severity,
    TaskVerificationArtifact,
)
from app.core.config import settings
from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeLineageEdge,
    MethodAsset,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputFeedback,
    OutputStatus,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.main import app
from app.repositories.knowledge_repository import KnowledgeRepository


PROJECT_ID = "operations-runtime-audit"
TENANT_ID = settings.DEFAULT_TENANT_ID
API_KEY = "operations-runtime-audit-key"
REQUIRED_LANES = {"mission", "evidence_source", "method_sop", "validation", "memory_feedback"}


def _timestamp() -> datetime:
    return datetime(2026, 7, 27, tzinfo=timezone.utc)


def main() -> None:
    with TemporaryDirectory(prefix="bsc-operations-runtime-") as directory:
        repository = GrowthRepository(db_path=f"{directory}/operations.db")
        projects = KnowledgeRepository(backend=repository._get_connection())
        projects._owns_connection = False
        store = ArtifactGraphStore(
            f"{directory}/artifacts",
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            session_id="dbos",
        )
        previous_overrides = dict(app.dependency_overrides)
        previous = {
            "API_KEY": settings.API_KEY,
            "RATE_LIMIT_ENABLED": settings.RATE_LIMIT_ENABLED,
            "KNOWLEDGE_WIKI_ENABLED": settings.KNOWLEDGE_WIKI_ENABLED,
        }
        try:
            projects.create_project(PROJECT_ID, "Operations runtime audit", tenant_id=TENANT_ID)
            _seed_growth(repository)
            _seed_artifacts(store)
            context = OperationsContext(repository, projects)
            context.service.dbos_store_factory = lambda project_id, tenant_id: store
            context.graph.dbos_store_factory = lambda project_id, tenant_id: store
            settings.API_KEY = API_KEY
            settings.RATE_LIMIT_ENABLED = False
            settings.KNOWLEDGE_WIKI_ENABLED = True
            app.dependency_overrides[get_operations_context] = lambda: context

            response = TestClient(app).get(
                f"/knowledge/operations/projects/{PROJECT_ID}/graph?limit=200",
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"operations runtime route returned {response.status_code}")
            payload = response.json()["data"]
            audit = payload["lifecycle_audit"]
            lanes = {node["lane"] for node in payload["nodes"]}
            if audit["complete_risk_lineage_count"] != 1 or not REQUIRED_LANES <= lanes:
                raise RuntimeError(f"complete lifecycle was not projected: {audit}")
            if "runtime audit source body" in str(payload):
                raise RuntimeError("operations response leaked raw source content")
            print(
                "knowledge operations runtime acceptance passed: "
                f"nodes={len(payload['nodes'])}, edges={len(payload['edges'])}, "
                f"complete_risk_lineages={audit['complete_risk_lineage_count']}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)
            for name, value in previous.items():
                setattr(settings, name, value)
            repository.close()


def _seed_growth(repository: GrowthRepository) -> None:
    captured_at = _timestamp()
    source = repository.create_source(
        SourceRecord(
            id="runtime-source",
            project_id=PROJECT_ID,
            source_type="test",
            origin="runtime-audit",
            content_hash="a" * 64,
            raw_content="runtime audit source body must never leave the operations projection",
            status=SourceStatus.ELIGIBLE,
            captured_at=captured_at,
            updated_at=captured_at,
        )
    )
    method = repository.create_method(
        MethodAsset(
            id="runtime-method",
            project_id=PROJECT_ID,
            slug="runtime-audit-method",
            name="Runtime audit method",
            status=MethodStatus.PUBLISHED,
            active_revision_id="runtime-method-revision",
            created_at=captured_at,
            updated_at=captured_at,
        )
    )
    revision = repository.save_method_revision(
        MethodRevision(
            id="runtime-method-revision",
            project_id=PROJECT_ID,
            method_id=method["id"],
            version=1,
            body="# Runtime audit method",
            status=MethodStatus.PUBLISHED,
            created_at=captured_at,
        )
    )
    repository.add_lineage_edge(
        KnowledgeLineageEdge(
            id="runtime-source-method",
            project_id=PROJECT_ID,
            from_type="source",
            from_id=source["id"],
            to_type="method",
            to_id=method["id"],
            relation="source_distills_method_proposal",
            created_at=captured_at,
        )
    )
    output = repository.register_output(
        OutputAsset(
            id="runtime-output",
            project_id=PROJECT_ID,
            kind="report",
            title="Runtime audit output",
            content_hash=sha256(b"runtime-audit-output").hexdigest(),
            vault_path="outputs/runtime-audit.md",
            method_revision_id=revision["id"],
            source_refs=[source["id"]],
            idempotency_key="runtime-audit-output",
            status=OutputStatus.ACCEPTED,
            created_at=captured_at,
            updated_at=captured_at,
        )
    )
    feedback = repository.add_output_feedback(
        OutputFeedback(
            id="runtime-feedback",
            project_id=PROJECT_ID,
            output_id=output["id"],
            feedback_type=FeedbackType.ACCEPTED,
            actor_id="runtime-audit",
            created_at=captured_at,
        )
    )
    repository.add_lineage_edge(
        KnowledgeLineageEdge(
            id="runtime-feedback-output",
            project_id=PROJECT_ID,
            from_type="feedback",
            from_id=feedback["id"],
            to_type="output",
            to_id=output["id"],
            relation="feedback_evaluates_output",
            created_at=captured_at,
        )
    )


def _seed_artifacts(store: ArtifactGraphStore) -> None:
    created_at = _timestamp().isoformat()
    store.add(MissionArtifact(project_id=PROJECT_ID, artifact_id="runtime-mission", mission_id="runtime-mission", title="Runtime audit", created_at=created_at))
    store.add(AssumptionArtifact(project_id=PROJECT_ID, artifact_id="runtime-assumption", parent_ids=["runtime-mission"], statement="A durable lifecycle can be audited.", criticality=Severity.HIGH, created_at=created_at))
    store.add(RiskArtifact(project_id=PROJECT_ID, artifact_id="runtime-risk", parent_ids=["runtime-assumption"], risk_statement="Lifecycle records are incomplete.", severity=Severity.HIGH, created_at=created_at))
    store.add(DynamicSOPArtifact(project_id=PROJECT_ID, artifact_id="runtime-sop", mission_id="runtime-mission", parent_ids=["runtime-mission"], title="Runtime audit SOP", created_at=created_at))
    store.add(RuntimeContextArtifact(project_id=PROJECT_ID, artifact_id="runtime-context", mission_id="runtime-mission", parent_ids=["runtime-sop"], source_ids=["runtime-source"], method_ids=["runtime-method"], created_at=created_at))
    store.add(ExecutionResultArtifact(project_id=PROJECT_ID, artifact_id="runtime-execution", execution_id="runtime-execution", mission_id="runtime-mission", dynamic_sop_id="runtime-sop", execution_status="completed", parent_ids=["runtime-context"], created_at=created_at))
    store.add(TaskVerificationArtifact(project_id=PROJECT_ID, artifact_id="runtime-verification", mission_id="runtime-mission", execution_id="runtime-execution", dynamic_sop_id="runtime-sop", verification_status="passed", parent_ids=["runtime-execution"], created_at=created_at))
    store.add(MemoryArtifact(project_id=PROJECT_ID, artifact_id="runtime-memory", memory_kind="feedback", statement="Runtime audit feedback is available.", parent_ids=["runtime-verification"], created_at=created_at))


if __name__ == "__main__":
    main()
