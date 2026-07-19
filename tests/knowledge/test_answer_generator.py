import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService
from app.knowledge.answer import RAGAnswerGenerator


class _FakeLLM:
    """模拟 SOPLLMClient.chat_structured:单阶段返回带 [1] 的 answer。"""
    provider = "fake"

    def chat_structured(self, system_prompt, user_prompt, **kw):
        return {"answer": "依据[1]可知需要加强审核。"}


class _FakeLLMTwoPhase:
    provider = "fake"
    calls = 0

    def chat_structured(self, system_prompt, user_prompt, **kw):
        self.calls += 1
        if "cite_ids" in system_prompt:
            return {"cite_ids": [1]}
        return {"answer": "依据[1]作答。"}


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_build_context_groups_by_section():
    gen = RAGAnswerGenerator()
    ctx, cites = gen.build_context([
        {"chunk_id": "a", "content": "内容安全 审核", "section": "合规", "idx": 0, "score": 0.5, "doc_title": "D"},
        {"chunk_id": "b", "content": "咖啡 烘焙", "section": "合规", "idx": 1, "score": 0.3, "doc_title": "D"},
    ])
    assert "[章节：合规]" in ctx
    assert cites[0]["index"] == 1 and cites[1]["index"] == 2
    assert cites[0]["section"] == "合规"


def test_answer_mock_returns_citations_degraded():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息", project_id="p1", title="A")
    gen = RAGAnswerGenerator(service=svc, provider="mock")
    out = gen.answer("内容安全 违规", project_id="p1")
    assert out["answer"] == ""
    assert out["citations"]
    assert out["degraded"] is True


def test_answer_with_fake_llm_returns_cited():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    gen = RAGAnswerGenerator(service=svc, llm_client=_FakeLLM())
    out = gen.answer("内容安全 违规", project_id="p1")
    assert "审核" in out["answer"]
    assert out["citations"]
    assert "citation_rate" in out["metrics"]


def test_two_phase_only_cites_plan():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    fake = _FakeLLMTwoPhase()
    gen = RAGAnswerGenerator(service=svc, llm_client=fake, two_phase=True)
    out = gen.answer("内容安全 违规", project_id="p1")
    assert "[1]" in out["answer"]
    assert fake.calls == 2


def test_validate_citations_strips_invalid():
    gen = RAGAnswerGenerator()
    cleaned, rate = gen.validate_citations(
        "依据[1]和[9]处理", [{"index": 1}, {"index": 2}])
    assert "[9]" not in cleaned
    assert "[1]" in cleaned
    assert rate == 0.5


def test_generator_builds_llm_with_only_keys():
    gen = RAGAnswerGenerator(provider="deepseek", keys=["k1", "k2"])
    llm = gen._get_llm()  # 不应抛 SOPLLMError(多 Key 优先,无需单 api_key)
    assert llm.keys == ["k1", "k2"]
