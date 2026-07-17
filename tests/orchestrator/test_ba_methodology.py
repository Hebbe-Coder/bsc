# tests/orchestrator/test_ba_methodology.py
"""Task 3: 验证 BusinessArchitectAgent 接入方法论检索并透传 source_ref 引用。"""
import asyncio
from app.orchestrator.methodology import MethodologyBridge
from app.orchestrator.agents.business_architect import BusinessArchitectAgent


class FakeLLM:
    def __init__(self, payload):
        self._p = payload

    def chat(self, system_prompt, user_prompt, temperature=0.1, max_tokens=None, use_cache=True):
        return self._p


class FakeService:
    """鸭子类型检索服务：返回固定 2 个 chunk（chunk_id 为 c1/c2）。"""

    def __init__(self):
        self.calls = 0

    def retrieve(self, project_id=None, query=None, top_k=5):
        self.calls += 1
        return [
            {"chunk_id": "c1", "doc_title": "零售运营规范", "section": "第1章",
             "idx": 0, "score": 0.9, "content": "门店收货验收标准"},
            {"chunk_id": "c2", "doc_title": "零售运营规范", "section": "第2章",
             "idx": 1, "score": 0.8, "content": "退货与换货流程"},
        ]


class FakeCompile:
    async def __call__(self, prd, llm_service=None, **kw):
        return {"functions": [{"name": "受理"}], "roles": [{"name": "审核员"}]}


def _make_agent(payload, service=None):
    bridge = MethodologyBridge(service=service if service is not None else FakeService())
    return BusinessArchitectAgent(llm_service=FakeLLM(payload), bridge=bridge), bridge._service


def test_source_ref_survives_and_maps_to_retrieved():
    payload = {"business_model": {"flows": [{
        "id": "f1", "name": "受理", "description": "", "steps": [],
        "input": "", "output": "", "source_ref": ["c1"]}],
        "roles": [], "rules": []}}
    service = FakeService()
    agent, _ = _make_agent(payload, service)
    result = asyncio.run(agent.run(
        idea="内容审核中心", project={"name": "内容审核中心"},
        requirements=[], _compile=FakeCompile(), project_id="p1"))

    assert result["business_model"]["flows"][0]["source_ref"] == ["c1"]
    # 验证 c1 确实在检索结果中
    assert service.calls == 1
    assert "c1" in [c["chunk_id"] for c in service.retrieve(project_id="p1", query="x")]


def test_no_retrieval_when_no_project_id():
    payload = {"business_model": {"flows": [{
        "id": "f1", "name": "受理", "description": "", "steps": [],
        "input": "", "output": "", "source_ref": ["c1"]}],
        "roles": [], "rules": []}}
    service = FakeService()
    agent, _ = _make_agent(payload, service)
    result = asyncio.run(agent.run(
        idea="内容审核中心", project={"name": "内容审核中心"},
        requirements=[], _compile=FakeCompile()))

    # 未传 project_id：不应触发检索
    assert service.calls == 0
    assert result["business_model"]["flows"][0]["source_ref"] == ["c1"]
