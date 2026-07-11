import asyncio
from unittest.mock import patch

import pytest

from app.api import bsc_api
from app.core.config import settings


def _fake_result(failed_agent="sop"):
    return {
        "business_system": {"composed": {}, "business_understanding": {}},
        "pipeline": {
            "stages": [
                {"agent": "business_understanding", "display": "BU", "status": "success"},
                {"agent": failed_agent, "display": "SOP", "status": "failed", "error": "boom"},
            ],
            "total_ms": 1,
            "parallel": True,
        },
        "summary": "",
        "workspace": {},
        "template": {},
    }


@pytest.fixture
def req():
    from app.api.bsc_api import CompileRequest
    return CompileRequest(input="x" * 10, output_types=[])


def test_compile_prd_reports_failure(monkeypatch, req):
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    with patch("app.core.async_pipeline.compile_to_business_system_async",
               return_value=_fake_result("sop")):
        resp = asyncio.run(bsc_api.compile_prd(req))
    assert resp.success is False, "部分失败却被标记为 success"
    assert resp.code == 2001
    agents = [s["agent"] for s in resp.data["stages"]]
    assert "sop" in agents


def test_compile_prd_failure_http_envelope(monkeypatch):
    """经 FastAPI 路由序列化：失败分支必须返回 HTTP 200 + success=False 信封，
    而非因 response_model 不匹配导致的 HTTP 500（捕获 P0 回归）。"""
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(bsc_api.router)
    client = TestClient(app)

    with patch("app.core.async_pipeline.compile_to_business_system_async",
               return_value=_fake_result("sop")):
        resp = client.post("/bsc/compile", json={"input": "x" * 10, "output_types": []})

    assert resp.status_code == 200, f"期望 200 信封，实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == 2001
    assert "sop" in [s["agent"] for s in body["data"]["stages"]]
    # 安全回归：不应泄漏堆栈/异常内部字段
    for s in body["data"]["stages"]:
        assert "traceback" not in s and "exception" not in s and "stack" not in s


def test_compile_prd_sync_reports_failure(monkeypatch, req):
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    with patch("app.core.bsc_pipeline.compile_to_business_system",
               return_value=_fake_result("risk")):
        resp = asyncio.run(bsc_api.compile_prd_sync(req))
    assert resp.success is False, "部分失败却被标记为 success"
    assert resp.code == 2001
    agents = [s["agent"] for s in resp.data["stages"]]
    assert "risk" in agents


def test_compile_prd_sync_failure_http_envelope(monkeypatch):
    """经 FastAPI 路由序列化：同步入口失败分支必须返回 HTTP 200 + success=False，
    而非 response_model 不匹配导致的 500。"""
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(bsc_api.router)
    client = TestClient(app)

    with patch("app.core.bsc_pipeline.compile_to_business_system",
               return_value=_fake_result("risk")):
        resp = client.post("/bsc/compile/sync", json={"input": "x" * 10, "output_types": []})

    assert resp.status_code == 200, f"期望 200 信封，实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == 2001
    assert "risk" in [s["agent"] for s in body["data"]["stages"]]
    for s in body["data"]["stages"]:
        assert "traceback" not in s and "exception" not in s and "stack" not in s
