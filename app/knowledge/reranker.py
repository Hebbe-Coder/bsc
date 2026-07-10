"""RRF 融合 + Reranker 抽象（本地 cross-encoder / 云端 / Mock）。"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List[tuple]:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


class Reranker:
    name = "base"

    def rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        raise NotImplementedError


class NoOpReranker(Reranker):
    """原序透传（rerank 关闭或降级时）。"""
    name = "none"

    def rerank(self, query, candidates, top_k):
        return candidates[:top_k]


class MockReranker(Reranker):
    """确定性重排：按 query 词在 content 中的命中数降序，便于测试断言。"""
    name = "mock"

    def rerank(self, query, candidates, top_k):
        q_tokens = [t for t in (query or "").lower().split() if t]

        def score(c):
            text = (c.get("content") or "").lower()
            return float(sum(text.count(t) for t in q_tokens))

        ranked = [dict(c, rerank_score=score(c)) for c in candidates]
        ranked.sort(key=lambda x: -x["rerank_score"])
        return ranked[:top_k]


class LocalCrossEncoderReranker(Reranker):
    """懒加载 cross-encoder；导入/推理失败 → 自动降级返回原序，绝不抛异常。"""
    name = "local"

    def __init__(self, model_name: str = ""):
        self.model_name = model_name or settings.RERANK_MODEL
        self._model = None  # None=未加载; False=加载失败

    def _ensure(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning("本地 reranker 加载失败, 将降级原序: %s", e)
                self._model = False
        return self._model

    def rerank(self, query, candidates, top_k):
        model = self._ensure()
        if not model:
            return candidates[:top_k]
        try:
            pairs = [(query, c.get("content") or "") for c in candidates]
            scores = model.predict(pairs)
            scored = [dict(c, rerank_score=float(s)) for c, s in zip(candidates, scores)]
            scored.sort(key=lambda x: -x["rerank_score"])
            return scored[:top_k]
        except Exception as e:
            logger.warning("本地 rerank 推理失败, 降级原序: %s", e)
            return candidates[:top_k]


def get_reranker(provider: Optional[str] = None, keys=None, model: str = None) -> Reranker:
    provider = (provider or settings.RERANK_PROVIDER or "none").lower()
    if provider in ("none", "false", "", "off"):
        return NoOpReranker()
    if provider == "mock":
        return MockReranker()
    if provider == "local":
        return LocalCrossEncoderReranker(model_name=model or settings.RERANK_MODEL)
    if provider == "cloud":
        from app.knowledge.cloud_reranker import CloudReranker
        return CloudReranker(keys=keys or list(settings.RERANK_KEYS or []))
    return NoOpReranker()
