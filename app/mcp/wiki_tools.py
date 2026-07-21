"""Project-scoped, filesystem-safe MCP read tools for the LLM Wiki."""

from __future__ import annotations

from typing import Any

from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_repository import WikiRepository


def wiki_guide(project_id: str) -> dict:
    _require_project(project_id)
    return {
        "project_id": project_id,
        "workflow": ["capture immutable evidence", "review eligibility", "compile a draft", "lint and evaluate", "publish through a proposal gate"],
        "safety": "MCP tools cannot access arbitrary Vault paths or bypass the proposal gate.",
    }


def wiki_search(project_id: str, query: str = "") -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        sources = repo.list_sources(project_id)
        needle = query.strip().lower()
        matched = [source for source in sources if not needle or needle in source["origin"].lower() or needle in str(source["metadata"]).lower()]
        return {"project_id": project_id, "sources": [_source_view(source) for source in matched], "count": len(matched)}
    finally:
        repo.close()


def wiki_graph(project_id: str) -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        edges = repo.list_graph_edges(project_id)
        return {"project_id": project_id, "edges": edges, "count": len(edges)}
    finally:
        repo.close()


def wiki_read(project_id: str, page_id: str) -> dict:
    """Read one published Wiki revision and its citation metadata, scoped to a project."""
    _require_project(project_id)
    if not page_id or not page_id.strip():
        raise ValueError("page_id is required")
    repo = WikiRepository()
    try:
        page = repo.get_page(project_id, page_id)
        content = repo.get_page_content(project_id, page_id) if page else None
        if not page or not content:
            raise ValueError("published Wiki page not found")
        return {
            "project_id": project_id,
            "page": page,
            "content": content["content"],
            "citations": repo.list_citations(project_id, page_id),
            "revisions": repo.list_page_revisions(project_id, page_id),
        }
    finally:
        repo.close()


def wiki_propose_update(
    project_id: str, operations: list[dict[str, Any]], source_ids: list[str] | None = None, rationale: str = ""
) -> dict:
    """Create a reviewable manual proposal; it cannot write a Vault."""
    _require_project(project_id)
    repo = WikiRepository()
    try:
        proposal = WikiCommandService(repo).create_proposal(
            {
                "project_id": project_id,
                "operations": operations,
                "source_ids": source_ids or [],
                "rationale": rationale,
            },
            actor_id="mcp",
        )
        return {"project_id": project_id, "proposal": proposal}
    finally:
        repo.close()


def wiki_lint(project_id: str, proposal_id: str) -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        return WikiCommandService(repo).lint_proposal(project_id=project_id, proposal_id=proposal_id)
    finally:
        repo.close()


def wiki_apply_update(project_id: str, proposal_id: str) -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        return WikiCommandService(repo).publish_proposal(project_id=project_id, proposal_id=proposal_id)
    finally:
        repo.close()


def wiki_distill(project_id: str) -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        return WikiCommandService(repo).start_run(project_id=project_id, job_type="weekly_distillation", trigger="mcp")
    finally:
        repo.close()


def wiki_schedule(project_id: str, job_type: str, cron: str, timezone: str = "Asia/Shanghai") -> dict:
    _require_project(project_id)
    repo = WikiRepository()
    try:
        return WikiCommandService(repo).configure_schedule(
            project_id=project_id, job_type=job_type, cron=cron, timezone_name=timezone
        )
    finally:
        repo.close()


def _require_project(project_id: str) -> None:
    if not project_id or not project_id.strip():
        raise ValueError("project_id is required")


def _source_view(source: dict) -> dict:
    return {key: source[key] for key in ("id", "project_id", "source_type", "origin", "content_hash", "trust_level", "status", "metadata", "captured_at")}
