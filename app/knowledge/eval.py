"""RAG 质量评估:对 gold Q&A 算 precision@k / recall@k;可选 faithfulness。"""
from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class RAGEvaluator:
    # 仅作冒烟默认:expected_chunk_ids 为空,真实评估需传入带标注的 gold
    DEFAULT_GOLD: List[dict] = [
        {"query": "内容安全 违规", "expected_chunk_ids": []},
        {"query": "咖啡 烘焙", "expected_chunk_ids": []},
        {"query": "用户反馈 投诉", "expected_chunk_ids": []},
    ]

    def load_gold(self, payload) -> List[dict]:
        if not isinstance(payload, list):
            raise ValueError("gold 必须是列表")
        for item in payload:
            if not isinstance(item, dict) or not item.get("query"):
                raise ValueError("gold 每项需含非空 query")
        return payload

    def evaluate(self, service, gold=None, top_k: int = 5,
                 project_id: Optional[str] = None, with_faithfulness: bool = False) -> dict:
        gold = self.load_gold(gold if gold is not None else self.DEFAULT_GOLD)
        if not gold:
            raise ValueError("gold 为空")
        per_item = []
        p_sum = r_sum = 0.0
        for item in gold:
            retrieved = service.retrieve(item["query"], top_k=top_k, project_id=project_id)
            got = {r["chunk_id"] for r in retrieved}
            expected = set(item.get("expected_chunk_ids") or [])
            hit = len(got & expected)
            precision = hit / min(top_k, len(retrieved)) if retrieved else 0.0
            recall = (hit / len(expected)) if expected else (1.0 if not retrieved else 0.0)
            entry = {"query": item["query"], "precision@k": precision, "recall@k": recall}
            if with_faithfulness and expected:
                try:
                    from app.knowledge.answer import RAGAnswerGenerator
                    # 注:默认 RAG_LLM_PROVIDER=mock 时生成会降级,faithfulness 仅 best-effort
                    gen = RAGAnswerGenerator(service=service)
                    out = gen.answer(item["query"], project_id=project_id, top_k=top_k)
                    entry["faithfulness"] = out.get("metrics", {}).get("citation_rate", None)
                except Exception as e:
                    logger.warning("faithfulness 计算失败: %s", e)
                    entry["faithfulness"] = None
            per_item.append(entry)
            p_sum += precision
            r_sum += recall
        n = len(per_item)
        result = {
            "precision@k": round(p_sum / n, 4) if n else 0.0,
            "recall@k": round(r_sum / n, 4) if n else 0.0,
            "n": n,
            "per_item": per_item,
        }
        return result
