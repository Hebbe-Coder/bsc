"""知识层门面：ingest / retrieve + 可插拔后端注册表。永不向上抛异常。"""
from __future__ import annotations
import logging
from typing import List, Optional

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.chunker import chunk_text
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.reranker import rrf_fuse

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self, db_path: Optional[str] = None, repo: Optional[KnowledgeRepository] = None):
        self.repo = repo or KnowledgeRepository(db_path)
        ensure_schema(self.repo)
        self.backends = {
            "keyword": KeywordBackend(self.repo),
            "tfidf": TfidfBackend(self.repo),
        }

    def ingest(self, text: str, project_id: str = "", asset_id: str = "",
               title: str = "", source: str = "") -> Optional[str]:
        text = (text or "").strip()
        if not text:
            return None
        try:
            chunks = chunk_text(text)
        except Exception as e:
            logger.warning("chunk failed: %s", e)
            return None
        if not chunks:
            return None
        doc_id = self.repo._generate_id()
        self.repo._execute(
            "INSERT INTO knowledge_docs (id, project_id, asset_id, title, source, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (doc_id, project_id, asset_id, title, source, self.repo._now()))
        chunk_records = []
        for i, ch in enumerate(chunks):
            cid = self.repo._generate_id()
            self.repo._execute(
                "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) "
                "VALUES (?,?,?,?,?,?)",
                (cid, doc_id, i, ch.content, ch.section, self.repo._json_dumps(ch.meta)))
            chunk_records.append({"id": cid, "content": ch.content, "doc_id": doc_id})
        self.repo._commit()
        # 后端各自容错，单后端失败不影响其他
        try:
            self.backends["keyword"].index(chunk_records)
        except Exception as e:
            logger.warning("keyword index failed: %s", e)
            self.backends["keyword"].enabled = False
        try:
            self.backends["tfidf"].index(chunk_records)
        except Exception as e:
            logger.warning("tfidf index failed: %s", e)
        return doc_id

    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None) -> List[dict]:
        if not query or not query.strip():
            return []
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids])
        top = fused[:top_k]
        if not top:
            return []
        results = []
        for cid in top:
            row = self.repo._execute(
                "SELECT c.content AS content, c.section AS section, d.title AS doc_title "
                "FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
                "WHERE c.id=? AND (? = '' OR d.project_id = ?)",
                (cid, project_id or "", project_id or "")).fetchone()
            if row:
                results.append({
                    "content": row["content"],
                    "section": row["section"],
                    "doc_title": row["doc_title"] or "未知来源",
                })
        return results
