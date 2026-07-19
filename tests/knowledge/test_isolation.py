from app.knowledge.service import KnowledgeService
import tempfile
import os


def _svc():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    svc = KnowledgeService(db_path=p)
    return svc, p


def _cleanup(svc, p):
    try: svc.repo.close()
    except Exception: pass
    for suffix in ("", "-wal", "-shm"):
        try: os.remove(p + suffix)
        except OSError: pass


def test_no_cross_project_leak():
    svc, p = _svc()
    try:
        svc.ingest_text("A 机密内容 alpha", project_id="PA", title="da")
        svc.ingest_text("B 公开内容 beta", project_id="PB", title="db")
        # PB 检索不应出现 PA 的 chunk
        res_pb = svc.retrieve("alpha", top_k=5, project_id="PB")
        assert all(c["doc_title"] != "da" for c in res_pb)
        # 空 project_id 必须被拒（返回空，不再全可见）
        assert svc.retrieve("alpha", top_k=5, project_id="") == []
    finally:
        _cleanup(svc, p)
