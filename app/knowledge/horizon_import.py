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

    _TASK_FAMILY_TERMS = {
        "context_mapping": (
            "agent", "mcp", "model context protocol", "knowledge", "obsidian", "rag",
            "retrieval", "context engineering", "context management",
        ),
        "operating_cadence": ("workflow", "automation", "orchestration", "scheduler"),
        "risk_control": ("prompt injection", "security", "vulnerability", "red team", "safety"),
        "evidence_validation": ("benchmark", "evaluation", "eval", "verification"),
        "decision_design": ("decision", "roadmap", "strategy"),
        "conversion_experiment": ("conversion", "growth experiment", "a/b test", "ab test"),
    }

    def __init__(self, repository: WikiRepository, *, min_score: float = 7.0) -> None:
        self.capture_service = SourceCaptureService(repository)
        self.min_score = min_score

    def import_items(
        self,
        *,
        project_id: str,
        run_id: str,
        stage: str,
        items: list[dict[str, Any]],
        capture_run_id: str = "",
    ) -> dict[str, int]:
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
                        "title": item.title,
                        "published_at": item.published_at,
                        "ai_score": item.ai_score,
                        "ai_reason": item.ai_reason,
                        "ai_summary": item.ai_summary,
                        "ai_tags": item.ai_tags,
                        "task_families": self._task_families(item),
                        "admission_gate": "project_triage",
                        "evidence_role": "discovery_signal",
                        "primary_capture_required": True,
                        "horizon_metadata": item.metadata,
                    },
                    capture_run_id=capture_run_id,
                )
            )
            report["created" if result.created else "duplicates"] += 1
        return report

    @classmethod
    def _task_families(cls, item: HorizonExportItem) -> list[str]:
        """Classify only explicit Horizon metadata for bounded DBOS reuse."""
        tags = item.metadata.get("tags") if isinstance(item.metadata.get("tags"), list) else []
        searchable = " ".join(
            str(value).strip().lower()
            for value in (item.title, item.ai_reason, item.ai_summary, *item.ai_tags, *tags)
            if str(value).strip()
        )
        return [
            family
            for family, terms in cls._TASK_FAMILY_TERMS.items()
            if any(term in searchable for term in terms)
        ]
