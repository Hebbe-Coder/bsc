from __future__ import annotations

import hashlib
import hmac
import json
import asyncio

import httpx
from fastapi import HTTPException
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


def test_project_ingress_key_can_read_only_its_enabled_feed_manifest(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-manifest-api.db"))
    service = InformationIntelligenceService(repository)
    rss = service.register_source(
        {
            "project_id": "project-a",
            "name": "Engineering RSS",
            "connector_type": "rss",
            "feed_url": "https://example.com/feed.xml",
        }
    )
    service.register_source(
        {
            "project_id": "project-a",
            "name": "Disabled RSS",
            "connector_type": "rss",
            "feed_url": "https://example.com/disabled.xml",
            "enabled": False,
        }
    )
    service.register_source(
        {
            "project_id": "project-b",
            "name": "Other project RSS",
            "connector_type": "rss",
            "feed_url": "https://example.com/other.xml",
        }
    )
    monkeypatch.setattr(
        auth,
        "resolve_knowledge_auth",
        lambda key, repo=None: ("project_ingress", "project-a") if key == "ingress-key" else None,
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_ENABLED", True, raising=False)
    app.dependency_overrides[knowledge_intelligence_api.get_intelligence_repository] = lambda: repository
    client = TestClient(app)
    try:
        manifest = client.get(
            "/knowledge/intelligence/n8n/source-manifest?connector_type=rss",
            headers={"Authorization": "Bearer ingress-key"},
        )
        invalid = client.get(
            "/knowledge/intelligence/n8n/source-manifest?connector_type=reddit",
            headers={"Authorization": "Bearer ingress-key"},
        )
        overview = client.get("/knowledge/intelligence/projects/project-a", headers={"Authorization": "Bearer ingress-key"})

        assert manifest.status_code == 200, manifest.text
        assert manifest.json()["data"] == {
            "project_id": "project-a",
            "connector_type": "rss",
            "state": "ready",
            "sources": [
                {
                    "id": rss["id"],
                    "name": "Engineering RSS",
                    "connector_type": "rss",
                    "feed_url": "https://example.com/feed.xml",
                    "channel_id": "",
                    "topics": [],
                    "languages": [],
                    "freshness_hours": 168,
                    "retention_days": 90,
                    "authority_tier": "untrusted",
                }
            ],
        }
        assert invalid.status_code == 422
        assert overview.status_code == 403
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


def test_project_writer_can_request_only_its_configured_signed_n8n_manual_run(monkeypatch):
    calls: list[str] = []

    async def dispatch(project_id: str, _repository: WikiRepository) -> dict:
        calls.append(project_id)
        return {
            "project_id": project_id,
            "trigger": "n8n_signed_manual_webhook",
            "request_id": "request-1",
            "requested_at": "2026-07-31T00:00:00+00:00",
            "state": "completed",
            "batch_count": 1,
            "receipt_count": 2,
            "batches": [{"batch_id": "rss-1", "receipt_count": 2, "replayed": False, "status": "completed"}],
        }

    monkeypatch.setattr(
        auth,
        "resolve_knowledge_auth",
        lambda key, repo=None: ("project_admin", "project-a") if key == "writer-key" else ("project_reader", "project-a") if key == "reader-key" else None,
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID", "project-a", raising=False)
    monkeypatch.setattr(knowledge_intelligence_api, "_dispatch_n8n_manual_run", dispatch)
    client = TestClient(app)
    try:
        accepted = client.post("/knowledge/intelligence/projects/project-a/manual-runs", headers={"Authorization": "Bearer writer-key"})
        reader = client.post("/knowledge/intelligence/projects/project-a/manual-runs", headers={"Authorization": "Bearer reader-key"})
        cross_project = client.post("/knowledge/intelligence/projects/project-b/manual-runs", headers={"Authorization": "Bearer writer-key"})

        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["data"]["receipt_count"] == 2
        assert calls == ["project-a"]
        assert reader.status_code == 403
        assert cross_project.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_manual_n8n_dispatch_signs_a_fresh_project_payload_and_redacts_untrusted_response(tmp_path, monkeypatch):
    calls: list[dict] = []
    repository = WikiRepository(db_path=str(tmp_path / "manual-run-receipts.db"))

    class StubResponse:
        content = b"response"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return [{
                "batch_id": "rss-batch-1",
                "receipt_count": 3,
                "replayed": False,
                "status": "completed",
                "raw_content": "must never return through BSC",
            }]

    class StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url: str, *, headers: dict[str, str], content: bytes):
            calls.append({"url": url, "headers": headers, "content": content})
            return StubResponse()

    repository.create_signal_batch(
        project_id="project-a",
        batch_id="rss-batch-1",
        execution_id="execution-1",
        schema_version="v1",
        connector_type="rss",
        workflow_id="workflow-1",
        collected_at="2026-07-31T00:00:00+00:00",
        payload_hash="a" * 64,
        run_id="run-1",
    )
    for item_key in ("0", "1", "2"):
        repository.create_signal_receipt(
            project_id="project-a",
            batch_id="rss-batch-1",
            item_key=item_key,
            registry_id="registry-1",
            external_id=f"entry-{item_key}",
            canonical_url=f"https://example.com/{item_key}",
            source_id="source-1",
            disposition="captured",
            reason="captured",
            metadata={},
        )
    repository.update_signal_batch_status("project-a", "rss-batch-1", "completed", output_refs={"receipt_count": 3})
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID", "project-a", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_URL", "http://n8n:5678/webhook/manual", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_TIMEOUT_SECONDS", 15, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET", "test-signing-secret", raising=False)
    monkeypatch.setattr(knowledge_intelligence_api.httpx, "AsyncClient", lambda timeout: StubClient())
    try:
        result = asyncio.run(knowledge_intelligence_api._dispatch_n8n_manual_run("project-a", repository))

        assert result["state"] == "completed"
        assert result["receipt_count"] == 3
        assert result["batches"] == [{"batch_id": "rss-batch-1", "receipt_count": 3, "replayed": False, "status": "completed"}]
        assert result["verification"] == {"state": "verified", "claimed_batch_count": 1, "verified_batch_count": 1, "pending_batch_ids": []}
        assert "raw_content" not in str(result)
        assert calls[0]["url"] == "http://n8n:5678/webhook/manual"
        payload = calls[0]["headers"]["X-BSC-Manual-Payload"]
        assert json.loads(payload)["project_id"] == "project-a"
        assert calls[0]["headers"]["X-BSC-Manual-Signature"] == hmac.new(
            b"test-signing-secret", payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert calls[0]["content"] == b"{}"
    finally:
        repository.close()


def test_manual_n8n_dispatch_does_not_claim_receipts_before_bsc_persists_them(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "manual-run-verification.db"))

    class StubResponse:
        content = b"response"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return [{"batch_id": "unverified-batch", "receipt_count": 2, "replayed": False, "status": "completed"}]

    class StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return StubResponse()

    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID", "project-a", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_URL", "http://n8n:5678/webhook/manual", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET", "test-signing-secret", raising=False)
    monkeypatch.setattr(knowledge_intelligence_api.httpx, "AsyncClient", lambda timeout: StubClient())
    try:
        result = asyncio.run(knowledge_intelligence_api._dispatch_n8n_manual_run("project-a", repository))

        assert result["state"] == "receipt_verification_pending"
        assert result["receipt_count"] == 0
        assert result["batches"] == []
        assert result["verification"] == {
            "state": "pending",
            "claimed_batch_count": 1,
            "verified_batch_count": 0,
            "pending_batch_ids": ["unverified-batch"],
        }
        assert "raw_content" not in str(result)
    finally:
        repository.close()


def test_manual_n8n_dispatch_persists_bounded_audit_runs_for_all_outcomes(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "manual-run-audit.db"))
    outcomes: list[object] = [
        [{"batch_id": "verified-batch", "receipt_count": 1, "status": "completed"}],
        [{"batch_id": "pending-batch", "receipt_count": 2, "status": "completed"}],
        httpx.HTTPError("n8n is unavailable"),
    ]

    class StubResponse:
        content = b"response"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    class StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return StubResponse(outcome)

    repository.create_signal_batch(
        project_id="project-a",
        batch_id="verified-batch",
        execution_id="execution-verified",
        schema_version="v1",
        connector_type="rss",
        workflow_id="workflow-verified",
        collected_at="2026-07-31T00:00:00+00:00",
        payload_hash="b" * 64,
        run_id="run-verified",
    )
    repository.create_signal_receipt(
        project_id="project-a",
        batch_id="verified-batch",
        item_key="0",
        registry_id="registry-verified",
        external_id="entry-verified",
        canonical_url="https://example.com/verified",
        source_id="source-verified",
        disposition="captured",
        reason="captured",
        metadata={},
    )
    repository.update_signal_batch_status(
        "project-a", "verified-batch", "completed", output_refs={"receipt_count": 1}
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID", "project-a", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_URL", "http://n8n:5678/webhook/manual", raising=False)
    monkeypatch.setattr(settings, "KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET", "test-signing-secret", raising=False)
    monkeypatch.setattr(knowledge_intelligence_api.httpx, "AsyncClient", lambda timeout: StubClient())
    try:
        completed = asyncio.run(knowledge_intelligence_api._dispatch_n8n_manual_run("project-a", repository))
        pending = asyncio.run(knowledge_intelligence_api._dispatch_n8n_manual_run("project-a", repository))
        try:
            asyncio.run(knowledge_intelligence_api._dispatch_n8n_manual_run("project-a", repository))
            raise AssertionError("dispatch failure should raise an HTTP error")
        except HTTPException as exc:
            assert exc.status_code == 502

        audit_runs = [
            run for run in repository.list_runs("project-a")
            if run["run_type"] == "information_manual_dispatch"
        ]
        assert len(audit_runs) == 3
        by_id = {run["id"]: run for run in audit_runs}
        completed_run = by_id[completed["run_id"]]
        pending_run = by_id[pending["run_id"]]
        failed_run = next(run for run in audit_runs if run["status"] == "failed")

        assert completed_run["status"] == "completed"
        assert completed_run["output_refs"]["verification_state"] == "completed"
        assert completed_run["output_refs"]["verified_batch_ids"] == ["verified-batch"]
        assert pending_run["status"] == "completed"
        assert pending_run["output_refs"]["verification_state"] == "receipt_verification_pending"
        assert pending_run["output_refs"]["pending_batch_ids"] == ["pending-batch"]
        assert failed_run["output_refs"]["verification_state"] == "failed"
        assert failed_run["error"] == "n8n manual webhook request failed"

        for run in audit_runs:
            serialized = json.dumps(run, sort_keys=True)
            assert "test-signing-secret" not in serialized
            assert "http://n8n:5678/webhook/manual" not in serialized
            assert "raw_content" not in serialized
            assert run["input_refs"]["trigger_kind"] == "n8n_signed_manual_webhook"
            assert run["input_refs"]["request_id"]
    finally:
        repository.close()
