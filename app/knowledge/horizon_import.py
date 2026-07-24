"""Import Horizon's filtered intelligence as immutable, reviewable BSC evidence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class HorizonExportItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    content: str = ""
    published_at: str = ""
    ai_score: float | None = None
    ai_reason: str = ""
    ai_summary: str = ""
    ai_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HorizonImportService:
    """Keep Horizon's selection signal separate from BSC's evidence/publish authority."""

    def __init__(self, repository: WikiRepository, *, min_score: float = 7.0) -> None:
        self.capture_service = SourceCaptureService(repository)
        self.min_score = min_score

    def import_items(self, *, project_id: str, run_id: str, stage: str, items: list[dict[str, Any]]) -> dict[str, int]:
        if stage not in {"filtered", "enriched"}:
            raise ValueError("Horizon import accepts filtered or enriched stage items only")
        report = {"accepted": 0, "created": 0, "duplicates": 0, "rejected": 0}
        for raw_item in items:
            item = HorizonExportItem.model_validate(raw_item)
            if item.ai_score is None or item.ai_score < self.min_score or not item.content.strip():
                report["rejected"] += 1
                continue
            report["accepted"] += 1
            content = "\n".join(
                part for part in (
                    f"# {item.title}", item.content.strip(),
                    f"Horizon summary: {item.ai_summary}" if item.ai_summary else "",
                    f"Horizon rationale: {item.ai_reason}" if item.ai_reason else "",
                    f"URL: {item.url}",
                ) if part
            )
            result = self.capture_service.capture(
                CapturedSourceInput(
                    project_id=project_id,
                    source_type="horizon_signal",
                    origin=str(item.url),
                    raw_content=content,
                    trust_level="reviewed",
                    metadata={
                        "horizon_item_id": item.id,
                        "horizon_run_id": run_id,
                        "horizon_stage": stage,
                        "source_type": item.source_type,
                        "published_at": item.published_at,
                        "ai_score": item.ai_score,
                        "ai_reason": item.ai_reason,
                        "ai_summary": item.ai_summary,
                        "ai_tags": item.ai_tags,
                        "admission_gate": "project_triage",
                        "horizon_metadata": item.metadata,
                    },
                )
            )
            report["created" if result.created else "duplicates"] += 1
        return report
