import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService
from app.knowledge.eval import RAGEvaluator


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_eval_builtin_gold_metrics():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台 过滤 违规 信息 审核 流程", project_id="p1", title="安全制度")
    # 取该 doc 的某个 chunk_id 作为 expected
    rows = svc.repo._execute(
        "SELECT id FROM knowledge_chunks WHERE doc_id=?", (doc_id,)).fetchall()
    expected = [r["id"] for r in rows]
    gold = [{"query": "内容安全 违规", "expected_chunk_ids": expected}]
    ev = RAGEvaluator()
    m = ev.evaluate(svc, gold, top_k=5)
    assert m["n"] == 1
    assert m["precision@k"] >= 0.0
    assert m["recall@k"] == 1.0  # 期望块都在 top-k 内


def test_eval_empty_gold_raises():
    import pytest
    ev = RAGEvaluator()
    with pytest.raises(ValueError):
        ev.evaluate(_tmp_service(), [], top_k=5)


def test_load_gold_rejects_bad_structure():
    import pytest
    ev = RAGEvaluator()
    with pytest.raises(ValueError):
        ev.load_gold([{"expected_chunk_ids": ["x"]}])  # 缺 query


def test_eval_recall_zero_when_expected_missing():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核 流程", project_id="p1", title="安全制度")
    # 期望一个不存在的 chunk_id -> 检索非空但命中为 0
    gold = [{"query": "内容安全 违规", "expected_chunk_ids": ["nonexistent-id"]}]
    m = RAGEvaluator().evaluate(svc, gold, top_k=5)
    assert m["recall@k"] == 0.0
    assert m["precision@k"] == 0.0
