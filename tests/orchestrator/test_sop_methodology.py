# tests/orchestrator/test_sop_methodology.py
"""Task 2: 验证 SopBuilderAgent 接入方法论检索并透传 source_ref 引用。"""
from app.orchestrator.methodology import MethodologyBridge
from app.orchestrator.agents.sop_builder import SopBuilderAgent


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


class FakeSopEngine:
    def generate_full_sop_report(self, business_system, enable_ai_analysis=False):
        return {"workflow": [], "roles": [], "sla": []}


def _make_agent(payload, service=None):
    bridge = MethodologyBridge(service=service if service is not None else FakeService())
    return SopBuilderAgent(llm_service=FakeLLM(payload), bridge=bridge), bridge._service


def test_source_ref_survives_and_maps_to_retrieved():
    payload = {"sop": {"sops": [{
        "id": "s1", "title": "T", "owner_role": "R", "trigger": "x",
        "steps": [], "escalation": "", "review_cycle": "",
        "covers_constraints": [], "source_ref": ["c1"],
    }]}}
    service = FakeService()
    agent, _ = _make_agent(payload, service)
    result = agent.run(business_model={"name": "零售"}, _engine=FakeSopEngine(), project_id="p1")

    assert result["sop"]["sops"][0]["source_ref"] == ["c1"]
    # 验证 c1 确实在检索结果中
    assert service.calls == 1
    assert "c1" in [c["chunk_id"] for c in service.retrieve(project_id="p1", query="x")]


def test_no_retrieval_when_no_project_id():
    payload = {"sop": {"sops": [{
        "id": "s1", "title": "T", "owner_role": "R", "trigger": "x",
        "steps": [], "escalation": "", "review_cycle": "",
        "covers_constraints": [], "source_ref": ["c1"],
    }]}}
    service = FakeService()
    agent, _ = _make_agent(payload, service)
    result = agent.run(business_model={"name": "零售"}, _engine=FakeSopEngine())

    # 未传 project_id：不应触发检索
    assert service.calls == 0
    assert result["sop"]["sops"][0]["source_ref"] == ["c1"]


def test_citation_coverage_attached():
    payload = {"sop": {"sops": [{
        "id": "s1", "title": "T", "owner_role": "R", "trigger": "x",
        "steps": [], "escalation": "", "review_cycle": "",
        "covers_constraints": [], "source_ref": ["c1"],
    }]}}
    service = FakeService()
    agent, _ = _make_agent(payload, service)
    result = agent.run(business_model={"name": "零售"}, _engine=FakeSopEngine(), project_id="p1")

    # 检索发生（citations 非空），应附加覆盖率指标；单个合法引用 -> 覆盖率 1.0
    # 指标内联进 sop 子段，引擎 out.get("sop") 入库时得以保留（顶层会被丢弃）
    assert service.calls == 1
    assert "_citation_coverage" in result["sop"]
    assert result["sop"]["_citation_coverage"]["coverage"] == 1.0
    assert result["sop"]["_citation_coverage"]["covered"] == 1
    assert result["sop"]["_citation_coverage"]["flagged"] == []
