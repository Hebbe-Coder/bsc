"""稠密向量后端：增量索引 chunk 向量，检索时按余弦排序返回 chunk_id。

与 KeywordBackend / TfidfBackend 同接口：index(chunk_records) / search(query)->List[str]。
远程 embedding 失败 → 抛出 → 本后端捕获降级为空（不把 mock 向量误标入库）。
"""
from __future__ import annotations
import logging
from typing import List, Optional

import numpy as np

from app.knowledge.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


class VectorBackend:
    def __init__(self, repo, provider: Optional[EmbeddingProvider] = None):
        self.repo = repo
        self._provider = provider

    def _get_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        try:
            provider = self._get_provider()
        except Exception as e:
            logger.warning("vector provider 加载失败: %s", e)
            return
        try:
            texts = [r.get("content", "") for r in chunk_records]
            vectors = provider.embed(texts)
        except Exception as e:
            # 远程失败：抛出由此处捕获，本次不写向量（向量后端为空），不影响其他后端
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

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        try:
            provider = self._get_provider()
            qv = np.asarray(provider.embed([query])[0], dtype=np.float64)
        except Exception as e:
            logger.warning("vector 检索失败(返回空): %s", e)
            return []
        rows = self.repo._execute(
            "SELECT chunk_id, vector FROM knowledge_vectors WHERE model=?",
            (provider.name,)).fetchall()
        if not rows:
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
        return [cid for cid, _ in scored[:limit]]
