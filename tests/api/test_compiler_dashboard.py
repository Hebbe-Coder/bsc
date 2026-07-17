# tests/api/test_compiler_dashboard.py
"""Task 1：仪表盘端点重塑 ProjectDraft 的测试。

只挂载 orchestrate 路由，避免加载 app.main（17 个路由 / 脏模块）。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.state import ProjectDraft, ProjectDraftRepository
from app.api.orchestrate import router

DASH_SESSION = "dash-session-1"
EMPTY_SESSION = "dash-session-empty"
UNKNOWN_SESSION = "dash-session-never-saved"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_dash_draft():
    """构造并持久化一个带 sop / risk 段的编译草稿。"""
    draft = ProjectDraft(
        session_id=DASH_SESSION,
        idea="测试用 PRD 想法",
        status="done",
        sop={
            "sops": [{"id": "s1", "title": "步骤一", "source_ref": ["c1"]}],
            "_citation_coverage": {"coverage": 1.0, "covered": 1, "total": 1, "flagged": []},
        },
        risk={
            "overall_score": "high",
            "gate": {"decision": "block", "reason": "x"},
            "coverage": {"total": 3, "covered": 2, "coverage_pct": 67, "uncovered_ids": ["r3"]},
            "risks": [{"id": "rk1", "title": "t", "severity": "high",
                       "linked_constraints": ["r3"], "detail": "d"}],
        },
        business_model={"model": "订阅制"},
    )
    ProjectDraftRepository().save(draft)


def _seed_empty_draft():
    """构造并持久化一个 sop / risk 为空的空壳草稿。"""
    draft = ProjectDraft(session_id=EMPTY_SESSION, idea="空壳想法", status="planned")
    ProjectDraftRepository().save(draft)


def test_dashboard_returns_reshaped():
    _seed_dash_draft()
    resp = _client().get(f"/api/orchestrate/dashboard/{DASH_SESSION}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == DASH_SESSION
    # 风险段重塑
    assert body["risk"]["gate"]["decision"] == "block"
    assert body["risk"]["coverage"]["coverage_pct"] == 67
    # sop 段重塑
    assert body["sop"]["sops"][0]["source_ref"] == ["c1"]
    assert body["sop"]["_citation_coverage"]["coverage"] == 1.0
    # 业务模型透传
    assert body["business_model"] == {"model": "订阅制"}


def test_dashboard_404_unknown():
    resp = _client().get(f"/api/orchestrate/dashboard/{UNKNOWN_SESSION}")
    assert resp.status_code == 404


def test_dashboard_empty_shell():
    _seed_empty_draft()
    resp = _client().get(f"/api/orchestrate/dashboard/{EMPTY_SESSION}")
    assert resp.status_code == 200
    body = resp.json()
    # 空壳下重塑字段给出安全的空默认值
    assert body["sop"]["sops"] == []
    assert body["sop"]["_citation_coverage"] == {}
    assert body["risk"]["risks"] == []
