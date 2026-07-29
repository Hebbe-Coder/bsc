"""Optional real PostgreSQL contract for the LLM Wiki persistence facade."""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from app.core.database import PostgreSQLBackend
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.service import KnowledgeService
from app.knowledge.wiki_contracts import KnowledgeRun
from app.knowledge.wiki_repository import PublicationConflictError, WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required")
def test_postgresql_persists_project_scoped_wiki_and_transactional_conflicts():
    project_id = f"knowledge-pg-{uuid4().hex[:10]}"
    backend = PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"])
    repo = WikiRepository(backend=backend)
    try:
        repo.configure_vault(project_id, f"projects/{project_id}")
        source = SourceCaptureService(
            repo,
            search_index=type("Index", (), {"project_source": lambda self, value: {"status": "ingested"}})(),
        ).capture(
            CapturedSourceInput(
                project_id=project_id,
                source_type="manual_upload",
                raw_content="PostgreSQL immutable evidence",
                trust_level="trusted",
            )
        ).source
        repo.record_publication(
            project_id=project_id,
            contents={"wiki/index.md": f"# PostgreSQL Wiki\n[source:{source['id']}]"},
            source_ids=[],
        )
        page = repo.list_pages(project_id)[0]
        run = KnowledgeRun(project_id=project_id, run_type="source_sync", trigger="contract")
        repo.create_run(run)

        with pytest.raises(PublicationConflictError):
            repo.record_publication(
                project_id=project_id,
                contents={"wiki/index.md": "# Must not commit"},
                source_ids=[],
                expected_content_hashes={"wiki/index.md": hashlib.sha256(b"wrong").hexdigest()},
            )

        assert repo.get_page_content(project_id, page["id"])["content"].startswith("# PostgreSQL Wiki")
        assert repo.list_citations(project_id, page["id"])[0]["source_id"] == source["id"]
        assert repo.get_run(project_id, run.id)["status"] == "queued"
        assert repo.list_sources(f"{project_id}-other") == []
    finally:
        for table in (
            "knowledge_run_events", "knowledge_schedule_claims", "knowledge_schedules", "knowledge_runs",
            "knowledge_graph_edges", "knowledge_citations", "knowledge_wiki_page_revisions", "knowledge_wiki_pages",
            "knowledge_proposal_operations", "knowledge_proposals", "knowledge_horizon_import_claims", "knowledge_sources", "knowledge_vaults",
        ):
            repo._execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))  # nosec B608
        repo._commit()
        repo.close()


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required")
def test_postgresql_search_index_uses_dialect_safe_upserts():
    project_id = f"knowledge-index-pg-{uuid4().hex[:10]}"
    doc_id = f"knowledge-index-doc-{uuid4().hex[:10]}"
    backend = PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"])
    repo = WikiRepository(backend=backend)

    class DeterministicProvider(EmbeddingProvider):
        name = "postgres-contract"
        dim = 3

        def embed(self, texts):
            return [[1.0, 0.5, 0.25] for _ in texts]

    prior_model = None
    try:
        prior_model = repo._execute("SELECT vocab_json, idf_json FROM tfidf_model WHERE id=1").fetchone()
        service = KnowledgeService(repo=repo)
        service.backends["vector"] = VectorBackend(repo, provider=DeterministicProvider())
        result = service.ingest_text(
            "PostgreSQL-indexed knowledge must remain searchable after Wiki publication.",
            project_id=project_id,
            title="PostgreSQL Index Contract",
            doc_id=doc_id,
        )
        assert result["status"] == "ingested"

        chunks = repo._execute(
            "SELECT id,content FROM knowledge_chunks WHERE doc_id=? ORDER BY idx", (doc_id,)
        ).fetchall()
        records = [{"id": row["id"], "content": row["content"]} for row in chunks]
        service.backends["tfidf"].index(records)
        service.backends["vector"].index(records)

        tfidf_count = repo._execute(
            "SELECT COUNT(*) AS count FROM knowledge_tfidf WHERE chunk_id IN "
            "(SELECT id FROM knowledge_chunks WHERE doc_id=?)", (doc_id,)
        ).fetchone()["count"]
        vector_count = repo._execute(
            "SELECT COUNT(*) AS count FROM knowledge_vectors WHERE chunk_id IN "
            "(SELECT id FROM knowledge_chunks WHERE doc_id=?)", (doc_id,)
        ).fetchone()["count"]
        assert tfidf_count == len(records)
        assert vector_count == len(records)
    finally:
        try:
            if "service" in locals():
                service.delete_document(doc_id)
            repo._execute("DELETE FROM tfidf_model WHERE id=1")
            if prior_model:
                repo._execute(
                    "INSERT INTO tfidf_model (id,vocab_json,idf_json) VALUES (1,?,?)",
                    (prior_model["vocab_json"], prior_model["idf_json"]),
                )
            repo._commit()
        finally:
            repo.close()


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required")
def test_postgresql_horizon_claim_is_project_scoped_and_idempotent():
    project_id = f"knowledge-horizon-claim-pg-{uuid4().hex[:10]}"
    backend = PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"])
    repo = WikiRepository(backend=backend)
    try:
        first = repo.claim_horizon_import(
            project_id=project_id,
            horizon_run_id="horizon-run-pg",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:1",
            content_hash="a" * 64,
            capture_run_id="capture-pg-a",
        )
        duplicate = repo.claim_horizon_import(
            project_id=project_id,
            horizon_run_id="horizon-run-pg",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:1",
            content_hash="a" * 64,
            capture_run_id="capture-pg-b",
        )
        other_project = repo.claim_horizon_import(
            project_id=f"{project_id}-other",
            horizon_run_id="horizon-run-pg",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:1",
            content_hash="a" * 64,
            capture_run_id="capture-pg-other",
        )

        assert first["claimed"] is True
        assert duplicate["claimed"] is False
        assert other_project["claimed"] is True
        assert repo.complete_horizon_import_claim(
            project_id=project_id,
            horizon_run_id="horizon-run-pg",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:1",
            capture_run_id="capture-pg-a",
            source_id="source-pg-a",
        ) is True
        claim = repo.get_horizon_import_claim(
            project_id=project_id,
            horizon_run_id="horizon-run-pg",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:1",
        )
        assert claim["status"] == "completed"
        assert claim["source_id"] == "source-pg-a"
    finally:
        for scoped_project_id in (project_id, f"{project_id}-other"):
            repo._execute(
                "DELETE FROM knowledge_horizon_import_claims WHERE project_id=?",
                (scoped_project_id,),
            )
        repo._commit()
        repo.close()
