"""Metadata-only projection of source bibliography into evidence references."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.knowledge.wiki_contracts import ReferenceLink
from app.knowledge.wiki_repository import WikiRepository


_TRACKING_QUERY_KEYS = frozenset({
    "dclid", "fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "ref", "ref_src",
})
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)
_CITEKEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:@+-]{0,127}$", re.IGNORECASE)


class SourceReferenceProjector:
    """Create idempotent bibliography links from bounded source metadata only.

    This component deliberately has no Vault path, body reader, network client,
    or mutation API for original evidence. It only reads the repository's
    narrow reference-candidate projection and writes ``ReferenceLink`` rows.
    """

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def project_source_id(self, project_id: str, source_id: str) -> dict[str, int]:
        source = self.repository.get_source_reference_candidate(project_id, source_id)
        if source is None:
            return {"created": 0, "existing": 0, "skipped": 0}
        return self._project(source)

    def backfill_project(self, project_id: str) -> dict[str, int]:
        total = {"examined": 0, "created": 0, "existing": 0, "skipped": 0}
        for source in self.repository.list_source_reference_candidates(project_id):
            total["examined"] += 1
            result = self._project(source)
            for field in ("created", "existing", "skipped"):
                total[field] += result[field]
        return total

    def _project(self, source: dict[str, Any]) -> dict[str, int]:
        project_id = str(source.get("project_id") or "")
        source_id = str(source.get("id") or "")
        if not project_id or not source_id:
            return {"created": 0, "existing": 0, "skipped": 0}

        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        candidates = (
            ("url", source.get("origin"), "declares_url", "source_origin"),
            ("url", metadata.get("canonical_url"), "declares_url", "source_metadata"),
            ("url", metadata.get("zotero_url"), "declares_url", "zotero_frontmatter"),
            ("doi", metadata.get("zotero_doi"), "declares_doi", "zotero_frontmatter"),
            ("citekey", metadata.get("zotero_citation_key"), "declares_citekey", "zotero_frontmatter"),
        )
        normalized: list[tuple[str, str, str, str]] = []
        skipped = 0
        for target_type, value, relation, anchor_type in candidates:
            if not str(value or "").strip():
                continue
            anchor = self._normalize(target_type, value)
            if not anchor:
                skipped += 1
                continue
            candidate = (target_type, anchor, relation, anchor_type)
            if candidate not in normalized:
                normalized.append(candidate)

        existing_identities = {
            self._identity(item)
            for item in self.repository.list_reference_links(project_id, source_id=source_id, limit=500)
        }
        result = {"created": 0, "existing": 0, "skipped": skipped}
        for target_type, anchor, relation, anchor_type in normalized:
            identity = (target_type, self._target_id(target_type, anchor), anchor_type, anchor, relation)
            if identity in existing_identities:
                result["existing"] += 1
                continue
            self.repository.create_reference_link(
                ReferenceLink(
                    project_id=project_id,
                    source_id=source_id,
                    target_type=target_type,
                    target_id=identity[1],
                    anchor_type=anchor_type,
                    anchor=anchor,
                    relation=relation,
                    metadata={"projector": "source_reference_metadata_v1"},
                )
            )
            existing_identities.add(identity)
            result["created"] += 1
        return result

    @staticmethod
    def _identity(reference: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(reference.get("target_type") or ""),
            str(reference.get("target_id") or ""),
            str(reference.get("anchor_type") or ""),
            str(reference.get("anchor") or ""),
            str(reference.get("relation") or ""),
        )

    @staticmethod
    def _target_id(target_type: str, anchor: str) -> str:
        digest = hashlib.sha256(f"{target_type}|{anchor}".encode("utf-8")).hexdigest()[:32]
        return f"{target_type}:{digest}"

    @staticmethod
    def _normalize(target_type: str, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw or len(raw) > 2_048 or any(character.isspace() for character in raw):
            return ""
        if target_type == "url":
            return SourceReferenceProjector._normalize_http_url(raw)
        if target_type == "doi":
            raw = raw.removeprefix("doi:").removeprefix("DOI:")
            return raw.lower() if _DOI_PATTERN.fullmatch(raw) else ""
        if target_type == "citekey":
            return raw if _CITEKEY_PATTERN.fullmatch(raw) else ""
        return ""

    @staticmethod
    def _normalize_http_url(value: str) -> str:
        try:
            parsed = urlsplit(value)
            scheme = parsed.scheme.lower()
            host = parsed.hostname
            if scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
                return ""
            port = parsed.port
        except ValueError:
            return ""

        normalized_host = host.lower()
        if ":" in normalized_host and not normalized_host.startswith("["):
            normalized_host = f"[{normalized_host}]"
        default_port = 80 if scheme == "http" else 443
        netloc = normalized_host if port in {None, default_port} else f"{normalized_host}:{port}"
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/") or "/"
        query = urlencode(sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
        ), doseq=True)
        return urlunsplit((scheme, netloc, path, query, ""))
