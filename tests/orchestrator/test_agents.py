# tests/orchestrator/test_agents.py  (Planner 部分)
import asyncio
import os
import tempfile
import threading
import time
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.agents.business_architect import BusinessArchitectAgent
from app.orchestrator.agents.sop_builder import SopBuilderAgent
from app.orchestrator.agents.reviewer import ReviewerAgent
from app.orchestrator.agents.presenter import PresenterAgent
from app.orchestrator.schemas import validate_segment
from app.agents.unified_agent import AgentContext, LLMAgentAdapter


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


def test_ba_legacy_compile_does_not_block_event_loop():
    release = threading.Event()

    class BlockingCompile:
        async def __call__(self, prd, llm_service=None, **kwargs):
            release.wait(timeout=0.5)
            return {"functions": [], "roles": []}

    async def scenario():
        agent = BusinessArchitectAgent(
            llm_service=FakeLLM({"business_model": {}})
        )
        started = time.perf_counter()
        task = asyncio.create_task(agent.run(
            idea="x",
            project={},
            requirements=[],
            _compile=BlockingCompile(),
        ))
        await asyncio.sleep(0.05)
        elapsed = time.perf_counter() - started
        release.set()
        await task
        return elapsed

    assert asyncio.run(scenario()) < 0.2


def test_llm_adapter_injects_service_into_wrapped_agent():
    service = object()

    class InjectableAgent:
        name = "injectable"
        system_prompt = "test"

        def __init__(self):
            self.service = None

        def set_llm_service(self, llm_service):
            self.service = llm_service

        def run(self, chunks, context):
            return {"injected": self.service is service}

    adapter = LLMAgentAdapter(InjectableAgent())
    adapter._llm_service = service

    result = adapter.run(AgentContext(chunks=[]))

    assert result.data["injected"] is True


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


def test_presenter_writes_html_and_ppt():
    out_dir = tempfile.mkdtemp()
    payload = {"presentation": {"html_url": "/presentations/s1.html",
                                "ppt_path": "/presentations/s1.pptx",
                                "diagram_spec": {"flows": [], "roles": [], "rules": []}}}
    agent = PresenterAgent(llm_service=FakeLLM(payload))
    out = agent.run(session_id="s1", state={"project": {"name": "审核中心"}}, out_dir=out_dir)
    assert out["presentation"]["html_url"].endswith(".html")
    assert os.path.exists(os.path.join(out_dir, "s1.html"))
    assert os.path.exists(os.path.join(out_dir, "s1.pptx"))
