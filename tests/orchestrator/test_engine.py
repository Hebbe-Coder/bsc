# tests/orchestrator/test_engine.py
import asyncio
from app.orchestrator.engine import OrchestratorEngine


class FakeBus:
    def __init__(self): self.events = []
    async def publish(self, session_id, event): self.events.append(event)


def make_engine():
    # 每个 agent 直接返回正确段名的固定 payload
    class StubAgent:
        def __init__(self, payload): self.payload = payload
        def run(self, *a, **k): return self.payload
        async def run_async(self, *a, **k): return self.payload
    agents = {
        "planner": StubAgent({"project": {"name": "x"}, "requirements": []}),
        "architect": StubAgent({"business_model": {"flows": [], "roles": [], "rules": []}}),
        "sop": StubAgent({"sop": {"sops": []}}),
        "reviewer": StubAgent({"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}),
        "presenter": StubAgent({"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}),
    }
    return OrchestratorEngine(agents=agents, repo=None, bus=FakeBus())


def test_pipeline_writes_six_segments():
    eng = make_engine()
    result = asyncio.run(eng.run_pipeline("s1", "内容审核中心"))
    assert result["project"]["name"] == "x"
    assert "business_model" in result
    assert result["review"]["approved"] is True


def test_loopback_once_on_high_gap():
    eng = make_engine()
    # 让 reviewer 第一次返回 high 漏洞打回 sop，第二次通过
    class LoopReviewer:
        def __init__(self): self.n = 0
        def run(self, *a, **k):
            self.n += 1
            if self.n == 1:
                return {"review": {"approved": False, "gaps": [{"severity": "high", "target": "sop"}],
                                   "loopback_target": "sop", "summary": "缺 SLA"}}
            return {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
    eng.agents["reviewer"] = LoopReviewer()
    result = asyncio.run(eng.run_pipeline("s2", "内容审核中心"))
    assert result["review"]["approved"] is True   # 回环后通过


def test_presenter_receives_session_id():
    # 回归：engine 必须把 session_id 真正传入 presenter agent（否则真实 PresenterAgent 缺参）
    eng = make_engine()
    captured = {}
    class PresenterSpy:
        def run(self, *a, **k):
            captured.update(k)
            return {"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}
    eng.agents["presenter"] = PresenterSpy()
    asyncio.run(eng.run_pipeline("s3", "内容审核中心"))
    assert captured.get("session_id") == "s3"
    assert "state" in captured
