"""Normalize capture channels before they enter immutable A-layer evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import PurePosixPath
import re
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlsplit

from app.knowledge.wiki_source_capture import CapturedSourceInput, CaptureResult, SourceCaptureService

_SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|authorization|credential)", re.IGNORECASE)
_SECRET_VALUE = re.compile(
    r"(?i)(?:"
    r"\b(?:api[_-]?key|token|secret|password|authorization|credential)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;\"']+"
    r"|sk-[a-z0-9_-]{8,}"
    r"|bearer\s+[a-z0-9._-]{8,}"
    r")"
)
_MIME_TYPE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
_MAX_METADATA_BYTES = 65_536
_MAX_ATTACHMENTS = 100

SUPPORTED_CAPTURE_TYPES = frozenset(
    {
        "manual_upload",
        "upload",
        "browser_clip",
        "primary_web",
        "obsidian_import",
        "obsidian_markdown",
        "obsidian_file",
        "feishu_document",
        "feishu_minutes",
        "horizon_signal",
        "horizon_staged_artifact",
        "bsc_artifact",
        "adopted_bsc_artifact",
    }
)


class CaptureAdapterError(ValueError):
    """Raised when untrusted capture input cannot satisfy the frozen contract."""


def redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


class CaptureAdapter:
    """Build one normalized request and optionally persist it via source capture."""

    def __init__(self, capture_service: SourceCaptureService | None = None) -> None:
        self.capture_service = capture_service

    def capture(self, **kwargs: Any) -> CaptureResult:
        if self.capture_service is None:
            raise CaptureAdapterError("capture_service is required to persist normalized evidence")
        return self.capture_service.capture(self.normalize(**kwargs))

    def normalize(
        self,
        *,
        project_id: str,
        source_type: str,
        origin: str,
        content: str | bytes,
        metadata: dict[str, Any] | None = None,
        trust_level: str = "untrusted",
        vault_path: str = "",
        mime_type: str = "",
        source_revision: str = "",
        source_time: str | datetime | None = None,
        capture_time: str | datetime | None = None,
        extraction_text: str = "",
        extraction_status: str = "",
        attachments: Iterable[Mapping[str, Any]] = (),
        annotations: Iterable[str | Mapping[str, Any]] = (),
        external_provenance: Mapping[str, Any] | None = None,
    ) -> CapturedSourceInput:
        project_id = project_id.strip()
        source_type = source_type.strip().lower()
        origin = self._safe_reference(origin, field="origin", required=True)
        if not project_id:
            raise CaptureAdapterError("project_id is required")
        if source_type not in SUPPORTED_CAPTURE_TYPES:
            raise CaptureAdapterError(f"unsupported capture source_type: {source_type or '<empty>'}")
        safe_vault_path = self._vault_path(vault_path)
        provenance = dict(external_provenance or {})
        if source_type in {"bsc_artifact", "adopted_bsc_artifact"}:
            if str(provenance.get("artifact_project_id") or "") != project_id:
                raise CaptureAdapterError("adopted BSC artifact requires matching project ownership")
            if not str(provenance.get("artifact_id") or "").strip():
                raise CaptureAdapterError("adopted BSC artifact requires artifact_id provenance")

        if metadata is not None and not isinstance(metadata, dict):
            raise CaptureAdapterError("metadata must be a mapping")
        attachment_items = list(attachments)
        if len(attachment_items) > _MAX_ATTACHMENTS:
            raise CaptureAdapterError(f"attachments are limited to {_MAX_ATTACHMENTS} entries")
        normalized_attachments = [self._attachment(item) for item in attachment_items]
        normalized_annotations = [self._annotation(item) for item in annotations]
        safe_mime = self._mime_type(mime_type, origin, content)
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        safe_text, extractor_state = self._extraction(
            content=content,
            extraction_text=extraction_text,
            mime_type=safe_mime,
            origin=origin,
            requested_state=extraction_status,
        )
        captured_at = self._time(capture_time, "capture_time", default_now=True)
        sourced_at = self._time(source_time, "source_time", default_now=False)
        safe_metadata = redact_secrets(metadata or {})
        normalized: dict[str, Any] = {
            **safe_metadata,
            "capture_adapter": source_type,
            "source_kind": source_type,
            "original_uri": origin,
            "source_revision": source_revision.strip(),
            "source_time": sourced_at,
            "capture_time": captured_at,
            "mime_type": safe_mime,
            "byte_size": len(raw_bytes),
            "byte_hash": content_hash,
            "extraction_status": extractor_state,
            "attachments": normalized_attachments,
            "annotations": normalized_annotations,
            "external_provenance": redact_secrets(provenance),
        }
        self._bounded_metadata(normalized)
        return CapturedSourceInput(
            project_id=project_id,
            source_type=source_type,
            origin=origin,
            raw_content=redact_secrets(safe_text),
            vault_path=safe_vault_path,
            trust_level=trust_level,
            metadata=normalized,
            content_hash=content_hash,
        )

    @staticmethod
    def _mime_type(value: str, origin: str, content: str | bytes) -> str:
        candidate = value.strip().lower()
        if not candidate:
            candidate = mimetypes.guess_type(origin)[0] or (
                "text/plain" if isinstance(content, str) else "application/octet-stream"
            )
        if len(candidate) > 255 or not _MIME_TYPE.fullmatch(candidate):
            raise CaptureAdapterError("mime_type is invalid")
        return candidate

    @staticmethod
    def _vault_path(value: str) -> str:
        raw = value.strip().replace("\\", "/")
        if not raw:
            return ""
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise CaptureAdapterError("vault_path must be project-relative")
        if path.parts and ":" in path.parts[0]:
            raise CaptureAdapterError("vault_path must not include a drive prefix")
        return path.as_posix()

    @staticmethod
    def _safe_reference(value: str, *, field: str, required: bool) -> str:
        normalized = value.strip()
        if (required and not normalized) or len(normalized) > 2_048 or any(
            character in normalized for character in "\r\n\x00"
        ):
            raise CaptureAdapterError(f"{field} is required and must be a bounded URI or path")
        if not normalized:
            return ""
        parsed = urlsplit(normalized)
        if parsed.username is not None or parsed.password is not None:
            raise CaptureAdapterError(f"{field} must not contain credentials")
        try:
            query_items = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=False)
        except ValueError as exc:
            raise CaptureAdapterError(f"{field} contains an invalid query string") from exc
        if any(_SECRET_KEY.search(key) for key, _value in query_items) or _SECRET_VALUE.search(normalized):
            raise CaptureAdapterError(f"{field} must not contain credentials")
        return normalized

    @staticmethod
    def _time(value: str | datetime | None, field: str, *, default_now: bool) -> str:
        if value in {None, ""}:
            return datetime.now(timezone.utc).isoformat() if default_now else ""
        try:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CaptureAdapterError(f"{field} must be an ISO-8601 datetime") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _extraction(
        *,
        content: str | bytes,
        extraction_text: str,
        mime_type: str,
        origin: str,
        requested_state: str,
    ) -> tuple[str, str]:
        if extraction_text.strip():
            return extraction_text.strip(), requested_state.strip() or "complete"
        if isinstance(content, str):
            if not content.strip():
                return f"Extraction unavailable; source retained at {origin}", requested_state.strip() or "extraction_unavailable"
            return content, requested_state.strip() or "complete"
        if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                return f"UTF-8 extraction failed; source retained at {origin}", requested_state.strip() or "encoding_error"
            if decoded.strip():
                return decoded, requested_state.strip() or "complete"
        return f"Binary source retained by URI and SHA-256 at {origin}", requested_state.strip() or "extraction_unavailable"

    @staticmethod
    def _attachment(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise CaptureAdapterError("attachment descriptors must be mappings")
        name = str(value.get("name") or "").strip()
        if not name or len(name) > 512:
            raise CaptureAdapterError("attachment name is required and bounded")
        byte_size = value.get("byte_size")
        if byte_size is not None and (not isinstance(byte_size, int) or byte_size < 0):
            raise CaptureAdapterError("attachment byte_size must be non-negative")
        content_hash = str(value.get("content_hash") or "").lower().strip()
        if content_hash and (len(content_hash) != 64 or not re.fullmatch(r"[0-9a-f]{64}", content_hash)):
            raise CaptureAdapterError("attachment content_hash must be SHA-256")
        access_state = str(value.get("access_state") or "available").strip().lower()
        if access_state not in {"available", "unavailable", "missing"}:
            raise CaptureAdapterError("attachment access_state is invalid")
        extraction_state = str(value.get("extraction_state") or "").strip()
        if not extraction_state:
            extraction_state = "extraction_unavailable" if access_state != "available" else "not_requested"
        mime_type = str(value.get("mime_type") or "application/octet-stream").strip().lower()
        if len(mime_type) > 255 or not _MIME_TYPE.fullmatch(mime_type):
            raise CaptureAdapterError("attachment mime_type is invalid")
        origin = CaptureAdapter._safe_reference(
            str(value.get("origin") or ""), field="attachment origin", required=False
        )
        return redact_secrets(
            {
                "attachment_id": str(value.get("attachment_id") or "").strip(),
                "name": name,
                "mime_type": mime_type,
                "byte_size": byte_size,
                "content_hash": content_hash,
                "origin": origin,
                "revision": str(value.get("revision") or "").strip(),
                "access_state": access_state,
                "extraction_state": extraction_state,
                "error": str(value.get("error") or "").strip(),
            }
        )

    @staticmethod
    def _annotation(value: str | Mapping[str, Any]) -> dict[str, str]:
        raw_text = value.get("text") if isinstance(value, Mapping) else value
        text = "" if raw_text is None else str(raw_text).strip()
        if not text or len(text) > 10_000:
            raise CaptureAdapterError("annotation text is required and bounded")
        return {"text": redact_secrets(text), "classification": "curated_opinion"}

    @staticmethod
    def _bounded_metadata(value: dict[str, Any]) -> None:
        try:
            size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise CaptureAdapterError("metadata must be JSON serializable") from exc
        if size > _MAX_METADATA_BYTES:
            raise CaptureAdapterError(f"metadata exceeds {_MAX_METADATA_BYTES} bytes")
