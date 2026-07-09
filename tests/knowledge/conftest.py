import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service

# 知识库测试统一使用的 API Key：所有功能测试默认携带合法 Key，
# 以真实走通「已配置 API_KEY」路径；鉴权拦截用例改用 anon_client / dev_unset_client。
TEST_API_KEY = "test-api-key-for-knowledge-suite"


def _make_client(monkeypatch, api_key: str, attach_header: bool):
    monkeypatch.setattr(settings, "API_KEY", api_key)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    tmp = f.name
    app.dependency_overrides[get_knowledge_service] = (
        lambda: KnowledgeService(db_path=tmp))
    c = TestClient(app)
    if attach_header and api_key:
        c.headers["Authorization"] = f"Bearer {api_key}"
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(monkeypatch):
    """功能测试 client：服务端已配置 API_KEY，且默认携带合法 Bearer Key。"""
    yield from _make_client(monkeypatch, TEST_API_KEY, attach_header=True)


@pytest.fixture
def anon_client(monkeypatch):
    """未携带 Key 的 client（服务端已配置 API_KEY），用于验证鉴权拦截。"""
    yield from _make_client(monkeypatch, TEST_API_KEY, attach_header=False)


@pytest.fixture
def dev_unset_client(monkeypatch):
    """模拟 API_KEY 未配置的开发环境：知识库端点必须被拒，非知识库端点放行。"""
    yield from _make_client(monkeypatch, "", attach_header=False)
