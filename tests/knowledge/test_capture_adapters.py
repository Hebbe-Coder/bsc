import hashlib

import pytest

from app.knowledge.capture_adapters import CaptureAdapter, CaptureAdapterError, redact_secrets
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import SourceCaptureService


def test_adapter_redacts_secrets_and_preserves_external_provenance():
    adapter = CaptureAdapter()
    payload = adapter.normalize(
        project_id="project-a",
        source_type="browser_clip",
        origin="https://example.com/article",
        content="API_KEY=sk-live-secret\nUseful claim",
        metadata={"title": "Article", "authorization": "Bearer secret"},
    )
    assert "sk-live-secret" not in payload.raw_content
    assert payload.metadata["title"] == "Article"
    assert payload.metadata["authorization"] == "[REDACTED]"
    assert payload.metadata["capture_adapter"] == "browser_clip"


def test_redact_secrets_handles_nested_metadata():
    result = redact_secrets(
        {"token": "abc", "nested": {"api_key": "def", "safe": "token=plain-secret"}}
    )
    assert result == {
        "token": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "safe": "[REDACTED]"},
    }


def test_adapter_rejects_unknown_channels_and_requires_an_origin():
    adapter = CaptureAdapter()

    with pytest.raises(CaptureAdapterError, match="unsupported capture source_type"):
        adapter.normalize(project_id="project-a", source_type="arbitrary_plugin", origin="file.md", content="text")
    with pytest.raises(CaptureAdapterError, match="origin"):
        adapter.normalize(project_id="project-a", source_type="browser_clip", origin="", content="text")
    with pytest.raises(CaptureAdapterError, match="credentials"):
        adapter.normalize(
            project_id="project-a",
            source_type="browser_clip",
            origin="https://example.com/article?access_token=private-value",
            content="text",
        )
    with pytest.raises(CaptureAdapterError, match="credentials"):
        adapter.normalize(
            project_id="project-a",
            source_type="browser_clip",
            origin="https://user:password@example.com/article",
            content="text",
        )


def test_binary_capture_uses_original_bytes_for_identity_without_decoding_them():
    payload = CaptureAdapter().normalize(
        project_id="project-a",
        source_type="manual_upload",
        origin="uploads/research.pdf",
        content=b"%PDF-\xff\x00source-bytes",
        mime_type="application/pdf",
        source_revision="upload-1",
    )

    assert payload.content_hash == hashlib.sha256(b"%PDF-\xff\x00source-bytes").hexdigest()
    assert payload.metadata["byte_size"] == len(b"%PDF-\xff\x00source-bytes")
    assert payload.metadata["mime_type"] == "application/pdf"
    assert payload.metadata["extraction_status"] == "extraction_unavailable"
    assert "uploads/research.pdf" in payload.raw_content


def test_annotations_are_curated_opinion_and_provenance_is_normalized():
    payload = CaptureAdapter().normalize(
        project_id="project-a",
        source_type="browser_clip",
        origin="https://example.com/research",
        content="External claim",
        mime_type="text/html",
        source_time="2026-07-21T10:00:00Z",
        capture_time="2026-07-22T10:00:00Z",
        annotations=["This is useful for my project."],
        external_provenance={"provider": "browser", "request_token": "secret-value"},
    )

    assert payload.metadata["source_time"] == "2026-07-21T10:00:00+00:00"
    assert payload.metadata["capture_time"] == "2026-07-22T10:00:00+00:00"
    assert payload.metadata["annotations"] == [
        {"text": "This is useful for my project.", "classification": "curated_opinion"}
    ]
    assert payload.metadata["external_provenance"]["request_token"] == "[REDACTED]"


def test_adopted_bsc_artifact_requires_matching_project_ownership():
    adapter = CaptureAdapter()

    with pytest.raises(CaptureAdapterError, match="project ownership"):
        adapter.normalize(
            project_id="project-a",
            source_type="bsc_artifact",
            origin="artifacts/legacy.md",
            content="legacy",
            external_provenance={"artifact_project_id": "project-b", "artifact_id": "artifact-1"},
        )


def test_adapter_routes_normalized_input_through_immutable_capture_service(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "adapter-capture.db"))
    adapter = CaptureAdapter(SourceCaptureService(repo))
    try:
        first = adapter.capture(
            project_id="project-a",
            source_type="browser_clip",
            origin="https://example.com/one",
            content="Same immutable evidence",
        )
        duplicate = adapter.capture(
            project_id="project-a",
            source_type="browser_clip",
            origin="https://example.com/one",
            content="Same immutable evidence",
        )
        other_project = adapter.capture(
            project_id="project-b",
            source_type="browser_clip",
            origin="https://example.com/one",
            content="Same immutable evidence",
        )

        assert first.created is True
        assert duplicate.created is False
        assert other_project.created is True
        assert repo.list_sources("project-a")[0]["raw_content"] == "Same immutable evidence"
    finally:
        repo.close()


def test_adapter_bounds_attachments_and_metadata():
    adapter = CaptureAdapter()

    with pytest.raises(CaptureAdapterError, match="attachments"):
        adapter.normalize(
            project_id="project-a",
            source_type="manual_upload",
            origin="upload.md",
            content="content",
            attachments=[{"name": f"file-{index}.txt"} for index in range(101)],
        )
    with pytest.raises(CaptureAdapterError, match="metadata"):
        adapter.normalize(
            project_id="project-a",
            source_type="manual_upload",
            origin="upload.md",
            content="content",
            metadata={"oversized": "x" * 70_000},
        )
    with pytest.raises(CaptureAdapterError, match="mime_type"):
        adapter.normalize(
            project_id="project-a",
            source_type="manual_upload",
            origin="upload.md",
            content="content",
            attachments=[{"name": "unsafe", "mime_type": "text/plain\r\nX-Injected: true"}],
        )
    with pytest.raises(CaptureAdapterError, match="annotation"):
        adapter.normalize(
            project_id="project-a",
            source_type="manual_upload",
            origin="upload.md",
            content="content",
            annotations=[{}],
        )
