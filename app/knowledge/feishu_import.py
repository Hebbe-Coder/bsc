"""Explicit, authorized Feishu export ingestion into immutable A evidence."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.knowledge.capture_adapters import CaptureAdapter, redact_secrets
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CaptureResult, SourceCaptureService


class FeishuImportError(ValueError):
    """A credential-safe Feishu import failure with automation semantics."""

    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(str(redact_secrets(message)))
        self.code = code
        self.retryable = retryable


class FeishuAttachment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attachment_id: str = ""
    name: str = Field(min_length=1, max_length=512)
    mime_type: str = "application/octet-stream"
    byte_size: int | None = Field(default=None, ge=0)
    content_hash: str = ""
    origin: str = ""
    revision: str = ""
    access_state: str = "available"
    extraction_state: str = ""
    error: str = ""

    @field_validator("access_state")
    @classmethod
    def validate_access_state(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"available", "unavailable", "missing"}:
            raise ValueError("access_state must be available, unavailable, or missing")
        return normalized


class FeishuExport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(min_length=1, max_length=256)
    revision_id: str = Field(min_length=1, max_length=256)
    document_type: str
    source_url: str = Field(min_length=1, max_length=2_048)
    title: str = Field(min_length=1, max_length=1_000)
    content: str = ""
    source_time: str = ""
    attachments: list[FeishuAttachment] = Field(default_factory=list, max_length=100)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {"doc": "document", "docx": "document", "meeting": "minutes", "meeting_minutes": "minutes"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"document", "minutes"}:
            raise ValueError("document_type must be document or minutes")
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("https://", "http://")) or any(character in normalized for character in "\r\n\x00"):
            raise ValueError("source_url must be an HTTP(S) URL")
        return normalized


class FeishuImportService:
    """Import user-selected CLI/export payloads; this service never fetches Feishu."""

    def __init__(self, repository: WikiRepository) -> None:
        self.adapter = CaptureAdapter(SourceCaptureService(repository))

    def import_export(
        self,
        *,
        project_id: str,
        payload: Mapping[str, Any],
        authorized: bool,
        authorization_status: str = "authorized",
    ) -> CaptureResult:
        if not authorized:
            normalized_status = authorization_status.strip().lower()
            expired = normalized_status == "expired"
            raise FeishuImportError(
                "Feishu authorization expired" if expired else "Feishu authorization is required",
                code="feishu_authorization_expired" if expired else "feishu_authorization_required",
                retryable=expired,
            )
        if self._contains_credential_field(payload):
            raise FeishuImportError(
                "Feishu exported payload must not contain credentials",
                code="feishu_payload_contains_credentials",
                retryable=False,
            )
        try:
            export = FeishuExport.model_validate(payload)
        except ValidationError as exc:
            raise FeishuImportError(
                "Feishu import requires an explicit exported payload with document and revision provenance",
                code="feishu_export_invalid",
                retryable=False,
            ) from exc

        source_type = "feishu_minutes" if export.document_type == "minutes" else "feishu_document"
        attachments = [attachment.model_dump(mode="python") for attachment in export.attachments]
        provenance = {
            "provider": "feishu",
            "feishu_document_id": export.document_id,
            "feishu_revision_id": export.revision_id,
            "feishu_document_type": export.document_type,
            "source_url": export.source_url,
            "import_mode": "explicit_export",
        }
        result = self.adapter.capture(
            project_id=project_id,
            source_type=source_type,
            origin=export.source_url,
            content=export.content or f"Extraction unavailable for Feishu {export.document_type}: {export.title}",
            mime_type="text/markdown",
            source_revision=export.revision_id,
            source_time=export.source_time or None,
            extraction_status="complete" if export.content.strip() else "extraction_unavailable",
            attachments=attachments,
            external_provenance=provenance,
            metadata={
                "title": export.title,
                "feishu_document_id": export.document_id,
                "feishu_revision_id": export.revision_id,
                "feishu_document_type": export.document_type,
            },
            trust_level="reviewed",
        )
        return result

    @classmethod
    def _contains_credential_field(cls, value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                if (
                    normalized == "token"
                    or normalized.endswith("_token")
                    or any(
                        marker in normalized
                        for marker in ("authorization", "api_key", "secret", "password", "credential")
                    )
                ):
                    return True
                if cls._contains_credential_field(item):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(cls._contains_credential_field(item) for item in value)
        return False
