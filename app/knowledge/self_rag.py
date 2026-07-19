"""Self-RAG：让 LLM 自我评估检索结果的相关性，必要时重新检索。

生产级 RAG 的核心组件：
- 让 LLM 判断检索结果是否足够回答问题
- 如果不够，生成更精确的查询重新检索
- 支持多轮检索直到找到满意的结果
- 减少幻觉，提升答案准确性
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.knowledge.query_rewrite import get_query_rewriter
from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)

SELF_RAG_PROMPT = """你是一个专业的检索评估专家，负责判断检索到的文档是否足够回答用户的问题。

任务：
1. 评估检索结果的相关性
2. 如果结果足够回答问题，输出 "SUFFICIENT"
3. 如果结果不够或不相关，输出 "INSUFFICIENT" 并提供一个更精确的查询词

请输出 JSON 格式：
{
  "decision": "SUFFICIENT" 或 "INSUFFICIENT",
  "confidence": 0.0-1.0,
  "reason": "判断理由",
  "rewritten_query": "更精确的查询词（仅当 decision=INSUFFICIENT 时需要）"
}

示例：
输入问题："如何降低客服投诉率？"
检索结果：["内容安全管理规范", "违规处罚机制"]
输出：{
  "decision": "INSUFFICIENT",
  "confidence": 0.8,
  "reason": "检索结果主要涉及内容安全和违规处理，没有直接涉及客服投诉率的降低方法",
  "rewritten_query": "客诉闭环管理机制 用户满意度提升"
}

输入问题："内容安全违规有哪些类型？"
检索结果：["内容安全管理规范 - 违规定义", "违规处罚机制"]
输出：{
  "decision": "SUFFICIENT",
  "confidence": 0.95,
  "reason": "检索结果包含违规定义，足够回答用户问题",
  "rewritten_query": ""
}

用户问题：{question}

检索结果摘要：{context}
"""


class SelfRAG:
    def __init__(self, provider: str = "mock", max_retries: int = 3,
                 service: Optional[KnowledgeService] = None):
        self.provider = provider
        self.max_retries = max_retries
        self.service = service or KnowledgeService()
        self._llm_client = None
        self.rewriter = get_query_rewriter(mock=provider == "mock")

    def _get_llm(self):
        if self._llm_client is None:
            from app.services.sop_llm_client import SOPLLMClient
            self._llm_client = SOPLLMClient(self.provider)
        return self._llm_client

    def _build_context_summary(self, chunks: List[dict]) -> str:
        summaries = []
        for i, chunk in enumerate(chunks[:5]):
            snippet = (chunk.get("content") or "")[:100]
            summaries.append(f"{i+1}. [{chunk.get('doc_title', '')}] {chunk.get('section', '')}: {snippet}")
        return "\n".join(summaries)

    def _evaluate_relevance(self, question: str, chunks: List[dict]) -> Dict:
        if not chunks:
            return {
                "decision": "INSUFFICIENT",
                "confidence": 1.0,
                "reason": "未检索到任何结果",
                "rewritten_query": question,
            }

        if self.provider == "mock":
            return self._mock_evaluate(question, chunks)

        llm = self._get_llm()
        context = self._build_context_summary(chunks)
        user_prompt = f"问题：{question}\n\n检索结果：\n{context}"

        try:
            result = llm.chat_structured(SELF_RAG_PROMPT, user_prompt)
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning("Self-RAG 评估失败，降级为默认逻辑: %s", e)

        return self._fallback_evaluate(question, chunks)

    def _mock_evaluate(self, question: str, chunks: List[dict]) -> Dict:
        titles = [c.get("doc_title", "") for c in chunks]
        sections = [c.get("section", "") for c in chunks]

        if any("内容安全" in t and "违规" in s for t, s in zip(titles, sections)):
            if "违规" in question or "安全" in question:
                return {
                    "decision": "SUFFICIENT",
                    "confidence": 0.9,
                    "reason": "检索结果包含相关的内容安全和违规信息",
                    "rewritten_query": "",
                }

        if any("咖啡" in t and "烘焙" in s for t, s in zip(titles, sections)):
            if "咖啡" in question or "烘焙" in question:
                return {
                    "decision": "SUFFICIENT",
                    "confidence": 0.9,
                    "reason": "检索结果包含相关的咖啡烘焙信息",
                    "rewritten_query": "",
                }

        if any("教师" in t or "师资" in t for t in titles):
            if "教师" in question or "师资" in question or "流失" in question:
                return {
                    "decision": "SUFFICIENT",
                    "confidence": 0.9,
                    "reason": "检索结果包含相关的教师管理信息",
                    "rewritten_query": "",
                }

        return {
            "decision": "INSUFFICIENT",
            "confidence": 0.7,
            "reason": "检索结果与问题的相关性不足",
            "rewritten_query": self.rewriter.rewrite(question).get("rewritten_query", question),
        }

    def _fallback_evaluate(self, question: str, chunks: List[dict]) -> Dict:
        titles = [c.get("doc_title", "").lower() for c in chunks]
        question_lower = question.lower()

        for title in titles:
            if any(kw in title for kw in question_lower.split()):
                return {
                    "decision": "SUFFICIENT",
                    "confidence": 0.7,
                    "reason": "检索结果包含问题中的关键词",
                    "rewritten_query": "",
                }

        return {
            "decision": "INSUFFICIENT",
            "confidence": 0.5,
            "reason": "检索结果与问题相关性较低",
            "rewritten_query": question,
        }

    def retrieve_with_self_rag(self, question: str, project_id: str,
                               top_k: int = 5) -> Dict:
        query = question
        history = []

        for attempt in range(self.max_retries):
            chunks = self.service.retrieve(query, top_k=top_k, project_id=project_id)
            
            eval_result = self._evaluate_relevance(question, chunks)
            eval_result["attempt"] = attempt + 1
            eval_result["query_used"] = query
            eval_result["chunk_count"] = len(chunks)
            history.append(eval_result)

            if eval_result["decision"] == "SUFFICIENT":
                return {
                    "final_chunks": chunks,
                    "history": history,
                    "retries": attempt + 1,
                    "success": True,
                }

            if attempt < self.max_retries - 1 and eval_result.get("rewritten_query"):
                query = eval_result["rewritten_query"]
                logger.info("Self-RAG 重新检索: 尝试 %d -> 新查询: '%s'", attempt + 2, query)
            else:
                break

        return {
            "final_chunks": chunks,
            "history": history,
            "retries": attempt + 1,
            "success": False,
            "note": f"已达到最大重试次数 {self.max_retries}",
        }

    def answer(self, question: str, project_id: str, top_k: int = 5) -> Dict:
        rag_result = self.retrieve_with_self_rag(question, project_id, top_k=top_k)
        chunks = rag_result["final_chunks"]

        if not chunks:
            return {
                "answer": "依据现有知识无法回答",
                "citations": [],
                "degraded": True,
                "note": "未检索到相关知识",
                "self_rag": rag_result,
            }

        from app.knowledge.answer import RAGAnswerGenerator
        generator = RAGAnswerGenerator(provider=self.provider, service=self.service)
        answer_result = generator.answer(question, project_id=project_id, top_k=top_k)
        answer_result["self_rag"] = rag_result

        return answer_result


def get_self_rag(provider: str = "mock", max_retries: int = 3,
                 service: Optional[KnowledgeService] = None) -> SelfRAG:
    return SelfRAG(provider=provider, max_retries=max_retries, service=service)
