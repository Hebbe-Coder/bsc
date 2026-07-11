# tests/orchestrator/test_agents.py  (Planner 部分)
import asyncio
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.agents.business_architect import BusinessArchitectAgent
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
