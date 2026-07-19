import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_retrieve_returns_chunk_id_idx_score():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 分析", project_id="p1", title="B")
    res = svc.retrieve("内容安全 违规", project_id="p1")
    assert res, "应检索到结果"
    top = res[0]
    assert "chunk_id" in top and top["chunk_id"]
    assert "idx" in top
    assert "score" in top and isinstance(top["score"], float)
    assert top["doc_title"] == "A"
