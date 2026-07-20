# tests/api/test_dashboard_evolution.py
"""仪表盘端点 evolution 段测试（方案 C Phase 2）。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.orchestrate import router
from app.agent.state import ProjectDraftRepository, ProjectDraft


def _put_draft(session_id: str, **kwargs):
    repo = ProjectDraftRepository()
    kwargs.setdefault("status", "completed")
    draft = ProjectDraft(session_id=session_id, **kwargs)
    repo.save(draft)
    return draft.to_dict()


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_dashboard_includes_evolution():
    state = _put_draft("evo-1",
        idea="做一个咖啡馆",
        sop={"sops": [{"id": "s1", "title": "开店流程"}], "_citation_coverage": {"coverage": 1.0, "covered": 1, "total": 1, "flagged": []}},
        business_model={"flows": [{"id": "f1"}], "roles": [], "rules": [], "_citation_coverage": {"coverage": 0.8, "covered": 2, "total": 2, "flagged": []}},
        risk={"gate": {"decision": "pass"}, "coverage": {"total": 3, "covered": 3, "coverage_pct": 100, "uncovered_ids": []}},
    )
    r = _client().get(f"/api/orchestrate/dashboard/{state['session_id']}")
    assert r.status_code == 200
    body = r.json()
    assert "evolution" in body
    evo = body["evolution"]
    assert "recent_feedback" in evo and "stats" in evo
    assert isinstance(evo["recent_feedback"], list)
    assert len(evo["recent_feedback"]) >= 1
    # 最近一条应来自当前 session
    last = evo["recent_feedback"][0]
    assert last["trace_id"] == "evo-1"
    assert last["user_id"] == "compiler_evaluator"
    assert last["feedback_type"] in {"thumbs_up", "thumbs_down", "comment"}
    # stats.total >= 1
    assert evo["stats"]["total"] >= 1


def test_evolution_high_score_records_thumbs_up():
    # SOP 满分 + risk pass + 引用满 → 评测接近 100 → thumbs_up
    state = _put_draft("evo-high",
        idea="满分 demo",
        sop={"sops": [{"id": "s1", "title": "S"}], "_citation_coverage": {"coverage": 1.0, "covered": 1, "total": 1, "flagged": []}},
        business_model={"flows": [{"id": "f1"}], "roles": [{"id": "r1"}], "rules": [{"id": "ru1"}], "_citation_coverage": {"coverage": 1.0, "covered": 3, "total": 3, "flagged": []}},
        risk={"gate": {"decision": "pass"}, "coverage": {"total": 5, "covered": 5, "coverage_pct": 100, "uncovered_ids": []}},
    )
    r = _client().get(f"/api/orchestrate/dashboard/{state['session_id']}")
    last = r.json()["evolution"]["recent_feedback"][0]
    assert last["feedback_type"] == "thumbs_up"


def test_evolution_low_score_records_thumbs_down():
    # 空 draft → 评测 15 → thumbs_down
    state = _put_draft("evo-low",
        idea="空 demo",
        sop={}, business_model={}, risk={},
    )
    r = _client().get(f"/api/orchestrate/dashboard/{state['session_id']}")
    last = r.json()["evolution"]["recent_feedback"][0]
    assert last["feedback_type"] == "thumbs_down"


def test_evolution_accumulates_across_sessions():
    # 多次访问 → stats 累计增加
    c = _client()
    for i in range(3):
        state = _put_draft(f"evo-acc-{i}", idea=f"x{i}", sop={"sops": [{"id": "s1"}]}, risk={"gate": {"decision": "pass"}})
        c.get(f"/api/orchestrate/dashboard/{state['session_id']}")
    # 最新一次返回的 recent 至少 1 条
    body = c.get("/api/orchestrate/dashboard/evo-acc-2").json()
    assert body["evolution"]["stats"]["total"] >= 3
