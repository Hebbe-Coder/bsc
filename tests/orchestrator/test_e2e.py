# tests/orchestrator/test_e2e.py
import asyncio

try:
    from tests.orchestrator.test_engine import FakeBus
except Exception:
    class FakeBus:
        def __init__(self): self.events = []
        async def publish(self, session_id, event): self.events.append(event)

from app.orchestrator.engine import OrchestratorEngine


def test_golden_content_moderation():
    # 用贴近「内容审核中心」语义的 stub agents，断言 6 段状态正确演进
    class A:
        def run(self, *a, **k): return {"project": {"name": "内容审核中心", "industry": "互联网"},
                                         "requirements": [{"id": "r1", "text": "多模态", "priority": "high"}]}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class B:
        def run(self, *a, **k): return {"business_model": {"flows": [{"id": "f1", "name": "受理"}], "roles": [{"id": "r1", "name": "审核员"}], "rules": []}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class S:
        def run(self, *a, **k): return {"sop": {"sops": [{"id": "s1", "title": "审核SOP", "owner_role": "审核员", "steps": [{"seq": 1, "action": "初审"}]}]}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class R:
        def run(self, *a, **k): return {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class P:
        def run(self, *a, **k): return {"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    eng = OrchestratorEngine(agents={"planner": A(), "architect": B(), "sop": S(), "reviewer": R(), "presenter": P()},
                              bus=FakeBus())
    state = asyncio.run(eng.run_pipeline("golden-1", "我要做一个内容审核中心"))
    assert state["project"]["name"] == "内容审核中心"
    assert state["business_model"]["flows"][0]["name"] == "受理"
    assert state["sop"]["sops"][0]["title"] == "审核SOP"
    assert state["review"]["approved"] is True
    assert "presentation" in state
