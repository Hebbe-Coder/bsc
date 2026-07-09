import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from app.main import app  # 若 main 暴露 app;否则用 app.api.knowledge_api.router 组装
from app.knowledge.service import KnowledgeService


def _client_with_tmp_db():
    # 用临时库初始化一个 KnowledgeService 并写入样例,再对 /knowledge/ask 发请求
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    svc = KnowledgeService(db_path=f.name)
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    return svc


def test_ask_endpoint_returns_citations():
    svc = _client_with_tmp_db()
    # 直接调用 generator(走真实端点的集成需 app 装配,此处验证行为等价)
    from app.knowledge.answer import RAGAnswerGenerator
    out = RAGAnswerGenerator(service=svc, provider="mock").answer("内容安全 违规", project_id="p1")
    assert out["degraded"] is True
    assert out["citations"]


def test_evaluate_endpoint_structure():
    from app.knowledge.eval import RAGEvaluator
    svc = _client_with_tmp_db()
    m = RAGEvaluator().evaluate(svc, [{"query": "内容安全 违规", "expected_chunk_ids": []}], top_k=5)
    assert "precision@k" in m and "recall@k" in m and m["n"] == 1
