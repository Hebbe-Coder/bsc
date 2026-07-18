# tests/orchestrator/test_methodology_e2e.py
"""Task 5 黄金集成测试：验证 project_id 已贯穿 engine → sop/architect，
且编译器流水线能真正检索方法论、在 sop/business_model 上携带 source_ref 与 _citation_coverage；
无文档时优雅降级、不崩溃。
"""
from __future__ import annotations
import asyncio

from app.orchestrator.methodology import (
    MethodologyBridge,
    derive_methodology_query,
    validate_source_refs,
)
from app.orchestrator.engine import OrchestratorEngine

try:
    from tests.orchestrator.test_engine import FakeBus
except Exception:  # pragma: no cover
    class FakeBus:
        def __init__(self): self.events = []
        async def publish(self, session_id, event_type, **kwargs):
            self.events.append({"type": str(event_type), **kwargs})


class FakeLLM:
    """固定返回预设 payload 的假 LLM，仅提供 chat 接口。"""
    def __init__(self, payload): self._payload = payload
    def chat(self, system_prompt, user_prompt, temperature=0.1):
        return self._payload


class FakeService:
    """鸭子类型的知识检索服务：返回预设分块（或空列表以模拟无文档）。"""
    def __init__(self, chunks): self._chunks = chunks
    def retrieve(self, project_id=None, query=None, top_k=5):
        return self._chunks


class FakeSopAgent:
    """忠于此 real SopBuilderAgent 的方法论路径，但使用假 LLM，保证确定性。"""
    def __init__(self, llm: FakeLLM, bridge: MethodologyBridge):
        self.llm = llm
        self._bridge = bridge
    def run(self, business_model, _engine=None, context=None,
            fix_instructions=None, project_id=None) -> dict:
        citations = []
        if project_id and self._bridge:
            out = self._bridge.retrieve(project_id, derive_methodology_query(business_model))
            citations = out.get("citations") or []
        result = self.llm.chat("", "")
        # 仅当发生检索时附加溯源覆盖率（与真实 agent 行为一致，置于 sop 段内以便 engine 上抛）
        if citations:
            items = (result.get("sop") or {}).get("sops") or []
            result.setdefault("sop", {})["_citation_coverage"] = validate_source_refs(items, citations)
        return result


class FakeArchitectAgent:
    """忠于此 real BusinessArchitectAgent 的方法论路径，但使用假 LLM，保证确定性。"""
    def __init__(self, llm: FakeLLM, bridge: MethodologyBridge):
        self.llm = llm
        self._bridge = bridge
    async def run(self, idea, project, requirements, _compile=None, context=None,
                  fix_instructions=None, project_id=None) -> dict:
        citations = []
        if project_id and self._bridge:
            out = self._bridge.retrieve(project_id, derive_methodology_query(project))
            citations = out.get("citations") or []
        result = self.llm.chat("", "")
        if citations:
            bm = result.setdefault("business_model", {})
            items = (bm.get("flows") or []) + (bm.get("roles") or []) + (bm.get("rules") or [])
            bm["_citation_coverage"] = validate_source_refs(items, citations)
        return result


def _make_agents(sop_payload, bm_payload, bridge):
    # 流水线还会调用 planner/risk/reviewer/presenter，用最简 stub 补齐
    class Stub:
        def __init__(self, payload): self.payload = payload
        def run(self, *a, **k): return self.payload
        async def run_async(self, *a, **k): return self.payload
    return {
        "planner": Stub({"project": {"name": "奶茶店"}, "requirements": []}),
        "architect": FakeArchitectAgent(FakeLLM(bm_payload), bridge),
        "sop": FakeSopAgent(FakeLLM(sop_payload), bridge),
        "risk": Stub({"risk": {"overall_score": "low", "coverage": {"total": 0, "covered": 0, "coverage_pct": 100, "uncovered_ids": []}, "gate": {"decision": "pass", "reasons": []}, "audit": []}}),
        "reviewer": Stub({"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}),
        "presenter": Stub({"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}),
    }


def test_pipeline_carries_source_ref_with_docs(draft_repo):
    # 两个 chunk：c1/c2；sop 与 business_model 均引用 c1
    chunks = [
        {"chunk_id": "c1", "doc_title": "奶茶店运营手册", "section": "SOP", "idx": 0, "score": 0.9, "content": "出杯标准"},
        {"chunk_id": "c2", "doc_title": "奶茶店运营手册", "section": "风险", "idx": 1, "score": 0.8, "content": "食安"},
    ]
    bridge = MethodologyBridge(service=FakeService(chunks))
    sop_payload = {"sop": {"sops": [{"id": "s1", "title": "T", "owner_role": "R", "trigger": "x",
                                    "steps": [], "escalation": "", "review_cycle": "",
                                    "covers_constraints": [], "source_ref": ["c1"]}]}}
    bm_payload = {"business_model": {"flows": [{"id": "f1", "name": "出杯", "description": "x",
                                               "steps": ["a"], "input": "i", "output": "o",
                                               "source_ref": ["c1"]}], "roles": [], "rules": []}}
    eng = OrchestratorEngine(
        agents=_make_agents(sop_payload, bm_payload, bridge),
        repo=draft_repo,
        bus=FakeBus(),
    )
    result = asyncio.run(eng.run_pipeline("sess-1", "开个奶茶店"))

    # sop 携带 source_ref 与覆盖率
    assert result["sop"]["sops"][0]["source_ref"] == ["c1"]
    assert result["sop"]["_citation_coverage"]["coverage"] > 0
    # business_model 携带 source_ref 与覆盖率
    assert result["business_model"]["flows"][0]["source_ref"] == ["c1"]
    assert result["business_model"]["_citation_coverage"]["coverage"] > 0


def test_pipeline_degrades_without_docs(draft_repo):
    # 无文档：FakeService 返回空列表，流水线应优雅降级、不崩溃
    bridge = MethodologyBridge(service=FakeService([]))
    sop_payload = {"sop": {"sops": [{"id": "s1", "title": "T", "owner_role": "R", "trigger": "x",
                                    "steps": [], "escalation": "", "review_cycle": "",
                                    "covers_constraints": [], "source_ref": []}]}}
    bm_payload = {"business_model": {"flows": [{"id": "f1", "name": "出杯", "description": "x",
                                               "steps": ["a"], "input": "i", "output": "o",
                                               "source_ref": []}], "roles": [], "rules": []}}
    eng = OrchestratorEngine(
        agents=_make_agents(sop_payload, bm_payload, bridge),
        repo=draft_repo,
        bus=FakeBus(),
    )
    result = asyncio.run(eng.run_pipeline("sess-2", "开个奶茶店"))

    # SOP 仍被产出（sop agent 始终返回其输出）
    assert "sop" in result and result["sop"].get("sops")
    # 未检索时 _citation_coverage 要么缺失，要么覆盖率为 0（优雅、不抛异常）
    cov = result["sop"].get("_citation_coverage")
    assert cov is None or cov.get("coverage") == 0.0
