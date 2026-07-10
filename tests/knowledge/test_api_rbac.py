"""知识库端点基于角色的细粒度授权（RBAC）测试。

角色模型：
- admin（全局 API_KEY）：可读 / 检索 / 灌入 / 删除；写入需显式 project_id。
- reader（全局 API_KEY_READER）：系统级只读——可读/检索/问答任意 project，
  但任何写入（ingest / delete）一律 403；读取需显式 project_id。
- project_admin：可对自己的 project 读写。
- project_reader：仅对自己的 project 只读；写入 403。
reader key 仅对 /knowledge/* 生效，且不授予非知识库端点的访问权（由 AuthMiddleware 保证）。
"""
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service

ADMIN_KEY = "admin-secret-key"
READER_KEY = "reader-secret-key"


def _client_with_key(monkeypatch, key: str):
    monkeypatch.setattr(settings, "API_KEY", ADMIN_KEY)
    monkeypatch.setattr(settings, "API_KEY_READER", READER_KEY)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    tmp = f.name
    app.dependency_overrides[get_knowledge_service] = (
        lambda: KnowledgeService(db_path=tmp))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {key}"
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(monkeypatch):
    yield from _client_with_key(monkeypatch, ADMIN_KEY)


@pytest.fixture
def reader_client(monkeypatch):
    yield from _client_with_key(monkeypatch, READER_KEY)


def test_reader_can_list(reader_client):
    # 全局 reader 系统级只读：提供有效 project_id 时可列出文档
    r = reader_client.get("/knowledge/documents", params={"project_id": "p1"})
    assert r.status_code == 200


def test_reader_can_retrieve(reader_client):
    # 全局 reader 系统级只读：提供有效 project_id 时可检索
    r = reader_client.post("/knowledge/retrieve",
                           json={"query": "企业知识", "project_id": "p1"})
    assert r.status_code == 200


def test_reader_cannot_ingest(reader_client):
    # 依赖层抛出的 403 会被 FastAPI 异常处理器转成 403 响应（非异常冒泡），故断言状态码
    r = reader_client.post("/knowledge/ingest", data={"text": "x", "project_id": "p1"})
    assert r.status_code == 403


def test_reader_cannot_delete(reader_client):
    r = reader_client.delete("/knowledge/documents/does-not-exist")
    assert r.status_code == 403


def test_admin_can_ingest(admin_client):
    r = admin_client.post("/knowledge/ingest", data={"text": "企业知识库内容", "project_id": "p1"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["count"] == 1


def test_admin_can_delete(admin_client):
    # 删除不存在文档：通过鉴权后由业务层返回 404 信封，绝不应是 403
    r = admin_client.delete("/knowledge/documents/missing-id")
    assert r.status_code == 200
    assert r.json()["code"] == 404
