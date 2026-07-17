"""方法论检索桥接：为后续编译器 Agent 提供可注入、可单测的知识检索入口。

本模块不与数据库/向量库直接耦合，而是通过依赖注入的 KnowledgeService 取回
方法论文献分块，并将结果转换为「带溯源信息的引用列表 + 可读上下文块」，
二者形状与 app.knowledge.answer.build_context 保持一致，便于后续审计步骤统一消费。
"""
from __future__ import annotations

from typing import List, Optional


class MethodologyBridge:
    """桥接方法论知识库与编译器 Agent。"""

    def __init__(self, service=None):
        # 可注入的检索服务；None 时惰性构建默认 KnowledgeService()
        self._service = service

    def _get_service(self):
        if self._service is None:
            from app.knowledge.service import KnowledgeService
            self._service = KnowledgeService()
        return self._service

    def retrieve(self, project_id: Optional[str], query: str, top_k: int = 5) -> dict:
        """检索方法论文献并返回 {context_block, citations}。

        - project_id 为空或检索无结果时返回 {"context_block": "", "citations": []}。
        - 否则生成可读的 context_block（逐条列出分块的索引、文档标题、章节、
          偏移与摘要），以及 shape 与 build_context 一致的 citations 列表。
        """
        # 空 project_id 直接短路，避免误跨项目边界
        if not project_id:
            return {"context_block": "", "citations": []}

        # 使用关键字参数调用，兼容真实 KnowledgeService 与 FakeService 的不同形参顺序
        chunks = self._get_service().retrieve(
            project_id=project_id, query=query, top_k=top_k
        )
        if not chunks:
            return {"context_block": "", "citations": []}

        citations: List[dict] = []
        lines: List[str] = []
        for i, ch in enumerate(chunks, start=1):
            snippet = (ch.get("content") or "")[:200]
            offset = ch.get("idx", 0)
            citations.append({
                "index": i,
                "chunk_id": ch.get("chunk_id"),
                "doc_title": ch.get("doc_title"),
                "section": ch.get("section"),
                "offset": offset,
                "score": ch.get("score", 0.0),
                "snippet": snippet,
            })
            doc_title = ch.get("doc_title") or ""
            section = ch.get("section") or ""
            lines.append(
                f"[{i}] 《{doc_title}》{section} (offset={offset}): {snippet}"
            )

        context_block = "\n".join(lines)
        return {"context_block": context_block, "citations": citations}
