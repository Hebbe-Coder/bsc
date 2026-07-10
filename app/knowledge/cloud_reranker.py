"""云端 Reranker（Cohere/Jina 风格），多 key 故障转移，失败降级原序。"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.knowledge.reranker import Reranker

logger = logging.getLogger(__name__)

COHERE_URL = "https://api.cohere.ai/v2/rerank"


class CloudReranker(Reranker):
    name = "cloud"

    def __init__(self, provider: str = "cohere", keys: Optional[List[str]] = None,
                 base_url: Optional[str] = None):
        self.provider = provider
        self.keys = list(keys or [])
        self.base_url = base_url or COHERE_URL

    def _post(self, url, headers, json):
        import requests
        return requests.post(url, headers=headers, json=json, timeout=20)

    def _headers(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _payload(self, query: str, texts: List[str]) -> dict:
        return {"model": "rerank-english-v3.0", "query": query, "documents": texts, "top_n": len(texts)}

    def _extract(self, data: dict) -> List[tuple]:
        # Cohere/Jina: results 按相关度降序，每项含 index 指回原文位置。
        # 必须按 index 对齐，不能依赖列表顺序。
        return [(int(r["index"]), float(r["relevance_score"]))
                for r in data.get("results", [])]

    def rerank(self, query, candidates, top_k) -> List[Dict]:
        if not self.keys:
            logger.warning("cloud rerank 无 key, 降级原序")
            return candidates[:top_k]
        texts = [c.get("content") or "" for c in candidates]
        n = len(candidates)
        last_err = None
        for key in self.keys:
            try:
                resp = self._post(self.base_url, self._headers(key), self._payload(query, texts))
                pairs = self._extract(resp.json())
                if len(pairs) != n:
                    raise ValueError("云端返回分数数与候选不一致")
                scored = []
                for idx, s in pairs:
                    if 0 <= idx < n:
                        scored.append(dict(candidates[idx], rerank_score=s))
                if len(scored) != n:
                    raise ValueError("云端返回 index 越界或重复")
                scored.sort(key=lambda x: -x["rerank_score"])
                return scored[:top_k]
            except Exception as e:
                last_err = e
                logger.warning("cloud rerank key 失败, 尝试下一 key: %s", e)
        logger.warning("cloud rerank 全部 key 失败, 降级原序: %s", last_err)
        return candidates[:top_k]
