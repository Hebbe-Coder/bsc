"""RAG 质量评估:对 gold Q&A 算 precision@k / recall@k / MRR / NDCG / F1;可选 faithfulness;支持自动生成 gold data。"""
from __future__ import annotations
import logging
import math
from typing import List, Optional

logger = logging.getLogger(__name__)


class RAGEvaluator:
    DEFAULT_GOLD: List[dict] = [
        {"query": "内容安全 违规", "expected_chunk_ids": []},
        {"query": "咖啡 烘焙", "expected_chunk_ids": []},
        {"query": "用户反馈 投诉", "expected_chunk_ids": []},
    ]

    def generate_gold_data(self, service, project_id: str, num_samples: int = 10) -> List[dict]:
        docs = service.list_documents(project_id=project_id)
        gold_data = []
        
        for doc in docs["documents"]:
            doc_title = doc.get("title", "")
            chunks = service._fetch_candidates(
                [(cid, 1.0) for cid in 
                 [r["id"] for r in service.repo._execute(
                     "SELECT id FROM knowledge_chunks WHERE doc_id=?", 
                     (doc["id"],)).fetchall()]
                ],
                project_id
            )
            
            for chunk in chunks[:3]:
                chunk_id = chunk["chunk_id"]
                section = chunk.get("section", "")
                content = chunk.get("content", "")[:100]
                
                queries = []
                if section:
                    queries.append(f"{doc_title} {section}")
                    queries.append(f"{section} 是什么")
                if content:
                    keywords = self._extract_keywords(content)
                    if keywords:
                        queries.append(" ".join(keywords[:3]))
                
                for query in queries[:2]:
                    gold_data.append({
                        "query": query,
                        "expected_chunk_ids": [chunk_id],
                        "doc_title": doc_title,
                        "section": section,
                    })
        
        return gold_data[:num_samples]

    def _extract_keywords(self, text: str) -> List[str]:
        import re
        chinese_pattern = re.compile(r"[\u4e00-\u9fa5]{2,}")
        english_pattern = re.compile(r"[a-zA-Z]+")
        keywords = []
        keywords.extend(chinese_pattern.findall(text))
        keywords.extend(english_pattern.findall(text))
        return list(set(keywords))

    def load_gold(self, payload) -> List[dict]:
        if not isinstance(payload, list):
            raise ValueError("gold 必须是列表")
        for item in payload:
            if not isinstance(item, dict) or not item.get("query"):
                raise ValueError("gold 每项需含非空 query")
        return payload

    def _compute_mrr(self, retrieved_ids: list, expected_ids: set) -> float:
        if not expected_ids:
            return 1.0 if not retrieved_ids else 0.0
        for idx, rid in enumerate(retrieved_ids):
            if rid in expected_ids:
                return 1.0 / (idx + 1)
        return 0.0

    def _compute_ndcg(self, retrieved_ids: list, expected_ids: set, top_k: int) -> float:
        if not expected_ids:
            return 1.0 if not retrieved_ids else 0.0
        dcg = 0.0
        for idx, rid in enumerate(retrieved_ids[:top_k]):
            rel = 1.0 if rid in expected_ids else 0.0
            dcg += rel / math.log2(idx + 2)
        ideal_rank = list(expected_ids)[:top_k]
        idcg = sum(1.0 / math.log2(i + 2) for i in range(len(ideal_rank)))
        return round(dcg / idcg, 4) if idcg > 0 else 0.0

    def _compute_f1(self, precision: float, recall: float) -> float:
        if precision + recall == 0:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    def evaluate(self, service, gold=None, top_k: int = 5,
                 project_id: Optional[str] = None, with_faithfulness: bool = False,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> dict:
        gold = self.load_gold(gold if gold is not None else self.DEFAULT_GOLD)
        if not gold:
            raise ValueError("gold 为空")
        per_item = []
        p_sum = r_sum = mrr_sum = ndcg_sum = f1_sum = 0.0
        for item in gold:
            retrieved = service.retrieve(item["query"], top_k=top_k, project_id=project_id,
                                          rerank=rerank, rerank_top_n=rerank_top_n)
            retrieved_ids = [r["chunk_id"] for r in retrieved]
            got = set(retrieved_ids)
            expected = set(item.get("expected_chunk_ids") or [])
            hit = len(got & expected)
            precision = hit / min(top_k, len(retrieved)) if retrieved else 0.0
            recall = (hit / len(expected)) if expected else (1.0 if not retrieved else 0.0)
            f1 = self._compute_f1(precision, recall)
            mrr = self._compute_mrr(retrieved_ids, expected)
            ndcg = self._compute_ndcg(retrieved_ids, expected, top_k)
            
            entry = {
                "query": item["query"],
                "precision@k": precision,
                "recall@k": recall,
                "f1@k": f1,
                "mrr": mrr,
                "ndcg@k": ndcg,
            }
            if with_faithfulness:
                try:
                    from app.knowledge.answer import RAGAnswerGenerator
                    gen = RAGAnswerGenerator(service=service)
                    out = gen.answer(item["query"], project_id=project_id, top_k=top_k,
                                     rerank=rerank, rerank_top_n=rerank_top_n)
                    entry["faithfulness"] = out.get("metrics", {}).get("citation_rate", None)
                except Exception as e:
                    logger.warning("faithfulness 计算失败: %s", e)
                    entry["faithfulness"] = None
            per_item.append(entry)
            p_sum += precision
            r_sum += recall
            f1_sum += f1
            mrr_sum += mrr
            ndcg_sum += ndcg
        n = len(per_item)
        result = {
            "precision@k": round(p_sum / n, 4) if n else 0.0,
            "recall@k": round(r_sum / n, 4) if n else 0.0,
            "f1@k": round(f1_sum / n, 4) if n else 0.0,
            "mrr": round(mrr_sum / n, 4) if n else 0.0,
            "ndcg@k": round(ndcg_sum / n, 4) if n else 0.0,
            "n": n,
            "per_item": per_item,
        }
        return result

    def compare_before_after(self, service, gold=None, top_k: int = 5,
                             project_id: Optional[str] = None,
                             rerank_top_n: Optional[int] = None) -> dict:
        before = self.evaluate(service, gold, top_k=top_k, project_id=project_id, rerank=False)
        after = self.evaluate(service, gold, top_k=top_k, project_id=project_id,
                              rerank=True, rerank_top_n=rerank_top_n)
        bp, br, bf1 = before["precision@k"], before["recall@k"], before["f1@k"]
        ap, ar, af1 = after["precision@k"], after["recall@k"], after["f1@k"]
        bmrr, bndcg = before["mrr"], before["ndcg@k"]
        amrr, andcg = after["mrr"], after["ndcg@k"]
        return {
            "before": before,
            "after": after,
            "delta_precision": round(ap - bp, 4),
            "delta_recall": round(ar - br, 4),
            "delta_f1": round(af1 - bf1, 4),
            "delta_mrr": round(amrr - bmrr, 4),
            "delta_ndcg": round(andcg - bndcg, 4),
            "rerank_not_worse": (ap >= bp - 1e-9) and (ar >= br - 1e-9),
        }
