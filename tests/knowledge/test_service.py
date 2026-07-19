import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
    res = svc.retrieve("内容安全 审核", project_id="p1")
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
    res = svc.retrieve("内容安全 审核 风控", project_id="p1")
    assert res and res[0]["doc_title"] == "A"

def test_retrieve_empty_corpus():
    svc = _tmp_service()
    assert svc.retrieve("任何查询") == []

def test_ingest_empty_text_returns_none():
    svc = _tmp_service()
    assert svc.ingest("   ") is None

def test_ingest_parse_failure_skips():
    svc = _tmp_service()
    # chunk_text 对正常文本不抛；模拟坏数据不崩：
    assert svc.ingest("") is None          # 空文本跳过
    assert svc.ingest(None) is None        # None 跳过

def test_retrieve_no_model_safe():
    svc = _tmp_service()                    # 未摄取，无 tfidf_model
    assert svc.retrieve("查询") == []       # 不崩，返回空

def test_list_documents():
    svc = _tmp_service()
    svc.ingest("内容安全平台过滤违规信息。", project_id="p1", title="A")
    svc.ingest("咖啡烘焙风味分析。", project_id="p2", title="B")
    res = svc.list_documents()
    assert res["total"] == 2
    assert all(d["chunk_count"] >= 1 for d in res["documents"])
    assert {d["title"] for d in res["documents"]} == {"A", "B"}


def test_list_documents_project_filter():
    svc = _tmp_service()
    svc.ingest("x", project_id="p1", title="A")
    svc.ingest("y", project_id="p2", title="B")
    res = svc.list_documents(project_id="p1")
    assert res["total"] == 1 and res["documents"][0]["title"] == "A"


def test_delete_document():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台过滤违规信息。", title="A")
    assert svc.delete_document(doc_id) is True
    assert svc.list_documents()["total"] == 0


def test_delete_missing_returns_false():
    svc = _tmp_service()
    assert svc.delete_document("nope") is False
