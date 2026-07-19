import sys
import os
import tempfile
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.service import KnowledgeService
from app.knowledge.eval import RAGEvaluator
from app.core.config import settings


@pytest.fixture
def svc_and_gold():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    svc = KnowledgeService(db_path=f)
    svc.ingest_text("内容安全 平台 过滤 违规 信息 审核", source="p1.txt", doc_format="txt")
    svc.ingest_text("咖啡 烘焙 风味 产地", source="p2.txt", doc_format="txt")
    yield svc, f, [{"query": "内容安全 违规", "expected_chunk_ids": []}]
    try:
        os.remove(f)
    except OSError:
        pass


def test_compare_before_after_structure(svc_and_gold, monkeypatch):
    svc, _, gold = svc_and_gold
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    rep = RAGEvaluator().compare_before_after(svc, gold, top_k=3)
    assert "before" in rep and "after" in rep
    assert "precision@k" in rep["before"] and "precision@k" in rep["after"]
    assert isinstance(rep["rerank_not_worse"], bool)
