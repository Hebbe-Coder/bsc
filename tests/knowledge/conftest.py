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


@pytest.fixture(autouse=True)
def _isolate_global_state():
    """快照并还原全局 settings 与 app.dependency_overrides。

    知识库套件中部分用例（含辅助函数 _c()）会直接赋值 settings.API_KEY 等全局字段，
    若不还原会泄漏到后续非知识库测试模块（如 test_integration / test_sop_report_engine），
    导致 AuthMiddleware 对无鉴权请求返回 401，出现「单测通过、全量失败」的串扰。
    该 autouse fixture 对每个知识库用例做全字段快照/还原，隔离全局状态泄漏。
    """
    field_names = list(getattr(type(settings), "model_fields", {}).keys())
    snapshot = {k: getattr(settings, k) for k in field_names if hasattr(settings, k)}
    import app.main as _main
    overrides_snapshot = dict(_main.app.dependency_overrides)
    try:
        yield
    finally:
        for k, v in snapshot.items():
            try:
                setattr(settings, k, v)
            except Exception:
                pass
        _main.app.dependency_overrides.clear()
        _main.app.dependency_overrides.update(overrides_snapshot)


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
