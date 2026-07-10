import asyncio, os, tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def ws_env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws2-admin"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p)
    ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("咖啡 烘焙 温度曲线 知识内容", project_id="P1", title="coffee")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    svc.repo.close(); repo.close()
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def test_ws_ask_streams_and_cancels(ws_env):
    with ws_env.websocket_connect("/ws/knowledge/ask?token=ws2-admin") as ws:
        ws.send_json({"type": "ask", "request_id": "r1", "project_id": "P1",
                      "query": "咖啡", "top_k": 3})
        frames = {}
        while True:
            msg = ws.receive_json()
            frames[msg["type"]] = frames.get(msg["type"], 0) + 1
            if msg["type"] == "end":
                break
        assert frames.get("token", 0) > 0, "应流式输出 token"
        assert frames.get("sources", 0) == 1, "应有 sources 帧"
