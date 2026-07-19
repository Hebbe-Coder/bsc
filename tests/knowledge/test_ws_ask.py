import os
import tempfile
import pytest
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
    # 用假 LLM 服务，避免真实网络；T10 改为 token 流 + end
    import app.services.async_llm_service as allm
    monkeypatch.setattr(allm, "get_async_llm_service", lambda: _FakeLLM())
    try:
        with c.websocket_connect("/ws/knowledge/ask",
                                 headers={"Authorization": "Bearer ga-ws-t9"}) as ws:
            ws.send_json({"type": "ask", "request_id": "r1",
                          "query": "hello", "project_id": "PA"})
            f1 = ws.receive_json()
            assert f1["type"] == "sources" and f1["request_id"] == "r1"
            # T10 协议：sources 之后为 token 流，最终以 end 收尾
            seen_end = False
            while True:
                f = ws.receive_json()
                if f["type"] == "end":
                    seen_end = True
                    break
            assert seen_end
    finally:
        app.dependency_overrides.clear(); _rm(p)

class _FakeLLM:
    async def async_stream_chat(self, system_prompt="", user_prompt="", **kw):
        for t in ["Hel", "lo", "!"]:
            yield t

def test_ws_stream_tokens(monkeypatch):
    c, p, repo, svc = _c()
    monkeypatch.setattr(ws_mod, "KnowledgeService", lambda *a, **k: svc)
    import app.services.async_llm_service as allm
    monkeypatch.setattr(allm, "get_async_llm_service", lambda: _FakeLLM())
    try:
        with c.websocket_connect("/ws/knowledge/ask",
                                 headers={"Authorization": "Bearer ga-ws-t9"}) as ws:
            ws.send_json({"type":"ask","request_id":"r1","query":"hello","project_id":"PA"})
            types = []
            while True:
                f = ws.receive_json()
                types.append(f["type"])
                if f["type"] == "end":
                    end = f
                    break
            assert types[0] == "sources"
            assert "token" in types
            assert types[-1] == "end"
            assert end["data"]["answer"] == "Hello!"
    finally:
        app.dependency_overrides.clear(); _rm(p)

def test_ws_cancel_stops_stream(monkeypatch):
    """真实断言：cancel 后流必须提前中断（token 数远小于 100，且 end 标记 cancelled）。"""
    import asyncio
    class _SlowLLM:
        async def async_stream_chat(self, system_prompt="", user_prompt="", **kw):
            for i in range(100):
                await asyncio.sleep(0.02)
                yield f"t{i} "
    c, p, repo, svc = _c()
    monkeypatch.setattr(ws_mod, "KnowledgeService", lambda *a, **k: svc)
    import app.services.async_llm_service as allm
    monkeypatch.setattr(allm, "get_async_llm_service", lambda: _SlowLLM())
    try:
        with c.websocket_connect("/ws/knowledge/ask",
                                 headers={"Authorization": "Bearer ga-ws-t9"}) as ws:
            ws.send_json({"type":"ask","request_id":"r2","query":"long","project_id":"PA"})
            assert ws.receive_json()["type"] == "sources"
            _ = ws.receive_json()  # 至少一个 token
            ws.send_json({"type":"cancel","request_id":"r2"})
            token_count = 1
            end = None
            for _ in range(200):
                f = ws.receive_json()
                if f["type"] == "token":
                    token_count += 1
                elif f["type"] == "end":
                    end = f
                    break
            assert end is not None, "cancel 后必须收到 end 帧"
            # cancel 真正生效：绝不应把 100 个 token 全跑完
            assert token_count < 50, f"cancel 未生效，token_count={token_count}"
            assert end["data"].get("cancelled") is True
    finally:
        app.dependency_overrides.clear(); _rm(p)
