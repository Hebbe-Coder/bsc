"""方案 E：仪表盘端点返回体须含 trusted_audit 段（方案 D 端点扩展）。

只挂载 orchestrate 路由，避免加载 app.main（17 个路由 / 脏模块）。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.state import ProjectDraft, ProjectDraftRepository
from app.api.orchestrate import router

TRUST_SESSION = "dash-trust-session-1"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed():
    draft = ProjectDraft(
        session_id=TRUST_SESSION,
        idea="可信审计测试 PRD",
        status="done",
        sop={
            "sops": [{"id": "s1", "source_ref": ["c1"]}],
            "_citation_coverage": {"coverage": 1.0, "covered": 1, "total": 1, "flagged": []},
        },
        risk={
            "overall_score": "high",
            "gate": {"decision": "block", "reason": "x"},
            "coverage": {"total": 3, "covered": 2, "coverage_pct": 67, "uncovered_ids": ["r3"]},
            "risks": [],
        },
        business_model={"model": "订阅制"},
    )
    ProjectDraftRepository().save(draft)


def test_dashboard_includes_trusted_audit():
    _seed()
    resp = _client().get(f"/api/orchestrate/dashboard/{TRUST_SESSION}")
    assert resp.status_code == 200
    body = resp.json()
    assert "trusted_audit" in body
    ta = body["trusted_audit"]
    # 引用来自 sop 的 source_ref
    assert ta["source_refs"] == ["c1"]
    # 链自洽
    assert ta["verified"] is True
    # 覆盖率快照透传
    assert ta["coverage"]["coverage_pct"] == 67
    # 链头哈希（SHA-256 64 位十六进制）
    assert isinstance(ta["chain_hash"], str) and len(ta["chain_hash"]) == 64
    assert len(ta["audit"]) == 2
