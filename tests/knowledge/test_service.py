import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService

def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)

def test_ingest_then_retrieve():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台用于过滤违规信息。审核效率需要提升。",
                        project_id="p1", title="文档A", source="a.txt")
    assert doc_id
    res = svc.retrieve("内容安全 审核")
    assert res and "内容安全" in res[0]["content"]

def test_retrieve_project_filter():
    svc = _tmp_service()
    svc.ingest("内容安全平台过滤违规。", project_id="p1", title="A")
    svc.ingest("咖啡烘焙风味分析。", project_id="p2", title="B")
    res = svc.retrieve("内容", project_id="p1")
    assert res and all(r["doc_title"] == "A" for r in res)
    res2 = svc.retrieve("内容", project_id="p2")
    assert res2 == [] or all(r["doc_title"] == "B" for r in res2)

def test_hybrid_beats_single():
    svc = _tmp_service()
    svc.ingest("内容安全平台 违规信息 过滤 审核 风控", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 产地 杯测", project_id="p1", title="B")
    res = svc.retrieve("内容安全 审核 风控")
    assert res and res[0]["doc_title"] == "A"

def test_retrieve_empty_corpus():
    svc = _tmp_service()
    assert svc.retrieve("任何查询") == []

def test_ingest_empty_text_returns_none():
    svc = _tmp_service()
    assert svc.ingest("   ") is None
