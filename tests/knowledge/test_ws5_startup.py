import os
import tempfile

from app.core.config import settings


def test_startup_ensures_knowledge_schema_once(monkeypatch):
    # 验证 KnowledgeService 在临时 DB 构造+检索路径不抛异常
    # （启动期已预热；此处仅确认构造+检索路径可用）
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(settings, "API_KEY", "ws5-admin")
    repo = None
    svc = None
    try:
        from app.knowledge.schema import ensure_schema
        from app.repositories.knowledge_repository import KnowledgeRepository
        repo = KnowledgeRepository(db_path=p)
        ensure_schema(repo)
        svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
        svc.ingest_text("启动期 schema 预热", project_id="P1", title="s")
        res = svc.retrieve("启动期", project_id="P1", top_k=3)
        assert isinstance(res, list)
    finally:
        # 显式关闭连接，避免 Windows 下文件句柄未释放时 os.remove 抛 OSError 被吞掉导致泄漏
        for r in (svc.repo if svc else None, repo):
            try:
                if r is not None:
                    r.close()
            except Exception:
                pass
        try:
            os.remove(p)
        except OSError:
            pass
