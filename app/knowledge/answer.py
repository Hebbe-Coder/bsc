"""RAG 答案生成器: Agent Route → Query Rewrite → Self-RAG → 检索 → 分节上下文 → 多厂商 LLM 生成带 [n] 引用 → 引用校验 → Feedback 钩子。"""
from __future__ import annotations
import logging
import random
import re
from typing import List, Optional

from app.core.config import settings
from app.knowledge.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_citation_plan_prompt,
    build_answer_prompt,
)
from app.knowledge.query_rewrite import get_query_rewriter
from app.knowledge.agent_router import get_agent_router
from app.knowledge.self_rag import get_self_rag
from app.knowledge.feedback import get_feedback_store

logger = logging.getLogger(__name__)


class RAGAnswerGenerator:
    def __init__(
        self,
        provider: Optional[str] = None,
        service=None,
        llm_client=None,
        keys: Optional[List[str]] = None,
        two_phase: bool = False,
        enable_agent_router: bool = True,
        enable_self_rag: bool = True,
    ):
        self.provider = (provider or settings.RAG_LLM_PROVIDER or "mock").lower()
        self.service = service
        self._llm_client = llm_client
        self.keys = keys or list(getattr(settings, "RAG_LLM_KEYS", []) or [])
        self.two_phase = two_phase or bool(getattr(settings, "RAG_TWO_PHASE", False))
        self.enable_agent_router = enable_agent_router
        self.enable_self_rag = enable_self_rag
        self._trace_id = None

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

    @staticmethod
    def _serialize_route(route_result: Optional[dict]) -> Optional[dict]:
        if route_result is None:
            return None
        result = dict(route_result)
        result["tools"] = [
            {
                "tool_name": tool.tool_name,
                "params": tool.params,
                "status": tool.status,
            }
            if hasattr(tool, "tool_name") else tool
            for tool in result.get("tools", [])
        ]
        return result

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

    def _mock_generate_answer(self, question: str, citations: List[dict]) -> dict:
        if not citations:
            return {"answer": "依据现有知识无法回答", "citations": [], "metrics": {"citation_rate": 0.0}}
        
        available_indices = [c["index"] for c in citations]
        if len(available_indices) >= 3:
            selected = random.sample(available_indices, 3)
        else:
            selected = available_indices
        
        selected.sort()
        cite_marks = [f"[{i}]" for i in selected]
        
        answer_parts = []
        answer_parts.append(f"根据知识库内容，关于「{question}」的回答如下：")
        
        for idx in selected:
            cite = next((c for c in citations if c["index"] == idx), None)
            if cite:
                snippet = cite["snippet"][:50]
                answer_parts.append(f"- 要点{idx}：{snippet}...{cite_marks[selected.index(idx)]}")
        
        answer_parts.append(f"综上所述，结合引用的知识{''.join(cite_marks)}，可以得出结论。")
        
        answer_text = "\n".join(answer_parts)
        cleaned, rate = self.validate_citations(answer_text, citations)
        
        return {"answer": cleaned, "citations": citations, "metrics": {"citation_rate": rate}}

    def answer(self, question: str, project_id: Optional[str] = None, top_k: int = 5,
                rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None,
                enable_rewrite: bool = True, user_id: Optional[str] = None) -> dict:
        route_result = None
        rewrite_result = None
        self_rag_result = None

        if self.enable_agent_router:
            router = get_agent_router(mock=self.provider == "mock")
            route_result = router.route(question)
            logger.info("Agent Router: query='%s' -> intent='%s', router_decision='%s'", 
                        question, route_result.get("intent"), route_result.get("router_decision"))
            route_result = self._serialize_route(route_result)

        if enable_rewrite:
            rewriter = get_query_rewriter(mock=self.provider == "mock")
            rewrite_result = rewriter.rewrite(question)
            logger.info("Query Rewrite: %s -> %s (intent: %s)", 
                        question, rewrite_result.get("rewritten_query"), rewrite_result.get("intent"))

        search_query = rewrite_result.get("rewritten_query", question) if rewrite_result else question

        if self.enable_self_rag:
            self_rag = get_self_rag(provider=self.provider, service=self._get_service())
            self_rag_result = self_rag.retrieve_with_self_rag(search_query, project_id, top_k=top_k)
            chunks = self_rag_result["final_chunks"]
            logger.info("Self-RAG: retries=%d, success=%s", 
                        self_rag_result.get("retries", 1), self_rag_result.get("success", False))
        else:
            chunks = self._get_service().retrieve(
                search_query, top_k=top_k, project_id=project_id,
                rerank=rerank, rerank_top_n=rerank_top_n, user_id=user_id)

        if not chunks:
            return {
                "answer": "", 
                "citations": [], 
                "degraded": True, 
                "note": "未检索到相关知识",
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }

        context, citations = self.build_context(chunks)
        
        if self.provider == "mock" and self._llm_client is None:
            return {
                "answer": "",
                "citations": citations,
                "degraded": True,
                "note": "Mock provider returns retrieval context without generated content",
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }
        
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("RAG LLM 不可用,降级: %s", e)
            return {
                "answer": "", 
                "citations": citations, 
                "degraded": True, 
                "note": "无可用模型",
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }
        if getattr(llm, "provider", "mock") == "mock":
            return {
                "answer": "",
                "citations": citations,
                "degraded": True,
                "note": "Mock provider returns retrieval context without generated content",
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }
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
                return {
                    "answer": "", 
                    "citations": citations, 
                    "degraded": True, 
                    "note": "模型未返回答案",
                    "rewrite": rewrite_result,
                    "route": route_result,
                    "self_rag": self_rag_result,
                }
            cleaned, rate = self.validate_citations(answer_text, citations)
            return {
                "answer": cleaned, 
                "citations": citations, 
                "metrics": {"citation_rate": rate},
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }
        except Exception as e:
            logger.warning("RAG 答案生成失败,降级: %s", e)
            return {
                "answer": "", 
                "citations": citations, 
                "degraded": True, 
                "note": "生成失败,仅返回检索上下文",
                "rewrite": rewrite_result,
                "route": route_result,
                "self_rag": self_rag_result,
            }

    def add_feedback(self, trace_id: str, user_id: str, feedback_type: str,
                     query: str, answer: str, correction: Optional[str] = None,
                     comment: Optional[str] = None):
        store = get_feedback_store(mock=self.provider == "mock")
        return store.add_feedback(trace_id, user_id, feedback_type, query, answer, correction, comment)

    def get_feedback_stats(self):
        store = get_feedback_store(mock=self.provider == "mock")
        return store.get_stats()
