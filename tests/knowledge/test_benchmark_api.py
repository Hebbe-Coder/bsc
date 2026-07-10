"""Task 11: 常驻 gold benchmark 注入 + before/after rerank 对比端点（admin-gated）。

严格 TDD：先写失败测试，再实现。两个端点都必须 admin 鉴权
（POST /knowledge/evaluate/benchmark/gold 与 GET /knowledge/evaluate/benchmark）。

注意（与计划草稿的偏差）：
本仓库在 TestClient 下，/knowledge/* 缺失鉴权头时 AuthMiddleware 会
以 HTTPException(401/403) 形式抛出（参见 tests/knowledge/test_api_auth.py 约定），
而非返回带 success 字段的 JSON 信封。因此 admin 拦截用例采用「双路」断言：
- 若请求返回响应：断言 body["success"] is False；
- 若请求直接抛出 HTTPException：断言其 status_code 为 401/403。
两种路径都能证明端点是 admin-gated。
"""
import os
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service
from app.knowledge.service import KnowledgeService


def _c():
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings.API_KEY = "ga-bm"
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema
    ensure_schema(repo)
    svc = KnowledgeService(db_path=p)
    svc.ingest_text("咖啡 烘焙 温度曲线", project_id="PB", title="coffee")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    return TestClient(app), p, svc


def _auth():
    return {"Authorization": "Bearer ga-bm"}


def _cleanup(p, svc):
    app.dependency_overrides.clear()
    try:
        svc.repo._close_connection()
    except Exception:
        pass
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(p + suffix)
        except OSError:
            pass


def _no_auth_request(method, client, url, **kw):
    """发起无鉴权请求；返回响应对象，或抛出的异常（用于断言 admin 拦截）。"""
    try:
        if method == "post":
            return client.post(url, **kw)
        return client.get(url, **kw)
    except Exception as e:  # noqa: BLE001 - 捕获 TestClient 透传的 HTTPException
        return e


def test_benchmark_resident():
    c, p, svc = _c()
    try:
        # 注入常驻 gold
        rg = c.post(
            "/knowledge/evaluate/benchmark/gold",
            json={"project_id": "PB", "query": "咖啡 烘焙", "expected_chunk_ids": [], "notes": "smoke"},
            headers=_auth(),
        )
        assert rg.status_code == 200
        assert rg.json()["success"] is True
        assert rg.json()["data"]["added"] is True

        # 运行 before/after 对比
        r = c.get("/knowledge/evaluate/benchmark", params={"project_id": "PB"}, headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        for k in ("rerank_not_worse", "isolation_ok", "gold_count", "before", "after"):
            assert k in data, f"missing key: {k}"
        assert data["gold_count"] == 1
        assert isinstance(data["rerank_not_worse"], bool)
        assert isinstance(data["isolation_ok"], bool)
        # before/after 各自含 precision@k / recall@k
        for phase in ("before", "after"):
            assert "precision@k" in data[phase]
            assert "recall@k" in data[phase]
    finally:
        _cleanup(p, svc)


def test_benchmark_no_gold_returns_400():
    c, p, svc = _c()
    try:
        # 该项目无任何 gold
        r = c.get("/knowledge/evaluate/benchmark", params={"project_id": "PNONE"}, headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert body["code"] == 400
    finally:
        _cleanup(p, svc)


def test_benchmark_gold_requires_admin():
    c, p, svc = _c()
    try:
        res = _no_auth_request(
            "post",
            c,
            "/knowledge/evaluate/benchmark/gold",
            json={"project_id": "PB", "query": "咖啡 烘焙", "expected_chunk_ids": [], "notes": "x"},
        )
        if isinstance(res, Exception):
            # TestClient 透传的鉴权异常
            assert isinstance(res, HTTPException)
            assert res.status_code in (401, 403)
        else:
            # 若返回信封，则必须是失败
            assert res.json()["success"] is False
    finally:
        _cleanup(p, svc)


def test_benchmark_get_requires_admin():
    c, p, svc = _c()
    try:
        # 先注入一条 gold（以 admin 身份），证明 GET 端点本身需要鉴权
        c.post(
            "/knowledge/evaluate/benchmark/gold",
            json={"project_id": "PB", "query": "咖啡 烘焙", "expected_chunk_ids": [], "notes": "smoke"},
            headers=_auth(),
        )
        res = _no_auth_request(
            "get",
            c,
            "/knowledge/evaluate/benchmark",
            params={"project_id": "PB"},
        )
        if isinstance(res, Exception):
            assert isinstance(res, HTTPException)
            assert res.status_code in (401, 403)
        else:
            assert res.json()["success"] is False
    finally:
        _cleanup(p, svc)
