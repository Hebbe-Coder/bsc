"""稠密向量后端：增量索引 chunk 向量，检索时按余弦排序返回 chunk_id。

与 KeywordBackend / TfidfBackend 同接口：index(chunk_records) / search(query)->List[str]。
远程 embedding 失败 → 抛出 → 本后端捕获降级为空（不把 mock 向量误标入库）。
"""
from __future__ import annotations
import hashlib
import logging
from typing import List, Optional

import numpy as np

from app.knowledge.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

_CACHE_SIZE = 1000


class VectorBackend:
    def __init__(self, repo, provider: Optional[EmbeddingProvider] = None):
        self.repo = repo
        self._provider = provider
        self._cache = {}
        self._cache_order = []
        self._vector_cache = {}

    def _get_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    def _clear_cache(self):
        self._cache.clear()
        self._cache_order.clear()
        self._vector_cache.clear()

    def _cache_get(self, key: str):
        if key in self._cache:
            idx = self._cache_order.index(key)
            self._cache_order.pop(idx)
            self._cache_order.insert(0, key)
            return self._cache[key]
        return None

    def _cache_set(self, key: str, value):
        if key in self._cache:
            idx = self._cache_order.index(key)
            self._cache_order.pop(idx)
        elif len(self._cache_order) >= _CACHE_SIZE:
            oldest = self._cache_order.pop()
            self._cache.pop(oldest)
        self._cache_order.insert(0, key)
        self._cache[key] = value

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        self._clear_cache()
        try:
            provider = self._get_provider()
        except Exception as e:
            logger.warning("vector provider 加载失败: %s", e)
            return
        try:
            texts = [r.get("content", "") for r in chunk_records]
            vectors = provider.embed(texts)
        except Exception as e:
            logger.warning("vector embed 失败(整批跳过): %s", e)
            return
        rows = []
        for r, vec in zip(chunk_records, vectors):
            try:
                arr = np.asarray(vec, dtype=np.float32)
                rows.append((r["id"], provider.name, int(arr.shape[0]), arr.tobytes()))
            except Exception as e:
                logger.warning("vector 单条写入跳过 %s: %s", r.get("id"), e)
        if rows:
            try:
                self.repo._executemany(
                    "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, model, dim, vector) "
                    "VALUES (?,?,?,?)", rows)
                self.repo._commit()
            except Exception as e:
                logger.warning("vector 写入失败: %s", e)

    def search(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        
        cache_key = hashlib.sha256(f"{query}|{project_id}|{limit}".encode()).hexdigest()
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        
        try:
            provider = self._get_provider()
            qv = np.asarray(provider.embed([query])[0], dtype=np.float64)
        except Exception as e:
            logger.warning("vector 检索失败(返回空): %s", e)
            return []
        
        sql = ("SELECT v.chunk_id, v.vector FROM knowledge_vectors v "
               "JOIN knowledge_chunks c ON v.chunk_id=c.id "
               "WHERE v.model=?")
        params: list = [provider.name]
        if project_id:
            sql += " AND c.doc_id IN (SELECT id FROM knowledge_docs WHERE project_id=?)"
            params.append(project_id)
        rows = self.repo._execute(sql, tuple(params)).fetchall()
        if not rows:
            self._cache_set(cache_key, [])
            return []
        
        qnorm = np.linalg.norm(qv)
        scored = []
        for r in rows:
            try:
                cv = np.frombuffer(r["vector"], dtype=np.float32).astype(np.float64)
                if cv.shape[0] != qv.shape[0]:
                    continue
                cnorm = np.linalg.norm(cv)
                if qnorm == 0 or cnorm == 0:
                    continue
                sim = float(np.dot(qv, cv) / (qnorm * cnorm))
                if sim > 0:
                    scored.append((r["chunk_id"], sim))
            except Exception:
                continue
        
        scored.sort(key=lambda x: -x[1])
        result = [cid for cid, _ in scored[:limit]]
        self._cache_set(cache_key, result)
        return result

    def reindex_stale(self, project_id: Optional[str] = None) -> int:
        """清除 model 与当前 provider 不一致的陈旧向量行，返回清除数量。
        下次 ingest 该 doc 时会按新模型重写。"""
        try:
            provider = self._get_provider()
        except Exception:
            return 0
        sql = ("DELETE FROM knowledge_vectors "
               "WHERE model IS NOT NULL AND model <> ?")
        params: list = [provider.name]
        if project_id:
            # 清该项目下的陈旧向量；chunk 已不存在的孤行(无法归属任何项目)
            # 也视为陈旧一并清除。
            sql += (" AND (chunk_id IN (SELECT c.id FROM knowledge_chunks c "
                    "JOIN knowledge_docs d ON c.doc_id=d.id WHERE d.project_id=?) "
                    "OR chunk_id NOT IN (SELECT id FROM knowledge_chunks))")
            params.append(project_id)
        cur = self.repo._execute(sql, tuple(params))
        self.repo._commit()
        return cur.rowcount if hasattr(cur, "rowcount") else 0
