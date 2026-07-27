"""RRF 融合 + Reranker 抽象（本地 cross-encoder / 云端 / Mock）。"""
from __future__ import annotations
import base64
import hashlib
import logging
from typing import List, Dict, Optional

from cryptography.fernet import Fernet

from app.core.config import settings
from app.knowledge.knowledge_domains import get_domain_registry

logger = logging.getLogger(__name__)


def _b64key(master: str) -> bytes:
    """任意长度主密钥经 sha256→32 字节→urlsafe_b64 规整为 Fernet 合法 key。"""
    return base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())


def _encrypt_key(plain: str, master: str) -> str:
    return Fernet(_b64key(master)).encrypt(plain.encode()).decode()


def _decrypt_key(token: str, master: str) -> str:
    return Fernet(_b64key(master)).decrypt(token.encode()).decode()


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
    """确定性重排：保持原始顺序，只做阈值过滤和域匹配增强。"""
    name = "mock"

    def rerank(self, query, candidates, top_k):
        q_tokens = [t for t in (query or "").lower().split() if t]
        if not q_tokens:
            return candidates[:top_k]

        registry = get_domain_registry()
        query_domains = registry.infer_from_query(query)

        scored = []
        for c in candidates:
            text = (c.get("content") or "").lower()
            title = (c.get("doc_title") or "").lower()
            
            has_content_match = any(t in text for t in q_tokens)
            has_title_match = any(t in title for t in q_tokens)
            
            domain_match_bonus = 0
            if query_domains and query_domains != ["general"]:
                chunk_domain = c.get("domain") or registry.infer_from_doc_title(c.get("doc_title", ""))
                if chunk_domain in query_domains:
                    domain_match_bonus = 1.0
            
            base_score = c.get("score", 0.0)
            bonus = 0.5 if has_title_match else 0
            bonus += 0.3 if has_content_match else 0
            bonus += domain_match_bonus
            
            scored.append(dict(c, rerank_score=base_score + bonus))
        
        scored.sort(key=lambda x: -x["rerank_score"])
        
        filtered = [c for c in scored if c["rerank_score"] > 0.01]
        
        return filtered[:top_k]


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


def _normalize_keys(keys) -> Optional[list]:
    """归一化 keys 为 list：单个字符串 → [字符串]（避免被逐字符拆分）；None/空 → None。"""
    if not keys:
        return None
    if isinstance(keys, (list, tuple)):
        return list(keys)
    return [keys]


def _build(provider: Optional[str], keys=None, model: str = None) -> Reranker:
    """按 provider 实际构建 reranker（none/false/""/off→NoOp；mock→Mock；local→Local；cloud→Cloud；其它→NoOp）。"""
    provider = (provider or "none").lower()
    if provider in ("none", "false", "", "off"):
        return NoOpReranker()
    if provider == "mock":
        return MockReranker()
    if provider == "local":
        return LocalCrossEncoderReranker(model_name=model or settings.RERANK_MODEL)
    if provider == "cloud":
        from app.knowledge.cloud_reranker import CloudReranker
        return CloudReranker(keys=_normalize_keys(keys) or list(settings.RERANK_KEYS or []))
    return NoOpReranker()


def get_reranker(provider: Optional[str] = None, keys=None, model: str = None,
                 project_id: Optional[str] = None, repo=None) -> Reranker:
    # 1. 显式传 provider → 直接按 provider 构建（保持旧行为）。
    if provider:
        return _build(provider, keys=keys, model=model)
    # 2. 传了 project_id 且 repo 非 None → 走项目配置。
    get_project = getattr(repo, "get_project", None) if repo is not None else None
    if project_id and callable(get_project):
        proj = get_project(project_id)
        cfg = (proj or {}).get("rerank_config") if proj else None
        if isinstance(cfg, dict) and cfg.get("enabled") and cfg.get("provider"):
            pkeys = keys
            if cfg.get("keys_encrypted") and settings.RERANK_KEY_MASTER:
                try:
                    pkeys = _decrypt_key(cfg["keys_encrypted"], settings.RERANK_KEY_MASTER)
                except Exception as e:
                    logger.warning("项目云端 rerank key 解密失败, 静默降级: %s", e)
                    pkeys = None
            return _build(cfg["provider"], keys=pkeys, model=cfg.get("model"))
    # 3. 回退全局 settings。
    return _build(settings.RERANK_PROVIDER, keys=settings.RERANK_KEYS, model=settings.RERANK_MODEL)
