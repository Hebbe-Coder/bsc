import asyncio
from app.orchestrator.engine import OrchestratorEngine


class FakeBus:
    def __init__(self): self.events = []
    async def publish(self, session_id, event): self.events.append(event)


class Stub:
    def __init__(self, payload): self.payload = payload
    def run(self, *a, **k): return self.payload


def make():
    agents = {
        "planner": Stub({"project": {"name": "x"}, "requirements": []}),
        "architect": Stub({"business_model": {"flows": [], "roles": [], "rules": []}}),
        "sop": Stub({"sop": {"sops": []}}),
        "risk": Stub({"risk": {"overall_score": "low", "coverage": {"coverage_pct": 100}, "gate": {"decision": "pass"}, "audit": []}}),
        "reviewer": Stub({"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}),
        "presenter": Stub({"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}),
    }
    return OrchestratorEngine(agents=agents, repo=None, bus=FakeBus())


def test_rerun_risk_propagates_to_reviewer_and_presenter():
    eng = make()
    asyncio.run(eng.run_pipeline("r1", "x"))
    # 重跑 risk 应级联 reviewer -> presenter
    out = asyncio.run(eng.rerun_node("r1", "risk"))
    assert "risk" in out
    assert "review" in out
    assert "presentation" in out
