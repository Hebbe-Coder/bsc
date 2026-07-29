from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.api import knowledge_intelligence_api
from app.core.config import settings
from app.main import app
from app.middleware import auth
from app.knowledge.information_intelligence import InformationIntelligenceService
from app.knowledge.wiki_repository import WikiRepository


def _signed_headers(body: bytes) -> dict[str, str]:
    return {
        "Authorization": "Bearer ingress-key",
        "Content-Type": "application/json",
        "X-BSC-Signal-Signature": hmac.new(
            b"test-signing-secret", body, hashlib.sha256
        ).hexdigest(),
    }


def test_project_ingress_key_can_submit_signed_batch_but_cannot_read_workspace(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-api.db"))
    service = InformationIntelligenceService(repository)
    registry = service.register_source(
        {
            "project_id": "project-a",
            "name": "Engineering RSS",
            "connector_type": "rss",
            "feed_url": "https://example.com/feed.xml",
        }
    )
    monkeypatch.setattr(
        auth,
        "resolve_knowledge_auth",
        lambda key, repo=None: ("project_ingress", "project-a") if key == "ingress-key" else None,
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET", "test-signing-secret", raising=False)
    app.dependency_overrides[knowledge_intelligence_api.get_intelligence_repository] = lambda: repository
    client = TestClient(app)
    try:
        body = json.dumps(
            {
                "schema_version": "v1",
                "project_id": "project-a",
                "batch_id": "batch-api-1",
                "execution_id": "execution-api-1",
                "connector_type": "rss",
                "items": [
                    {
                        "registry_id": registry["id"],
                        "external_id": "item-api-1",
                        "title": "API evidence",
                        "url": "https://example.com/api?utm_campaign=test",
                        "raw_content": "Original RSS evidence.",
                    }
                ],
            },
            separators=(",", ":"),
        ).encode("utf-8")

        accepted = client.post("/knowledge/intelligence/signal-batches", content=body, headers=_signed_headers(body))
        replay = client.post("/knowledge/intelligence/signal-batches", content=body, headers=_signed_headers(body))
        wrong_project = client.post(
            "/knowledge/intelligence/signal-batches",
            content=body.replace(b"project-a", b"project-b"),
            headers=_signed_headers(body.replace(b"project-a", b"project-b")),
        )
        workspace = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer ingress-key"})

        assert accepted.status_code == 200
        assert accepted.json()["data"]["replayed"] is False
        assert replay.status_code == 200
        assert replay.json()["data"]["replayed"] is True
        assert wrong_project.status_code == 403
        assert workspace.status_code == 403
    finally:
        app.dependency_overrides.clear()
        repository.close()


def test_unsigned_or_malformed_batches_are_never_accepted(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-api.db"))
    monkeypatch.setattr(
        auth,
        "resolve_knowledge_auth",
        lambda key, repo=None: ("project_ingress", "project-a") if key == "ingress-key" else None,
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET", "test-signing-secret", raising=False)
    app.dependency_overrides[knowledge_intelligence_api.get_intelligence_repository] = lambda: repository
    client = TestClient(app)
    try:
        unsigned = client.post(
            "/knowledge/intelligence/signal-batches",
            content=b"{}",
            headers={"Authorization": "Bearer ingress-key", "Content-Type": "application/json"},
        )
        malformed = client.post(
            "/knowledge/intelligence/signal-batches",
            content=b"not-json",
            headers=_signed_headers(b"not-json"),
        )

        assert unsigned.status_code == 401
        assert malformed.status_code == 422
    finally:
        app.dependency_overrides.clear()
        repository.close()
