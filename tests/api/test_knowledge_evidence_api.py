import re
import socket

from fastapi.testclient import TestClient
from PIL import Image

from app.api.knowledge_evidence_api import get_evidence_repository
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import ExtractionArtifact, ExtractionStatus, MediaAsset, ReferenceLink, SourceRecord, TableArtifact
from app.main import app


_FORBIDDEN_EVIDENCE_BODY_FIELDS = frozenset({
    "raw_content", "content", "claim_text", "prompt", "provider_response",
})


def _assert_redacted_evidence_payload(value):
    if isinstance(value, dict):
        assert not _FORBIDDEN_EVIDENCE_BODY_FIELDS.intersection(value), value
        for nested in value.values():
            _assert_redacted_evidence_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_redacted_evidence_payload(nested)


def test_evidence_api_returns_project_scoped_read_models_without_source_or_derivative_bodies(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "evidence-api.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="article",
            origin="https://example.com/research",
            content_hash="a" * 64,
            raw_content="PRIVATE SOURCE BODY MUST NOT LEAK",
        )
    )
    vault_source = repository.create_source(
        SourceRecord(
            id="source-vault-a",
            project_id="project-a",
            source_type="obsidian_plugin:clipper",
            origin="projects/project-a/00_Inbox/private.md",
            content_hash="d" * 64,
            raw_content="PRIVATE VAULT BODY MUST NOT LEAK",
        )
    )
    asset = repository.register_media_asset(
        MediaAsset(
            id="asset-a",
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/csv",
            byte_hash="b" * 64,
            byte_size=42,
            storage_ref="projects/project-a/01_Sources/metrics.csv",
        )
    )
    extraction = repository.create_extraction_artifact(
        ExtractionArtifact(
            id="extract-a",
            project_id="project-a",
            source_id=source["id"],
            asset_id=asset["id"],
            extractor="csv-table",
            extractor_revision="local-v1",
            input_hash="b" * 64,
            content_hash="c" * 64,
            content="PRIVATE DERIVATIVE BODY MUST NOT LEAK",
            status=ExtractionStatus.COMPLETE,
            metadata={"row_count": 2, "column_count": 2},
        )
    )
    table = repository.create_table_artifact(
        TableArtifact(
            id="table-a",
            project_id="project-a",
            source_id=source["id"],
            extraction_id=extraction["id"],
            schema=["month", "revenue_usd"],
            row_count=2,
            units={"revenue_usd": "USD"},
            content_hash="c" * 64,
        )
    )
    repository.create_reference_link(
        ReferenceLink(
            id="reference-a",
            project_id="project-a",
            source_id=source["id"],
            target_type="table",
            target_id=table["id"],
            anchor_type="table_column",
            anchor="revenue_usd",
            relation="supports",
        )
    )
    repository.create_reference_link(
        ReferenceLink(
            id="reference-wiki-a",
            project_id="project-a",
            source_id=source["id"],
            target_type="wiki_page",
            target_id="wiki-overview-a",
            anchor_type="heading",
            anchor="Evidence handling",
            relation="explains",
        )
    )
    repository.create_reference_link(
        ReferenceLink(
            id="reference-url-a",
            project_id="project-a",
            source_id=source["id"],
            target_type="url",
            target_id="url:2a3dbf6d9f11c0a7",
            anchor_type="source_metadata",
            anchor="https://doi.org/10.1234/example",
            relation="declares_url",
        )
    )
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "evidence-key"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer evidence-key"}
        response = client.get("/knowledge/evidence/projects/project-a?limit=10", headers=headers)
        assert response.status_code == 200
        payload = response.json()["data"]
        _assert_redacted_evidence_payload(payload)
        assert payload["state"] == "available"
        assert payload["summary"]["assets"] == 1
        assert payload["summary"]["extractions"]["complete"] == 1
        assert payload["summary"]["tables"] == 1
        assert payload["summary"]["references"] == 3
        assert source["id"] in {item["id"] for item in payload["sources"]}
        redacted_vault = next(item for item in payload["sources"] if item["id"] == vault_source["id"])
        assert redacted_vault["origin"] == "vault-source:source-v"
        assert redacted_vault["origin_kind"] == "vault"
        assert payload["assets"][0]["id"] == "asset-a"
        assert payload["extractions"][0]["id"] == "extract-a"
        assert payload["tables"][0]["schema"] == ["month", "revenue_usd"]
        assert payload["graph"]["nodes"]
        assert {node["id"] for node in payload["graph"]["nodes"]} >= {
            "source-a", "asset-a", "extract-a", "table-a", "target:wiki_page:wiki-overview-a", "target:url:url:2a3dbf6d9f11c0a7",
        }
        labels = {node["id"]: node["label"] for node in payload["graph"]["nodes"]}
        assert labels["source-a"] == "Source: example.com/research"
        assert labels["source-vault-a"] == "Vault source: source-v"
        assert labels["asset-a"] == "Asset: CSV"
        assert labels["extract-a"] == "Extraction: CSV table (complete)"
        assert labels["table-a"] == "Table: 2 rows"
        assert labels["target:wiki_page:wiki-overview-a"] == "Wiki page: wiki-ov"
        assert labels["target:url:url:2a3dbf6d9f11c0a7"] == "URL: doi.org/10.1234/example"
        url_target = next(item for item in payload["graph"]["nodes"] if item["id"] == "target:url:url:2a3dbf6d9f11c0a7")
        assert url_target["anchor"] == "https://doi.org/10.1234/example"
        wiki_edge = next(edge for edge in payload["graph"]["edges"] if edge["id"] == "reference-wiki-a")
        assert wiki_edge["target"] == "target:wiki_page:wiki-overview-a"
        assert payload["graph"]["edges"]
        assert any(edge["id"].startswith("source-asset:") for edge in payload["graph"]["edges"])
        bounded = client.get("/knowledge/evidence/projects/project-a?limit=4", headers=headers)
        bounded_graph = bounded.json()["data"]["graph"]
        assert any(edge["id"].startswith("source-asset:") for edge in bounded_graph["edges"])
        assert bounded_graph["omitted_edge_count"] >= 1
        assert "PRIVATE SOURCE BODY" not in response.text
        assert "projects/project-a" not in response.text
        assert "PRIVATE VAULT BODY" not in response.text
        assert "PRIVATE DERIVATIVE BODY" not in response.text

        detail = client.get("/knowledge/evidence/projects/project-a/records/extraction/extract-a", headers=headers)
        assert detail.status_code == 200
        _assert_redacted_evidence_payload(detail.json()["data"])
        assert detail.json()["data"]["record"]["id"] == "extract-a"
        assert "content" not in detail.json()["data"]["record"]

        source_detail = client.get("/knowledge/evidence/projects/project-a/records/source/source-a", headers=headers)
        assert source_detail.status_code == 200
        _assert_redacted_evidence_payload(source_detail.json()["data"])
        assert source_detail.json()["data"]["record"]["id"] == "source-a"
        assert "raw_content" not in source_detail.text

        empty = client.get("/knowledge/evidence/projects/project-b", headers=headers)
        assert empty.status_code == 200
        assert empty.json()["data"]["state"] == "no_sample"
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()


def test_evidence_overview_and_record_queries_are_metadata_only_read_only_and_offline(tmp_path, monkeypatch):
    """Protect the default Atlas path from source-body reads, writes and network access."""
    repository = GrowthRepository(db_path=str(tmp_path / "evidence-metadata-boundary.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-private-a",
            project_id="project-a",
            source_type="article",
            origin="https://example.test/private",
            content_hash="a" * 64,
            raw_content="PRIVATE SOURCE BODY MUST NEVER BE QUERIED BY EVIDENCE ATLAS",
        )
    )
    repository.record_publication(
        project_id="project-a",
        contents={"wiki/private.md": f"# Private claim\n[source:{source['id']}]\n"},
        source_ids=[],
    )
    citation_id = repository.list_citations("project-a")[0]["id"]

    executed_sql: list[str] = []
    original_execute = repository._execute

    def read_only_metadata_execute(sql: str, params: tuple = ()):
        normalized = " ".join(sql.split())
        executed_sql.append(normalized)
        assert normalized.upper().startswith("SELECT "), normalized
        assert "RAW_CONTENT" not in normalized.upper(), normalized
        assert "CLAIM_TEXT" not in normalized.upper(), normalized
        assert not re.search(r"\bCONTENT\b", normalized, flags=re.IGNORECASE), normalized
        return original_execute(sql, params)

    def reject_full_source_read(*_args, **_kwargs):
        raise AssertionError("Evidence Atlas must use the metadata-only source projection")

    def reject_network(*_args, **_kwargs):
        raise AssertionError("Evidence Atlas metadata reads must not access the network")

    monkeypatch.setattr(repository, "_execute", read_only_metadata_execute)
    monkeypatch.setattr(repository, "list_sources", reject_full_source_read)
    monkeypatch.setattr(repository, "get_source", reject_full_source_read)
    monkeypatch.setattr(repository, "list_citations", reject_full_source_read)
    monkeypatch.setattr(repository, "get_citation", reject_full_source_read)

    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "evidence-key"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            # Start Starlette's local transport before disallowing external connections.
            monkeypatch.setattr(socket, "create_connection", reject_network)
            headers = {"Authorization": "Bearer evidence-key"}
            overview = client.get("/knowledge/evidence/projects/project-a", headers=headers)
            assert overview.status_code == 200
            _assert_redacted_evidence_payload(overview.json()["data"])
            assert overview.json()["data"]["summary"] == {
                "sources": 1,
                "assets": 0,
                "extractions": {},
                "tables": 0,
                "references": 1,
                "source_statuses": {"captured": 1},
                "denominator": 2,
            }

            detail = client.get(
                f"/knowledge/evidence/projects/project-a/records/reference/citation:{citation_id}",
                headers=headers,
            )
            assert detail.status_code == 200
            _assert_redacted_evidence_payload(detail.json()["data"])
            assert executed_sql
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()


def test_evidence_api_projects_persisted_wiki_citations_as_read_only_references(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "evidence-citation-projection.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-citation-a",
            project_id="project-a",
            source_type="research_note",
            origin="projects/project-a/01_Sources/private.md",
            content_hash="a" * 64,
            raw_content="PRIVATE SOURCE BODY MUST NOT LEAK THROUGH A CITATION",
        )
    )
    repository.record_publication(
        project_id="project-a",
        contents={"wiki/decision.md": f"# Evidence-backed decision\n[source:{source['id']}]\n"},
        source_ids=[],
    )
    citation = repository.list_citations("project-a")[0]
    page = repository.list_pages("project-a")[0]
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "evidence-key"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer evidence-key"}
        response = client.get("/knowledge/evidence/projects/project-a", headers=headers)
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["summary"]["references"] == 1
        projected = payload["references"][0]
        assert projected["id"] == f"citation:{citation['id']}"
        assert projected["source_id"] == source["id"]
        assert projected["target_type"] == "wiki_page"
        assert projected["target_id"] == page["id"]
        assert projected["relation"] == "cites"
        assert projected["resolution_state"] == "resolved"
        assert any(
            edge["id"] == projected["id"]
            and edge["source"] == source["id"]
            and edge["target"] == f"target:wiki_page:{page['id']}"
            for edge in payload["graph"]["edges"]
        )
        detail = client.get(
            f"/knowledge/evidence/projects/project-a/records/reference/{projected['id']}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["record"] == projected
        assert "PRIVATE SOURCE BODY" not in response.text
        assert "Evidence-backed decision" not in response.text
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()


def test_evidence_api_returns_a_bounded_authorized_table_preview_without_raw_source_body(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "table-preview.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-table-a",
            project_id="project-a",
            source_type="spreadsheet",
            origin="projects/project-a/01_Sources/financials.csv",
            content_hash="a" * 64,
            raw_content="PRIVATE RAW SOURCE BODY MUST NOT LEAK",
        )
    )
    asset = repository.register_media_asset(
        MediaAsset(
            id="asset-table-a",
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/csv",
            byte_hash="b" * 64,
            byte_size=42,
            storage_ref="projects/project-a/01_Sources/financials.csv",
        )
    )
    extraction = repository.create_extraction_artifact(
        ExtractionArtifact(
            id="extract-table-a",
            project_id="project-a",
            source_id=source["id"],
            asset_id=asset["id"],
            extractor="csv-table",
            extractor_revision="local-v2",
            input_hash="b" * 64,
            content_hash="c" * 64,
            content="month\tspend_usd\n2026-07\t120\n2026-08\t240\n2026-09\t360",
            status=ExtractionStatus.COMPLETE,
            metadata={"row_count": 3, "column_count": 2},
        )
    )
    table = repository.create_table_artifact(
        TableArtifact(
            id="table-preview-a",
            project_id="project-a",
            source_id=source["id"],
            extraction_id=extraction["id"],
            schema=["month", "spend_usd"],
            row_count=3,
            units={"spend_usd": "USD"},
            content_hash="c" * 64,
        )
    )
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "evidence-key"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer evidence-key"}
        first_page = client.get(
            f"/knowledge/evidence/projects/project-a/tables/{table['id']}/preview?page=1&page_size=2",
            headers=headers,
        )
        assert first_page.status_code == 200
        payload = first_page.json()["data"]
        assert payload["table_id"] == table["id"]
        assert payload["schema"] == ["month", "spend_usd"]
        assert payload["units"] == {"spend_usd": "USD"}
        assert payload["rows"] == [["2026-07", "120"], ["2026-08", "240"]]
        assert payload["page"] == 1
        assert payload["page_size"] == 2
        assert payload["total_rows"] == 3
        assert payload["total_pages"] == 2
        assert payload["derived"] is True
        assert "PRIVATE RAW SOURCE BODY" not in first_page.text

        second_page = client.get(
            f"/knowledge/evidence/projects/project-a/tables/{table['id']}/preview?page=2&page_size=2",
            headers=headers,
        )
        assert second_page.status_code == 200
        assert second_page.json()["data"]["rows"] == [["2026-09", "360"]]

        wrong_project = client.get(
            f"/knowledge/evidence/projects/project-b/tables/{table['id']}/preview",
            headers=headers,
        )
        assert wrong_project.status_code == 404

        mismatched = repository.create_table_artifact(
            TableArtifact(
                id="table-preview-mismatch",
                project_id="project-a",
                source_id=source["id"],
                extraction_id=extraction["id"],
                schema=["month", "spend_usd"],
                row_count=3,
                units={"spend_usd": "USD"},
                content_hash="d" * 64,
            )
        )
        stale_preview = client.get(
            f"/knowledge/evidence/projects/project-a/tables/{mismatched['id']}/preview",
            headers=headers,
        )
        assert stale_preview.status_code == 200
        assert stale_preview.json()["data"]["rows"] == []
        assert stale_preview.json()["data"]["state"] == "unavailable"
        assert stale_preview.json()["data"]["reason"] == "table_derivative_content_hash_mismatch"
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repository.close()


def test_evidence_api_returns_a_project_scoped_stripped_image_thumbnail(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "image-preview.db"))
    vault_root = tmp_path / "vault"
    image_path = vault_root / "projects" / "project-a" / "01_Sources" / "chart.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (1600, 900), color=(12, 87, 121)).save(image_path, format="PNG")
    repository.configure_vault("project-a", "projects/project-a")
    source = repository.create_source(
        SourceRecord(
            id="source-image-a",
            project_id="project-a",
            source_type="image",
            origin="projects/project-a/01_Sources/chart.png",
            content_hash="a" * 64,
            raw_content="PRIVATE SOURCE BODY MUST NOT LEAK",
        )
    )
    asset = repository.register_media_asset(
        MediaAsset(
            id="asset-image-a",
            project_id="project-a",
            source_id=source["id"],
            mime_type="image/png",
            byte_hash="b" * 64,
            byte_size=image_path.stat().st_size,
            storage_ref="projects/project-a/01_Sources/chart.png",
        )
    )
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    previous_vault_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "evidence-key"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer evidence-key"}
        response = client.get(
            f"/knowledge/evidence/projects/project-a/assets/{asset['id']}/thumbnail",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"
        assert len(response.content) > 100
        assert b"PRIVATE SOURCE BODY" not in response.content

        wrong_project = client.get(
            f"/knowledge/evidence/projects/project-b/assets/{asset['id']}/thumbnail",
            headers=headers,
        )
        assert wrong_project.status_code == 404
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        settings.OBSIDIAN_VAULT_ROOT = previous_vault_root
        app.dependency_overrides.clear()
        repository.close()
