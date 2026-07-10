"""LangChain 工具：agent 自主调用，把 top-k 知识格式化为带出处的上下文。"""
from __future__ import annotations
import logging
from typing import Optional

from langchain_core.tools import BaseTool

from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)


class RetrieveKnowledgeTool(BaseTool):
    name: str = "knowledge_retrieve"
    description: str = (
        "检索企业知识库中与查询相关的文档片段，返回带出处标注的上下文，"
        "用于增强业务系统生成。输入 query（查询语句）与可选 top_k（返回条数，默认5），"
        "以及可选 project_id（项目隔离ID，用于按项目隔离知识范围）。"
    )
    _service: Optional[KnowledgeService] = None

    def __init__(self, service: Optional[KnowledgeService] = None, **kwargs):
        super().__init__(**kwargs)
        self._service = service

    def _run(self, query: str, top_k: int = 5, project_id: Optional[str] = None) -> str:
        try:
            svc = self._service or KnowledgeService()
            results = svc.retrieve(query, top_k=top_k, project_id=project_id)
        except Exception as e:
            logger.warning("retrieve tool failed: %s", e)
            return "未检索到相关知识。"
        if not results:
            return "未检索到相关知识。"
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[知识 {i}] 出处：{r['doc_title']} / {r['section']}\n{r['content']}")
        return "\n\n".join(parts)

    async def _arun(self, query: str, top_k: int = 5, project_id: Optional[str] = None) -> str:
        return self._run(query, top_k=top_k, project_id=project_id)
