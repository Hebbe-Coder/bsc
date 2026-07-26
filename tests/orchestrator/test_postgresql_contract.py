import os
import uuid

import pytest

from app.agent.state import ProjectDraft, ProjectDraftRepository
from app.core.database import PostgreSQLBackend, init_database
from app.core.preference_db import PreferenceDB
from app.knowledge.schema import ensure_schema
from app.orchestrator.contracts import EventType, OrchestratorEvent
from app.orchestrator.event_store import DatabaseEventStore
from app.repositories import GraphRepository, KnowledgeRepository, ProjectRepository


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL is required for the PostgreSQL repository contract",
)
def test_postgresql_matches_runtime_persistence_contract():
    pytest.importorskip("psycopg2")
    backend = PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"])
    session_id = f"contract-{uuid.uuid4().hex[:12]}"
    try:
        init_database(backend)
        project_repo = ProjectRepository(backend=backend)
        project = project_repo.create_project("PostgreSQL contract")
        asset = project_repo.save_asset(project["id"], "report", {"ok": True})
        document = project_repo.save_document(
            project["id"], "prd", "contract.md", "contract content"
        )
        knowledge_repo = KnowledgeRepository(backend=backend)
        ensure_schema(knowledge_repo)
        entity = knowledge_repo.save_knowledge_entity(
            "postgres-contract-entity",
            project["id"],
            "fact",
            "PostgreSQL entity",
        )
        graph = GraphRepository(backend=backend).save_graph_snapshot(
            "postgres-contract-graph",
            "PostgreSQL graph",
            {},
            project_id=project["id"],
        )
        preferences = PreferenceDB(backend=backend)

        repo = ProjectDraftRepository(connection=backend)
        repo.save(
            ProjectDraft(
                session_id=session_id,
                tenant_id="tenant-contract",
                project_id="project-contract",
                owner_session_id="browser-contract",
                idea="postgres contract",
                status="queued",
            )
        )
        event_store = DatabaseEventStore(backend)
        event = OrchestratorEvent(
            session_id=session_id,
            seq=1,
            type=EventType.PIPELINE_STARTED,
            stage="pipeline",
            status="running",
            message="started",
        )
        event_store.append(event)
        repo.record_event(event)

        restored = repo.get(session_id)
        assert restored is not None
        assert restored.tenant_id == "tenant-contract"
        assert restored.project_id == "project-contract"
        assert restored.owner_session_id == "browser-contract"
        assert restored.current_stage == "pipeline"
        assert restored.event_seq == 1
        assert event_store.events_after(session_id, after=0) == [event]
        assert asset["project_id"] == project["id"]
        assert document["project_id"] == project["id"]
        assert entity["project_id"] == project["id"]
        assert graph["project_id"] == project["id"]
        assert preferences.create_user("postgres-contract-user", name="Contract User")
        assert preferences.get_user("postgres-contract-user")["name"] == "Contract User"
    finally:
        try:
            backend.execute("DROP SCHEMA public CASCADE")
            backend.execute("CREATE SCHEMA public")
            backend.commit()
        except Exception:
            backend.rollback()
        backend.close()
