"""Deterministic, project-scoped health metrics for the published Wiki."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.knowledge.wiki_repository import WikiRepository


class KnowledgeHealthService:
    """Calculate inspectable health facts without inventing unavailable measurements."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def snapshot(self, *, project_id: str, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        pages = self.repository.list_pages(project_id)
        sources = self.repository.list_sources(project_id)
        all_citations = self.repository.list_citations(project_id, include_stale=True)
        citations = [citation for citation in all_citations if citation["status"] == "active"]
        proposals = self.repository.list_proposals(project_id)
        edges = self.repository.list_graph_edges(project_id, edge_type="wiki_links_to")
        page_ids = {page["id"] for page in pages}
        source_ids = {source["id"] for source in sources}
        cited_page_ids = {citation["wiki_page_id"] for citation in citations}
        linked_page_ids = {edge["to_id"] for edge in edges if edge["to_id"] in page_ids}
        eligible_sources = {source["id"] for source in sources if source["status"] == "eligible"}
        cited_sources = {citation["source_id"] for citation in citations}
        stale_pages = [page["id"] for page in pages if self._is_stale(page.get("updated_at", ""), current)]
        pending = [proposal["id"] for proposal in proposals if proposal["status"] in {"draft", "validating", "approved"}]
        uncited_pages = page_ids - cited_page_ids
        eval_runs = self.repository.list_eval_runs(project_id, limit=20)
        latest_eval = eval_runs[0] if eval_runs else None
        contradiction_pairs: set[tuple[str, str]] = set()
        for source in sources:
            targets = source.get("metadata", {}).get("contradicts_source_ids", [])
            if not isinstance(targets, list):
                continue
            for target in targets:
                if isinstance(target, str) and target in source_ids and target != source["id"]:
                    contradiction_pairs.add(tuple(sorted((source["id"], target))))

        return {
            "project_id": project_id,
            "status": "available",
            "pages": len(pages),
            "sources": len(sources),
            "citations": len(citations),
            "citation_coverage": len(page_ids - uncited_pages) / len(page_ids) if page_ids else None,
            "orphan_page_ids": sorted(page_ids - linked_page_ids),
            "uncited_page_ids": sorted(uncited_pages),
            "dangling_citation_count": sum(1 for citation in citations if citation["source_id"] not in source_ids),
            "stale_citation_count": sum(1 for citation in all_citations if citation["status"] == "stale"),
            "stale_page_ids": sorted(stale_pages),
            "uncited_eligible_source_ids": sorted(eligible_sources - cited_sources),
            "pending_proposal_ids": sorted(pending),
            "contradiction_count": len(contradiction_pairs),
            "contradiction_pairs": [list(pair) for pair in sorted(contradiction_pairs)],
            "evaluation": {
                "status": latest_eval["status"] if latest_eval else "unavailable",
                "latest_score": latest_eval["summary"].get("score") if latest_eval else None,
                "runs": len(eval_runs),
                "reason": "" if latest_eval else "no persisted evaluation trend yet",
            },
        }

    def trend(self, *, project_id: str) -> dict[str, Any]:
        """Expose persisted observations for charts without backfilling synthetic history."""
        source_counts: dict[str, int] = {}
        for source in self.repository.list_sources(project_id):
            day = str(source.get("captured_at") or "")[:10]
            if day:
                source_counts[day] = source_counts.get(day, 0) + 1
        proposal_counts: dict[str, dict[str, int]] = {}
        for proposal in self.repository.list_proposals(project_id, limit=500):
            day = str(proposal.get("updated_at") or proposal.get("created_at") or "")[:10]
            if not day:
                continue
            statuses = proposal_counts.setdefault(day, {})
            status = str(proposal.get("status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
        evaluations = [
            {
                "at": item.get("created_at", ""),
                "score": item.get("summary", {}).get("score"),
                "status": item.get("status", ""),
            }
            for item in reversed(self.repository.list_eval_runs(project_id, limit=100))
        ]
        return {
            "source_throughput": [{"date": day, "count": count} for day, count in sorted(source_counts.items())],
            "proposal_outcomes": [{"date": day, "statuses": statuses} for day, statuses in sorted(proposal_counts.items())],
            "evaluations": evaluations,
            "current": self.snapshot(project_id=project_id),
        }

    @staticmethod
    def _is_stale(value: str, now: datetime) -> bool:
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed < now - timedelta(days=90)
