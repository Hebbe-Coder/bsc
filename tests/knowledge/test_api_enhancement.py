import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient
from app.knowledge.service import KnowledgeService
from app.main import app
from app.api.knowledge_api import get_knowledge_service
from app.core.config import settings


@pytest.fixture
def client_and_cleanup(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-admin-key-enh")
    monkeypatch.setattr(settings, "RAG_LLM_PROVIDER", "mock")
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    svc = KnowledgeService(db_path=tmp)
    # 预灌 b.txt（供 retrieve rerank 测试使用）；不预灌 a.txt，
    # 让 ingest 幂等测试中的 r1 成为首次入库(ingested)、r2 为重复(skipped)。
    svc.ingest_text("苹果 公司 股价 财报", source="b.txt", doc_format="txt")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-admin-key-enh"}
    yield client, headers, tmp
    app.dependency_overrides.pop(get_knowledge_service, None)
    try:
        os.remove(tmp)
    except OSError:
        pass


def test_ingest_idempotent_status(client_and_cleanup):
    client, headers, _ = client_and_cleanup
    r1 = client.post("/knowledge/ingest", data={"text": "苹果 水果 营养 健康", "source": "a.txt"}, headers=headers)
    r2 = client.post("/knowledge/ingest", data={"text": "苹果 水果 营养 健康", "source": "a.txt"}, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["docs"][0]["status"] == "ingested"
    assert r2.json()["data"]["docs"][0]["status"] == "skipped"


def test_retrieve_rerank_param(client_and_cleanup, monkeypatch):
    client, headers, _ = client_and_cleanup
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    resp = client.post("/knowledge/retrieve",
                       json={"query": "苹果 公司", "top_k": 2, "rerank": True},
                       headers=headers)
    assert resp.status_code == 200
    assert "rerank_score" in resp.json()["data"]["results"][0]
