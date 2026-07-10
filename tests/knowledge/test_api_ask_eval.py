import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient
from app.knowledge.service import KnowledgeService
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service

# 仅供本测试使用的 admin Key;通过 monkeypatch 注入 settings,不依赖 .env 配置。
# 因 RateLimitMiddleware 以 `key_<api_key[:16]>` 为桶键,该唯一 Key 使本测试请求
# 拥有独立令牌桶,不会与全量测试套件中其他 HTTP 请求互相限流。
_TEST_API_KEY = "test-admin-key-0000000001"


# ---- 直调等价测试(不发动 HTTP,验证核心行为) ----

def _make_tmp_service():
    """用临时库初始化一个 KnowledgeService 并写入样例数据,返回 (svc, db_path)。"""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    svc = KnowledgeService(db_path=f.name)
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    return svc, f.name


def test_ask_endpoint_returns_citations():
    svc, _ = _make_tmp_service()
    from app.knowledge.answer import RAGAnswerGenerator
    out = RAGAnswerGenerator(service=svc, provider="mock").answer("内容安全 违规", project_id="p1")
    assert out["degraded"] is True
    assert out["citations"]


def test_evaluate_endpoint_structure():
    from app.knowledge.eval import RAGEvaluator
    svc, _ = _make_tmp_service()
    m = RAGEvaluator().evaluate(svc, [{"query": "内容安全 违规", "expected_chunk_ids": []}], top_k=5)
    assert "precision@k" in m and "recall@k" in m and m["n"] == 1


# ---- 真实 HTTP 集成测试(dependency_overrides 注入临时库 + 强制鉴权头) ----

def _http_client_with_tmp_db():
    svc, path = _make_tmp_service()
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    return path


def test_ask_endpoint_http_returns_citations(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", _TEST_API_KEY)
    monkeypatch.setattr(settings, "RAG_LLM_PROVIDER", "mock")
    db_path = _http_client_with_tmp_db()
    try:
        client = TestClient(app)
        resp = client.post(
            "/knowledge/ask",
            json={"question": "内容安全 违规", "project_id": "p1"},
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["degraded"] is True  # mock provider 降级
        assert body["data"]["citations"]
    finally:
        app.dependency_overrides.pop(get_knowledge_service, None)
        try:
            os.remove(db_path)
        except OSError:
            pass


def test_evaluate_endpoint_http_returns_metrics(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", _TEST_API_KEY)
    db_path = _http_client_with_tmp_db()
    try:
        client = TestClient(app)
        resp = client.post(
            "/knowledge/evaluate",
            json={"gold": [{"query": "内容安全 违规", "expected_chunk_ids": []}], "top_k": 5, "project_id": "p1"},
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "precision@k" in body["data"]
        assert "recall@k" in body["data"]
        assert body["data"]["n"] == 1
    finally:
        app.dependency_overrides.pop(get_knowledge_service, None)
        try:
            os.remove(db_path)
        except OSError:
            pass
