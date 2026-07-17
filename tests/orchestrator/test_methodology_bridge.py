"""MethodologyBridge 单元测试：使用 FakeService 注入，避免依赖真实 DB/向量库。"""
from __future__ import annotations

from app.orchestrator.methodology import MethodologyBridge


class FakeService:
    """鸭子类型检索服务，仅返回预设分块，便于断言桥接层行为。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def retrieve(self, project_id, query, top_k=5, **kw):
        return self._chunks


def _make_chunk(chunk_id, content, section, idx, score, doc_title):
    return {
        "chunk_id": chunk_id,
        "content": content,
        "section": section,
        "idx": idx,
        "score": score,
        "doc_title": doc_title,
    }


def test_retrieve_returns_provenance_citations():
    chunks = [
        _make_chunk("c1", "敏捷迭代以短周期交付可运行软件。", "第2章", 3, 0.91, "敏捷方法论"),
        _make_chunk("c2", "看板通过限制在制品暴露瓶颈。", "第4章", 7, 0.85, "精益实践"),
    ]
    bridge = MethodologyBridge(service=FakeService(chunks))
    out = bridge.retrieve("p1", "如何做迭代交付", top_k=5)

    assert out["citations"], "应返回非空引用列表"
    first = out["citations"][0]
    for key in ("chunk_id", "doc_title", "section", "offset", "score", "snippet"):
        assert key in first, f"引用缺少字段 {key}"
    assert first["offset"] == chunks[0]["idx"], "offset 应等于分块 idx"
    assert out["context_block"], "context_block 不应为空"
    assert "敏捷方法论" in out["context_block"], "context_block 应包含文档标题"


def test_retrieve_empty_when_no_project_or_no_results():
    # 1) project_id 为 None -> 空形状
    bridge = MethodologyBridge(service=FakeService([]))
    assert bridge.retrieve(None, "q") == {"context_block": "", "citations": []}

    # 2) project_id 存在但检索无结果 -> 同样为空形状
    bridge2 = MethodologyBridge(service=FakeService([]))
    assert bridge2.retrieve("p1", "q") == {"context_block": "", "citations": []}
