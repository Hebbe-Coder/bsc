from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.api import knowledge_intelligence_api
from app.core.config import settings
from app.main import app
from app.middleware import auth
from app.knowledge.information_intelligence import InformationIntelligenceService
from app.knowledge.information_intelligence_contracts import SignalBatch, SignalItem
from app.knowledge.wiki_repository import WikiRepository


def test_project_reader_can_read_daily_brief_without_cross_project_or_raw_body_access(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "information-operations-api.db"))
    service = InformationIntelligenceService(repository)
    registry = service.register_source(
        {
            "project_id": "project-a",
            "name": "Engineering RSS",
            "connector_type": "rss",
            "feed_url": "https://example.com/engineering.xml",
        }
    )
    service.ingest(
        SignalBatch(
            project_id="project-a",
            batch_id="operations-batch",
            execution_id="operations-execution",
            connector_type="rss",
            items=[
                SignalItem(
                    registry_id=registry["id"],
                    external_id="operations-item",
                    title="Governed brief item",
                    url="https://example.com/operations-item",
                    raw_content="Original body must stay outside the brief.",
                )
            ],
        )
    )
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    monkeypatch.setattr(
        auth,
        "resolve_knowledge_auth",
        lambda key, repo=None: ("project_reader", "project-a") if key == "reader-key" else None,
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_ENABLED", True, raising=False)
    app.dependency_overrides[knowledge_intelligence_api.get_intelligence_repository] = lambda: repository
    client = TestClient(app)
    try:
        response = client.get(
            f"/knowledge/intelligence/projects/project-a/daily-brief?day={day}",
            headers={"Authorization": "Bearer reader-key"},
        )
        cross_project = client.get(
            f"/knowledge/intelligence/projects/project-b/daily-brief?day={day}",
            headers={"Authorization": "Bearer reader-key"},
        )

        assert response.status_code == 200, response.text
        brief = response.json()["data"]
        assert brief["state"] == "available"
        assert brief["summary"]["captured"] == 1
        assert brief["lineage"]["receipt_ids"]
        assert "Original body must stay outside the brief." not in response.text
        assert cross_project.status_code == 403
    finally:
        app.dependency_overrides.clear()
        repository.close()
