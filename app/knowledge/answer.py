"""RAG 答案生成器:检索 → 分节上下文 → 多厂商 LLM 生成带 [n] 引用 → 引用校验。"""
from __future__ import annotations
import logging
import re
from typing import List, Optional

from app.core.config import settings
from app.knowledge.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_citation_plan_prompt,
    build_answer_prompt,
)

logger = logging.getLogger(__name__)


class RAGAnswerGenerator:
    def __init__(
        self,
        provider: Optional[str] = None,
        service=None,
        llm_client=None,
        keys: Optional[List[str]] = None,
        two_phase: bool = False,
    ):
        self.provider = (provider or settings.RAG_LLM_PROVIDER or "mock").lower()
        self.service = service
        self._llm_client = llm_client
        self.keys = keys or list(getattr(settings, "RAG_LLM_KEYS", []) or [])
        self.two_phase = two_phase or bool(getattr(settings, "RAG_TWO_PHASE", False))

    def _get_llm(self):
        if self._llm_client is None:
            from app.services.sop_llm_client import SOPLLMClient
            self._llm_client = SOPLLMClient(self.provider, keys=self.keys)
        return self._llm_client

    def _get_service(self):
        if self.service is None:
            from app.knowledge.service import KnowledgeService
            self.service = KnowledgeService()
        return self.service

    def build_context(self, chunks: List[dict]):
        grouped = {}
        order = []
        for ch in chunks:
            sec = ch.get("section") or "未分节"
            if sec not in grouped:
                grouped[sec] = []
                order.append(sec)
            grouped[sec].append(ch)
        parts = []
        citations = []
        idx = 0
        for sec in order:
            parts.append(f"[章节：{sec}]")
            for ch in grouped[sec]:
                idx += 1
                snippet = (ch.get("content") or "")[:200]
                parts.append(f"[{idx}] {snippet}")
                citations.append({
                    "index": idx,
                    "chunk_id": ch.get("chunk_id"),
                    "doc_title": ch.get("doc_title"),
                    "section": sec,
                    "offset": ch.get("idx", 0),
                    "score": ch.get("score", 0.0),
                    "snippet": snippet,
                })
        return "\n\n".join(parts), citations

    def validate_citations(self, answer_text: str, citations: List[dict]):
        valid_ids = {c["index"] for c in citations}
        found = re.findall(r"\[(\d+)\]", answer_text or "")
        total = len(found)
        valid = 0
        cleaned = answer_text
        for n_str in found:
            n = int(n_str)
            if n in valid_ids:
                valid += 1
            else:
                cleaned = cleaned.replace(f"[{n}]", "")
        rate = (valid / total) if total else 0.0
        return cleaned, rate

    def answer(self, question: str, project_id: Optional[str] = None, top_k: int = 5,
                rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> dict:
        chunks = self._get_service().retrieve(
            question, top_k=top_k, project_id=project_id,
            rerank=rerank, rerank_top_n=rerank_top_n)
        if not chunks:
            return {"answer": "", "citations": [], "degraded": True, "note": "未检索到相关知识"}
        context, citations = self.build_context(chunks)
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("RAG LLM 不可用,降级: %s", e)
            return {"answer": "", "citations": citations, "degraded": True, "note": "无可用模型"}
        if getattr(llm, "provider", "mock") == "mock":
            return {"answer": "", "citations": citations, "degraded": True, "note": "未生成答案(无可用模型)"}
        try:
            if self.two_phase:
                plan = llm.chat_structured(build_citation_plan_prompt(question, context), question) or {}
                cite_ids = plan.get("cite_ids", []) if isinstance(plan, dict) else []
                raw = llm.chat_structured(build_answer_prompt(question, context, cite_ids), question)
            else:
                raw = llm.chat_structured(build_system_prompt(), build_user_prompt(question, context))
            data = raw or {}
            answer_text = data.get("answer", "")
            if not answer_text:
                return {"answer": "", "citations": citations, "degraded": True, "note": "模型未返回答案"}
            cleaned, rate = self.validate_citations(answer_text, citations)
            return {"answer": cleaned, "citations": citations, "metrics": {"citation_rate": rate}}
        except Exception as e:
            logger.warning("RAG 答案生成失败,降级: %s", e)
            return {"answer": "", "citations": citations, "degraded": True, "note": "生成失败,仅返回检索上下文"}
