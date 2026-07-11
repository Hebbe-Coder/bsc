# tests/orchestrator/test_agents.py  (Planner 部分)
import asyncio
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.agents.business_architect import BusinessArchitectAgent
from app.orchestrator.agents.sop_builder import SopBuilderAgent
from app.orchestrator.agents.reviewer import ReviewerAgent
from app.orchestrator.schemas import validate_segment


class FakeLLM:
    def __init__(self, payload): self._p = payload
    def chat(self, system_prompt, user_prompt, temperature=0.1, max_tokens=None, use_cache=True):
        return self._p


def test_planner_produces_project_and_requirements():
    payload = {
        "project": {"name": "内容审核中心", "goal": "高效审核 UGC", "industry": "互联网",
                    "scope": {"in_scope": ["文本审核"], "out_scope": ["视频"]},
                    "actors": [{"role": "审核员", "description": "一线审核"}]},
        "requirements": [{"id": "r1", "text": "支持多模态", "priority": "high", "source": "user"}],
    }
    agent = PlannerAgent(llm_service=FakeLLM(payload))
    out = agent.run(idea="我要做一个内容审核中心")
    validate_segment("project", out["project"])   # 不抛异常
    validate_segment("requirements", out["requirements"])
    assert out["project"]["name"] == "内容审核中心"


class FakeCompile:
    async def __call__(self, prd, llm_service=None, **kw):
        return {"functions": [{"name": "受理"}], "roles": [{"name": "审核员"}]}


def test_ba_produces_business_model():
    payload = {"business_model": {"flows": [{"id": "f1", "name": "受理", "steps": ["收单"]}],
                                  "roles": [{"id": "r1", "name": "审核员"}], "rules": []}}
    agent = BusinessArchitectAgent(llm_service=FakeLLM(payload))
    out = asyncio.run(agent.run(idea="内容审核中心",
                                project={"name": "内容审核中心"},
                                requirements=[],
                                _compile=FakeCompile()))
    assert "business_model" in out
    assert out["business_model"]["flows"][0]["name"] == "受理"


class FakeSopEngine:
    def generate_full_sop_report(self, business_system, enable_ai_analysis=False):
        return {"workflow": [{"step": 1, "name": "受理", "action": "收单"}],
                "roles": [{"role": "审核员"}],
                "sla": [{"metric": "时效", "target": "5min", "owner": "审核员"}]}


def test_sop_builder_produces_sops():
    payload = {"sop": {"sops": [{"id": "s1", "title": "审核 SOP", "owner_role": "审核员",
                                  "trigger": "收到内容", "steps": [{"seq": 1, "action": "初审"}],
                                  "escalation": "升级主管", "review_cycle": "周"}]}}
    agent = SopBuilderAgent(llm_service=FakeLLM(payload))
    out = agent.run(business_model={"flows": [], "roles": [], "rules": []},
                    _engine=FakeSopEngine())
    assert "sop" in out
    assert out["sop"]["sops"][0]["title"] == "审核 SOP"


def test_reviewer_finds_gap_and_loopback():
    payload = {"review": {"approved": False,
        "gaps": [{"id": "g1", "severity": "high", "type": "sla",
                  "desc": "缺 SLA", "suggested_fix": "加 SLA", "target": "sop"}],
        "loopback_target": "sop", "summary": "需补 SLA"}}
    agent = ReviewerAgent(llm_service=FakeLLM(payload))
    out = agent.run(project={}, business_model={}, sop={})
    assert out["review"]["approved"] is False
    assert out["review"]["loopback_target"] == "sop"


def test_reviewer_approves():
    payload = {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
    agent = ReviewerAgent(llm_service=FakeLLM(payload))
    out = agent.run(project={}, business_model={}, sop={})
    assert out["review"]["approved"] is True
