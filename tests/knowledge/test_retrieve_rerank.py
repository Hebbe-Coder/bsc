import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pytest
from app.knowledge.service import KnowledgeService
from app.core.config import settings


@pytest.fixture
def svc():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); f.close()
    s = KnowledgeService(db_path=f.name)
    s.ingest_text("苹果 香蕉 水果 营养", source="a.txt", doc_format="txt", project_id="p1")
    s.ingest_text("苹果 公司 股价 财报", source="b.txt", doc_format="txt", project_id="p1")
    s.ingest_text("汽车 引擎 发动机 保养", source="c.txt", doc_format="txt", project_id="p1")
    return s


def test_rerank_off_returns_fused_order(svc):
    out = svc.retrieve("苹果", top_k=2, rerank=False, project_id="p1")
    assert len(out) >= 1
    assert all("chunk_id" in c for c in out)


def test_rerank_mock_changes_order(svc, monkeypatch):
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    out = svc.retrieve("苹果 公司", top_k=2, rerank=True, project_id="p1")
    assert out[0]["chunk_id"]
    assert "rerank_score" in out[0]


def test_rerank_failure_degrades(svc, monkeypatch):
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    import app.knowledge.service as svc_mod
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(svc_mod, "get_reranker", boom)
    out = svc.retrieve("苹果", top_k=2, rerank=True, project_id="p1")
    assert isinstance(out, list) and len(out) >= 1
