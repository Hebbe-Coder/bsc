"""Read-only MCP views over the governed information-intelligence ledger."""

from __future__ import annotations

from app.knowledge.information_intelligence import InformationIntelligenceService
from app.knowledge.wiki_repository import WikiRepository


def overview(project_id: str) -> dict:
    repository = WikiRepository()
    try:
        return InformationIntelligenceService(repository).overview(project_id)
    finally:
        repository.close()


def receipts(project_id: str, limit: int = 100) -> dict:
    repository = WikiRepository()
    try:
        return {
            "project_id": project_id,
            "receipts": InformationIntelligenceService(repository).list_receipts(project_id, limit=limit),
        }
    finally:
        repository.close()
