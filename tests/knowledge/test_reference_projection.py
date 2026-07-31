from app.knowledge.reference_projection import SourceReferenceProjector
from app.knowledge.wiki_contracts import SourceRecord
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_capture_projects_a_normalized_http_origin_once_without_exposing_body(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "reference-capture.db"))
    capturer = SourceCaptureService(repository)
    try:
        payload = CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="HTTPS://Publisher.Example:443/research/?utm_source=newsletter&b=2&a=1#section",
            raw_content="PRIVATE BODY MUST NOT BECOME A REFERENCE",
        )

        first = capturer.capture(payload)
        second = capturer.capture(payload)
        references = repository.list_reference_links("project-a", source_id=first.source["id"])

        assert first.created is True
        assert second.created is False
        assert {(item["target_type"], item["anchor"], item["relation"]) for item in references} == {
            ("url", "https://publisher.example/research?a=1&b=2", "declares_url"),
        }
        assert references[0]["target_id"].startswith("url:")
        assert "publisher.example" not in references[0]["target_id"]
        assert all("PRIVATE BODY" not in str(item) for item in references)
        candidate = repository.list_source_reference_candidates("project-a")[0]
        assert "raw_content" not in candidate
    finally:
        repository.close()


def test_metadata_backfill_projects_zotero_identifiers_without_reading_sources_or_writing_vault(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "reference-backfill.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-zotero",
            project_id="project-a",
            source_type="obsidian_plugin:obsidian-zotero-desktop-connector",
            origin="projects/project-a/01_Sources/zotero/smith2025.md",
            vault_path="projects/project-a/01_Sources/zotero/smith2025.md",
            content_hash="a" * 64,
            raw_content="PRIVATE HISTORICAL NOTE BODY",
            metadata={
                "zotero_url": "https://doi.org/10.1234/example",
                "zotero_doi": "doi:10.1234/example",
                "zotero_citation_key": "smith2025",
            },
        )
    )
    try:
        projector = SourceReferenceProjector(repository)
        first = projector.backfill_project("project-a")
        second = projector.backfill_project("project-a")
        references = repository.list_reference_links("project-a", source_id=source["id"])

        assert first == {"examined": 1, "created": 3, "existing": 0, "skipped": 1}
        assert second == {"examined": 1, "created": 0, "existing": 3, "skipped": 1}
        assert {(item["target_type"], item["anchor"], item["relation"]) for item in references} == {
            ("url", "https://doi.org/10.1234/example", "declares_url"),
            ("doi", "10.1234/example", "declares_doi"),
            ("citekey", "smith2025", "declares_citekey"),
        }
        assert all("PRIVATE HISTORICAL NOTE BODY" not in str(item) for item in references)
    finally:
        repository.close()


def test_metadata_projector_rejects_local_paths_malformed_urls_and_invalid_identifiers(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "reference-rejection.db"))
    source = repository.create_source(
        SourceRecord(
            id="source-local",
            project_id="project-a",
            source_type="obsidian_markdown",
            origin="projects/project-a/01_Sources/local.md",
            vault_path="projects/project-a/01_Sources/local.md",
            content_hash="b" * 64,
            raw_content="PRIVATE LOCAL BODY",
            metadata={
                "canonical_url": "file:///D:/bsc/private.md",
                "zotero_url": "https://",
                "zotero_doi": "not a doi",
                "zotero_citation_key": "invalid cite key",
            },
        )
    )
    try:
        result = SourceReferenceProjector(repository).project_source_id("project-a", source["id"])

        assert result == {"created": 0, "existing": 0, "skipped": 5}
        assert repository.list_reference_links("project-a", source_id=source["id"]) == []
    finally:
        repository.close()
