from app.core.config import settings
from app.knowledge.wiki_contracts import MediaAsset, SourceRecord
from app.knowledge.wiki_repository import WikiRepository
from app.mcp import server, wiki_tools


def test_mcp_evidence_tools_are_project_scoped_and_redact_raw_evidence(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "evidence-mcp.db"))
    repository.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="article",
            origin="https://example.test/evidence",
            content_hash="a" * 64,
            raw_content="PRIVATE MCP EVIDENCE BODY",
        )
    )
    repository.register_media_asset(
        MediaAsset(
            id="asset-a",
            project_id="project-a",
            source_id="source-a",
            mime_type="text/plain",
            byte_hash="b" * 64,
            byte_size=24,
            storage_ref="projects/project-a/01_Sources/a.txt",
        )
    )
    monkeypatch.setattr(wiki_tools, "WikiRepository", lambda: WikiRepository(db_path=str(tmp_path / "evidence-mcp.db")))
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_reader", "project-a"))
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", True)
    try:
        overview = server.wiki_evidence("project-a")
        assert overview["sources"][0]["id"] == "source-a"
        assert "PRIVATE MCP EVIDENCE BODY" not in str(overview)

        record = server.wiki_evidence_record("project-a", "source", "source-a")
        assert record["record"]["id"] == "source-a"
        assert "raw_content" not in str(record)

        try:
            server.wiki_evidence("project-b")
            raise AssertionError("cross-project read must be denied")
        except PermissionError:
            pass
    finally:
        repository.close()
