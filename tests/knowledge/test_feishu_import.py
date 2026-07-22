import pytest

from app.knowledge.feishu_import import FeishuImportError, FeishuImportService
from app.knowledge.wiki_repository import WikiRepository


def _document_payload(**overrides):
    payload = {
        "document_id": "doccnA1",
        "revision_id": "rev-7",
        "document_type": "document",
        "source_url": "https://example.feishu.cn/docx/doccnA1",
        "title": "Agent research",
        "content": "Grounded document content.",
        "source_time": "2026-07-22T08:00:00Z",
        "attachments": [
            {
                "attachment_id": "file-a",
                "name": "diagram.png",
                "mime_type": "image/png",
                "byte_size": 128,
                "content_hash": "a" * 64,
                "access_state": "available",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_feishu_explicit_import_preserves_revision_and_attachment_provenance(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "feishu.db"))
    try:
        result = FeishuImportService(repo).import_export(
            project_id="project-a", payload=_document_payload(), authorized=True
        )

        assert result.created is True
        source = result.source
        assert source["project_id"] == "project-a"
        assert source["source_type"] == "feishu_document"
        assert source["origin"] == "https://example.feishu.cn/docx/doccnA1"
        assert source["metadata"]["feishu_document_id"] == "doccnA1"
        assert source["metadata"]["feishu_revision_id"] == "rev-7"
        assert source["metadata"]["source_time"] == "2026-07-22T08:00:00+00:00"
        assert source["metadata"]["capture_time"]
        assert source["metadata"]["attachments"][0]["name"] == "diagram.png"
        assert "Grounded document content." in source["raw_content"]
    finally:
        repo.close()


def test_feishu_minutes_and_duplicate_revision_are_idempotent_per_project(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "feishu-minutes.db"))
    service = FeishuImportService(repo)
    payload = _document_payload(
        document_id="minutes-9",
        revision_id="rev-2",
        document_type="minutes",
        source_url="https://example.feishu.cn/minutes/minutes-9",
        title="Weekly review",
        content="Decision: retain evidence gates.",
    )
    try:
        first = service.import_export(project_id="project-a", payload=payload, authorized=True)
        duplicate = service.import_export(project_id="project-a", payload=payload, authorized=True)
        other_project = service.import_export(project_id="project-b", payload=payload, authorized=True)

        assert first.created is True
        assert duplicate.created is False
        assert duplicate.source["id"] == first.source["id"]
        assert first.source["source_type"] == "feishu_minutes"
        assert other_project.created is True
        assert other_project.source["project_id"] == "project-b"
    finally:
        repo.close()


def test_feishu_import_reports_expired_authorization_without_leaking_credentials(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "feishu-auth.db"))
    try:
        with pytest.raises(FeishuImportError) as captured:
            FeishuImportService(repo).import_export(
                project_id="project-a",
                payload=_document_payload(error="Bearer secret-token-123456789 expired"),
                authorized=False,
                authorization_status="expired",
            )

        assert captured.value.code == "feishu_authorization_expired"
        assert captured.value.retryable is True
        assert "secret-token" not in str(captured.value)
        assert repo.list_sources("project-a") == []
    finally:
        repo.close()


def test_feishu_import_retains_missing_attachment_access_as_truthful_descriptor(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "feishu-attachment.db"))
    payload = _document_payload(
        attachments=[
            {
                "attachment_id": "file-private",
                "name": "private.pdf",
                "mime_type": "application/pdf",
                "access_state": "unavailable",
                "error": "Authorization: Bearer private-token-123456789",
            }
        ]
    )
    try:
        result = FeishuImportService(repo).import_export(project_id="project-a", payload=payload, authorized=True)
        attachment = result.source["metadata"]["attachments"][0]

        assert result.created is True
        assert attachment["access_state"] == "unavailable"
        assert attachment["extraction_state"] == "extraction_unavailable"
        assert "private-token" not in str(result.source)
    finally:
        repo.close()


def test_feishu_import_rejects_non_export_payloads_and_embedded_credentials(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "feishu-invalid.db"))
    try:
        with pytest.raises(FeishuImportError, match="explicit exported payload"):
            FeishuImportService(repo).import_export(project_id="project-a", payload={}, authorized=True)
        with pytest.raises(FeishuImportError, match="credentials"):
            FeishuImportService(repo).import_export(
                project_id="project-a",
                payload=_document_payload(access_token="token-value"),
                authorized=True,
            )
        with pytest.raises(FeishuImportError, match="credentials"):
            FeishuImportService(repo).import_export(
                project_id="project-a",
                payload=_document_payload(metadata={"tenant_access_token": "tenant-secret"}),
                authorized=True,
            )
    finally:
        repo.close()
