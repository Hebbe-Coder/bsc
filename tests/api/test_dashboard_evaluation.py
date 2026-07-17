# tests/api/test_dashboard_evaluation.py
"""仪表盘端点 evaluation 段测试（方案 C Phase 1）。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.orchestrate import router
from app.agent.state import ProjectDraftRepository, ProjectDraft


def _put_draft(session_id: str, **kwargs):
    """写一条 draft 并返回裸字典 state。"""
    repo = ProjectDraftRepository()
    draft = ProjectDraft(session_id=session_id, **kwargs)
    repo.save(draft)
    return draft.to_dict()


def test_dashboard_includes_evaluation():
    state = _put_draft("eval-1",
        sop={"sops": [{"id": "s1"}], "_citation_coverage": {"coverage": 1.0, "covered": 1, "total": 1, "flagged": []}},
        business_model={"flows": [{"id": "f1"}], "roles": [], "rules": [], "_citation_coverage": {"coverage": 0.5, "covered": 1, "total": 2, "flagged": ["r1"]}},
        risk={"gate": {"decision": "pass"}, "coverage": {"total": 5, "covered": 4, "coverage_pct": 80, "uncovered_ids": ["c5"]}},
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get(f"/api/orchestrate/dashboard/{state['session_id']}")
    assert r.status_code == 200
    body = r.json()
    assert "evaluation" in body, body.keys()
    ev = body["evaluation"]
    assert isinstance(ev["overall_score"], int)
    # 方法论：(1.0+0.5)/2*100=75; 约束 80; 门禁 pass=100; 审计 verified 100; 结构 3/3=100
    # 75*0.25+80*0.20+100*0.20+100*0.15+100*0.20 = 89
    assert ev["overall_score"] == 89
    assert ev["is_passed"] is True
    assert isinstance(ev["dimensions"], list) and len(ev["dimensions"]) == 5


def test_dashboard_evaluation_empty_draft():
    state = _put_draft("eval-empty",
        sop={}, business_model={}, risk={},
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get(f"/api/orchestrate/dashboard/{state['session_id']}")
    assert r.status_code == 200
    ev = r.json()["evaluation"]
    # 仅审计完整 → 100*0.15 = 15
    assert ev["overall_score"] == 15
    assert ev["is_passed"] is False
