"""Read-only A/B/C/D context and advisory DBOS feedback memory."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from app.artifacts import ExecutionResultArtifact, MemoryArtifact, MissionArtifact
from app.knowledge.method_routing import MethodRouter


_TASK_FAMILY_ALIASES = {
    "context mapping": "context_mapping",
    "business understanding": "context_mapping",
    "assumption validation": "assumption_validation",
    "evidence validation": "evidence_validation",
    "evidence review": "evidence_validation",
    "risk control": "risk_control",
    "risk analysis": "risk_control",
    "decision design": "decision_design",
    "decision support": "decision_design",
    "conversion experiment": "conversion_experiment",
    "conversion optimization": "conversion_experiment",
    "strategy design": "strategy_design",
    "resource guardrail": "resource_guardrail",
    "coverage review": "coverage_review",
    "gap resolution": "gap_resolution",
    "operating cadence": "operating_cadence",
    "decision brief": "decision_brief",
}
_SAFE_TASK_METADATA_FIELDS = (
    "task_family",
    "task_families",
    "capability_family",
    "capability_families",
    "applicability",
    "tags",
    "ai_tags",
)
_PAGE_KIND_TASK_FAMILIES = {
    "concept": "context_mapping",
    "decision": "decision_design",
    "sop": "operating_cadence",
}
_SOP_CONTEXT_HEADERS = (
    "## [profile:",
    "## [rules:",
    "## [task:",
    "## [page:",
    "## [method:",
)
_SOP_CONTEXT_MAX_CHARACTERS = 8_000


class KnowledgeMemoryAdapter:
    """Projects governed knowledge metadata without reading source or output bodies."""

    def __init__(
        self,
        repository: Any | None = None,
        repository_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.repository = repository
        self.repository_factory = repository_factory

    def snapshot(self, project_id: str, *, task: str = "") -> dict[str, Any]:
        repository = self.repository
        owns_repository = False
        if repository is None and self.repository_factory is not None:
            try:
                repository = self.repository_factory()
                owns_repository = True
            except Exception:
                return self._unavailable("knowledge_repository_unavailable")
        if repository is None:
            return self._unavailable("knowledge_repository_not_configured")
        try:
            methods = self._methods(repository, project_id)
            outputs = self._status_records(repository, "list_outputs", project_id, ("accepted", "filed"), limit=100)
            pages = self._all_records(repository, "list_pages", project_id, ("published",))
            sources = self._status_records(repository, "list_sources", project_id, ("eligible", "processed"))
            planning_context = self._planning_context(repository, project_id, task)
        except Exception:
            return self._unavailable("knowledge_repository_unavailable")
        finally:
            if owns_repository:
                close = getattr(repository, "close", None)
                if callable(close):
                    close()
        return {
            "availability": "available",
            "method_ids": [item["id"] for item in methods],
            "methods": methods,
            "output_ids": [str(item.get("id") or "") for item in outputs if str(item.get("id") or "")],
            "page_ids": [str(item.get("id") or "") for item in pages if str(item.get("id") or "")],
            "source_ids": [str(item.get("id") or "") for item in sources if str(item.get("id") or "")],
            "signals": self._signals(methods=methods, sources=sources, pages=pages, outputs=outputs),
            # This bounded context stays in-process until an explicitly requested
            # adaptive compilation. Selection artifacts persist only metadata.
            "planning_context": planning_context,
        }

    @staticmethod
    def _planning_context(repository: Any, project_id: str, task: str) -> dict[str, Any]:
        if not task.strip():
            return {"availability": "unavailable", "reason": "task_unavailable", "context_pack_id": "", "refs": [], "rendered": ""}
        try:
            from app.core.config import settings
            from app.knowledge.growth_context import GrowthContextService

            pack = GrowthContextService(repository, settings.OBSIDIAN_VAULT_ROOT).build_context(
                project_id=project_id,
                task=task,
            )
            refs = list(dict.fromkeys([
                f"context-pack:{pack.revision}",
                *(f"page:{item}" for item in pack.page_ids),
                *(f"source:{item}" for item in pack.source_ids),
                *(f"method:{item}" for item in pack.method_revision_ids),
                *(f"output:{item}" for item in pack.output_ids),
            ]))
            return {
                "availability": "available",
                "context_pack_id": pack.revision,
                "refs": refs[:128],
                "rendered": KnowledgeMemoryAdapter._sop_planning_context(pack.rendered_sections),
            }
        except Exception:
            return {"availability": "unavailable", "reason": "planning_context_unavailable", "context_pack_id": "", "refs": [], "rendered": ""}

    @staticmethod
    def _sop_planning_context(sections: Iterable[str]) -> str:
        """Project published Wiki knowledge into a bounded SOP-only prompt context."""
        included: list[str] = []
        used = 0
        for section in sections:
            value = str(section or "").strip()
            if not value or not value.startswith(_SOP_CONTEXT_HEADERS):
                continue
            separator = 2 if included else 0
            if used + separator + len(value) > _SOP_CONTEXT_MAX_CHARACTERS:
                continue
            included.append(value)
            used += separator + len(value)
        return "\n\n".join(included)

    def matching_methods(self, context: dict[str, Any], task_family: str) -> list[dict[str, Any]]:
        methods = [item for item in context.get("methods") or [] if isinstance(item, dict)]
        decision = MethodRouter().select(methods, str(task_family or "").replace("_", " "))
        by_slug = {str(item.get("slug") or ""): item for item in methods}
        return [by_slug[match.slug] for match in decision.matches if match.slug in by_slug]

    def _methods(self, repository: Any, project_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for status in ("approved", "published"):
            records.extend(repository.list_methods(project_id, status=status, limit=100))
        seen: set[str] = set()
        values: list[dict[str, Any]] = []
        for item in records:
            identifier = str(item.get("id") or "")
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            revision_id = str(item.get("active_revision_id") or "")
            revision = repository.get_method_revision(project_id, revision_id) if revision_id else None
            values.append({
                "id": identifier,
                "name": str(item.get("name") or ""),
                "slug": str(item.get("slug") or ""),
                "applicability": [str(value) for value in item.get("applicability") or [] if str(value)],
                "exclusions": [str(value) for value in item.get("exclusions") or [] if str(value)],
                "manifest": dict((revision or {}).get("manifest") or {}),
                "status": str(item.get("status") or ""),
            })
        return values[:100]

    def _status_records(self, repository: Any, method_name: str, project_id: str, statuses: tuple[str, ...], *, limit: int | None = None) -> list[dict[str, Any]]:
        method = getattr(repository, method_name, None)
        if not callable(method):
            return []
        values: list[dict[str, Any]] = []
        for status in statuses:
            kwargs = {"status": status}
            if limit is not None:
                kwargs["limit"] = limit
            values.extend(method(project_id, **kwargs))
        return values[:100]

    def _all_records(self, repository: Any, method_name: str, project_id: str, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        method = getattr(repository, method_name, None)
        if not callable(method):
            return []
        values = method(project_id)
        allowed = set(statuses)
        return [item for item in values if str(item.get("status") or "") in allowed][:100]

    @classmethod
    def _signals(
        cls,
        *,
        methods: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return bounded reuse signals from governed metadata, never content bodies."""
        by_family: dict[str, dict[str, list[str]]] = {}

        def add(record: dict[str, Any], field: str, identifier: str, families: Iterable[str]) -> None:
            for family in families:
                if not identifier or not family:
                    continue
                bucket = by_family.setdefault(family, {
                    "source_ids": [], "page_ids": [], "output_ids": [], "method_ids": [],
                })
                bucket[field].append(identifier)

        for source in sources:
            if str(source.get("trust_level") or "") not in {"trusted", "reviewed"}:
                continue
            add(source, "source_ids", str(source.get("id") or ""), cls._task_families(source))
        for page in pages:
            families = set(cls._task_families(page))
            page_kind = str(page.get("page_kind") or "").strip().lower()
            if page_kind in _PAGE_KIND_TASK_FAMILIES:
                families.add(_PAGE_KIND_TASK_FAMILIES[page_kind])
            add(page, "page_ids", str(page.get("id") or ""), families)
        for output in outputs:
            add(output, "output_ids", str(output.get("id") or ""), cls._task_families(output))
        for method in methods:
            add(method, "method_ids", str(method.get("id") or ""), cls._task_families(method))

        normalized = {
            family: {
                field: sorted(set(values))[:100]
                for field, values in bucket.items()
            }
            for family, bucket in sorted(by_family.items())
        }
        return {
            "revision": "dbos-knowledge-signals-v1",
            "by_task_family": normalized,
            "eligible_source_count": sum(1 for item in sources if str(item.get("trust_level") or "") in {"trusted", "reviewed"}),
            "published_page_count": len(pages),
            "verified_output_count": len(outputs),
        }

    @classmethod
    def _task_families(cls, record: dict[str, Any]) -> list[str]:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        manifest = record.get("manifest") if isinstance(record.get("manifest"), dict) else {}
        values: list[Any] = []
        for field in _SAFE_TASK_METADATA_FIELDS:
            values.extend(cls._as_values(record.get(field)))
            values.extend(cls._as_values(metadata.get(field)))
            values.extend(cls._as_values(manifest.get(field)))
        return sorted({family for value in values if (family := cls._task_family(value))})

    @staticmethod
    def _as_values(value: Any) -> list[Any]:
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _task_family(value: Any) -> str:
        normalized = " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())
        return _TASK_FAMILY_ALIASES.get(normalized, "")

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {
            "availability": "unavailable",
            "reason": reason,
            "method_ids": [],
            "methods": [],
            "output_ids": [],
            "page_ids": [],
            "source_ids": [],
            "signals": {
                "revision": "dbos-knowledge-signals-v1",
                "by_task_family": {},
                "eligible_source_count": 0,
                "published_page_count": 0,
                "verified_output_count": 0,
            },
        }


class DBOSMemoryService:
    """Persists advisory feedback memory without mutating the knowledge loop."""

    def record_feedback(
        self,
        *,
        mission: MissionArtifact,
        execution: ExecutionResultArtifact,
        statement: str,
        feedback_kind: str,
    ) -> MemoryArtifact:
        if not statement.strip():
            raise ValueError("feedback statement is required")
        return MemoryArtifact(
            project_id=mission.project_id,
            label=f"{feedback_kind}: {mission.title}"[:140],
            memory_kind=feedback_kind,
            statement=statement.strip(),
            source_refs=[execution.artifact_id],
            applicability=[execution.capability_name] if execution.capability_name else [],
            governance_status="candidate",
            parent_ids=[execution.artifact_id],
            source_agent="dbos_feedback_memory",
            tags=["dbos", "feedback", "candidate_memory"],
        )
