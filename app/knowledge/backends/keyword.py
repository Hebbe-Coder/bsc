"""关键词后端：FTS5 trigram + BM25，不可用时退回 LIKE，再不行降级为空。"""
from __future__ import annotations
import logging
from typing import List, Optional

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

    def search(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[str]:
        if not self.enabled or not query or not query.strip():
            return []
        import re as _re
        terms = [t for t in _re.split(r"\s+", query.strip()) if t]
        if not terms:
            return []
        q = " OR ".join('"%s"' % t.replace('"', " ") for t in terms)
        pid_filter = ""
        params: list = [q]
        if project_id:
            pid_filter = (" AND chunk_id IN (SELECT c.id FROM knowledge_chunks c "
                          "JOIN knowledge_docs d ON c.doc_id=d.id WHERE d.project_id=?)")
            params.append(project_id)
        params.append(limit)
        try:
            rows = self.repo._execute(
                "SELECT chunk_id, bm25(knowledge_fts) AS s FROM knowledge_fts "
                f"WHERE knowledge_fts MATCH ?{pid_filter} ORDER BY s LIMIT ?",
                tuple(params)).fetchall()  # nosec B608 - pid_filter is hardcoded
            return [r["chunk_id"] for r in rows]
        except Exception:
            try:
                like = f"%{query}%"
                sql = "SELECT c.id AS chunk_id FROM knowledge_chunks c WHERE c.content LIKE ?"
                lparams: list = [like]
                if project_id:
                    sql += (" AND c.doc_id IN (SELECT id FROM knowledge_docs "
                            "WHERE project_id=?)")
                    lparams.append(project_id)
                sql += " LIMIT ?"
                lparams.append(limit)
                rows = self.repo._execute(sql, tuple(lparams)).fetchall()
                return [r["chunk_id"] for r in rows]
            except Exception:
                self.enabled = False
                return []
