"""Contracts for governed, project-scoped information discovery.

Discovery tools may rank material, but only BSC can record evidence, receipts,
and knowledge lifecycle state. These models deliberately keep discovery metrics
separate from source authority and evidence content.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid4().hex[:12]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SUPPORTED_CONNECTORS = frozenset({
    "rss",
    "youtube_channel_rss",
    "x",
    "reddit",
    "youtube_data",
    "tiktok",
})
AVAILABLE_CONNECTORS = frozenset({"rss", "youtube_channel_rss"})


class SourceRegistryEntry(IntelligenceModel):
    id: str = Field(default_factory=_id, min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    connector_type: str = Field(min_length=1, max_length=64)
    feed_url: str = Field(min_length=1, max_length=2_048)
    channel_id: str = Field(default="", max_length=256)
    topics: list[str] = Field(default_factory=list, max_length=32)
    languages: list[str] = Field(default_factory=list, max_length=16)
    freshness_hours: int = Field(default=168, ge=1, le=8_760)
    retention_days: int = Field(default=90, ge=1, le=3_650)
    authority_tier: Literal["primary", "trusted", "community", "untrusted"] = "untrusted"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("connector_type")
    @classmethod
    def validate_connector(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_CONNECTORS:
            raise ValueError("connector_type is not supported")
        return normalized

    @field_validator("feed_url")
    @classmethod
    def validate_feed_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("feed_url must be an HTTP(S) URL")
        return normalized


class SignalDerivative(IntelligenceModel):
    kind: Literal["translation", "summary", "classification"]
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(default="", max_length=128)
    revision: str = Field(default="", max_length=128)
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalItem(IntelligenceModel):
    registry_id: str = Field(min_length=1, max_length=128)
    external_id: str = Field(default="", max_length=512)
    title: str = Field(min_length=1, max_length=2_000)
    url: str = Field(min_length=1, max_length=2_048)
    raw_content: str = Field(default="", max_length=2_000_000)
    raw_content_hash: str = Field(default="", max_length=64)
    published_at: str = Field(default="", max_length=64)
    language: str = Field(default="", max_length=32)
    lead_only: bool = False
    discovery_metrics: dict[str, float | int | str] = Field(default_factory=dict)
    derivatives: list[SignalDerivative] = Field(default_factory=list, max_length=8)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("url must be an HTTP(S) URL")
        return normalized

    @field_validator("raw_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and (len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized)):
            raise ValueError("raw_content_hash must be a SHA-256 hexadecimal digest")
        return normalized

    @model_validator(mode="after")
    def validate_evidence_mode(self) -> "SignalItem":
        if self.lead_only and self.raw_content:
            raise ValueError("lead_only items must not claim raw evidence")
        if self.lead_only and self.derivatives:
            raise ValueError("lead_only items must not include derivatives")
        if not self.lead_only and not self.raw_content:
            raise ValueError("raw_content is required unless lead_only is true")
        if self.raw_content_hash and self.raw_content_hash != _sha256(self.raw_content):
            raise ValueError("raw_content_hash does not match raw_content")
        return self


class SignalBatch(IntelligenceModel):
    schema_version: Literal["v1"] = "v1"
    project_id: str = Field(min_length=1, max_length=128)
    batch_id: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=256)
    connector_type: str = Field(min_length=1, max_length=64)
    workflow_id: str = Field(default="", max_length=256)
    collected_at: str = Field(default="", max_length=64)
    items: list[SignalItem] = Field(min_length=1, max_length=100)

    @field_validator("connector_type")
    @classmethod
    def validate_connector(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_CONNECTORS:
            raise ValueError("connector_type is not supported")
        return normalized

    def payload_hash(self) -> str:
        return _sha256(self.model_dump_json(exclude_none=True))


def connector_availability(connector_type: str) -> tuple[str, str]:
    if connector_type in AVAILABLE_CONNECTORS:
        return "available", ""
    return "unavailable", "credential_or_terms_required"
