"""关键词后端：FTS5 trigram + BM25，不可用时退回 LIKE，再不行降级为空。"""
from __future__ import annotations
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class KeywordBackend:
    def __init__(self, repo):
        self.repo = repo
        self.enabled = True

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        rows = [(r["content"], r["doc_id"], r["id"]) for r in chunk_records]
        try:
            self.repo._executemany(
                "INSERT INTO knowledge_fts (content, doc_id, chunk_id) VALUES (?,?,?)", rows)
            self.repo._commit()
        except Exception as e:
            logger.warning("keyword index failed, disabling: %s", e)
            self.enabled = False

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not self.enabled or not query or not query.strip():
            return []
        # 多词查询按词 OR（trigram 子串匹配），单/多词都稳健
        import re as _re
        terms = [t for t in _re.split(r"\s+", query.strip()) if t]
        if not terms:
            return []
        q = " OR ".join('"%s"' % t.replace('"', " ") for t in terms)
        try:
            rows = self.repo._execute(
                "SELECT chunk_id, bm25(knowledge_fts) AS s FROM knowledge_fts "
                "WHERE knowledge_fts MATCH ? ORDER BY s LIMIT ?",
                (q, limit)).fetchall()
            return [r["chunk_id"] for r in rows]
        except Exception:
            # 退回 LIKE 兜底
            try:
                like = f"%{query}%"
                rows = self.repo._execute(
                    "SELECT id AS chunk_id FROM knowledge_chunks WHERE content LIKE ? LIMIT ?",
                    (like, limit)).fetchall()
                return [r["chunk_id"] for r in rows]
            except Exception:
                self.enabled = False
                return []
