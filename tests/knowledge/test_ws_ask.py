import os, tempfile, pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service
import app.api.knowledge_ws as ws_mod

def _c():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ga-ws-t9"
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = KnowledgeService(db_path=p)
    # 灌一条属于 PA 的文档
    svc.ingest_text("hello alpha content", project_id="PA", title="da")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    # WS 端点内部 new KnowledgeService()/resolve_knowledge_auth 默认查默认库；
    # 用 monkeypatch 让 WS 用同一临时库
    import app.knowledge.service as svc_mod
    return TestClient(app), p, repo, svc

def _rm(p):
    for s in ("", "-wal", "-shm"):
        try: os.remove(p + s)
        except OSError: pass

def test_ws_rejects_no_auth(monkeypatch):
    c, p, repo, svc = _c()
    # 让 WS 内部构造的 KnowledgeService 复用临时 repo（否则查默认库）
    monkeypatch.setattr(ws_mod, "KnowledgeService", lambda *a, **k: svc)
    try:
        with c.websocket_connect("/ws/knowledge/ask") as ws:
            ws.send_json({"type": "ping"})
            with pytest.raises(Exception):
                ws.receive_json()  # 无 token → 服务端 close(1008)
    finally:
        app.dependency_overrides.clear(); _rm(p)

def test_ws_ping_pong(monkeypatch):
    c, p, repo, svc = _c()
    monkeypatch.setattr(ws_mod, "KnowledgeService", lambda *a, **k: svc)
    try:
        with c.websocket_connect("/ws/knowledge/ask",
                                 headers={"Authorization": "Bearer ga-ws-t9"}) as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
    finally:
        app.dependency_overrides.clear(); _rm(p)

def test_ws_ask_returns_sources_frame(monkeypatch):
    c, p, repo, svc = _c()
    monkeypatch.setattr(ws_mod, "KnowledgeService", lambda *a, **k: svc)
    try:
        with c.websocket_connect("/ws/knowledge/ask",
                                 headers={"Authorization": "Bearer ga-ws-t9"}) as ws:
            ws.send_json({"type": "ask", "request_id": "r1",
                          "query": "hello", "project_id": "PA"})
            f1 = ws.receive_json()
            assert f1["type"] == "sources" and f1["request_id"] == "r1"
            f2 = ws.receive_json()
            assert f2["type"] == "end"
    finally:
        app.dependency_overrides.clear(); _rm(p)
