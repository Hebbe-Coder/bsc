"""知识层门面：ingest / retrieve + 可插拔后端注册表。永不向上抛异常。"""
from __future__ import annotations
import hashlib
import logging
import re
from typing import List, Optional

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.chunker import chunk_text
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.backends.vector import VectorBackend
from app.core.config import settings
from app.knowledge.reranker import rrf_fuse, get_reranker

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self, db_path: Optional[str] = None, repo: Optional[KnowledgeRepository] = None):
        self.repo = repo or KnowledgeRepository(db_path)
        ensure_schema(self.repo)
        self.backends = {
            "keyword": KeywordBackend(self.repo),
            "tfidf": TfidfBackend(self.repo),
            "vector": VectorBackend(self.repo),
        }

    @staticmethod
    def _content_hash(text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _resolve_doc_id(self, doc_id: Optional[str], source: str,
                        project_id: str) -> str:
        if doc_id:
            return doc_id
        if source:
            return hashlib.sha256(f"{source}|{project_id}".encode()).hexdigest()[:16]
        return self.repo._generate_id()

    def _index_chunks(self, chunk_records: list) -> None:
        # 后端各自容错，单后端失败不影响其他
        for name in ("keyword", "tfidf", "vector"):
            try:
                self.backends[name].index(chunk_records)
            except Exception as e:
                logger.warning("%s index failed: %s", name, e)
                if name == "keyword":
                    self.backends["keyword"].enabled = False

    def ingest_text(self, text: str, project_id: str = "", asset_id: str = "",
                    title: str = "", source: str = "", doc_format: str = "text",
                    doc_id: Optional[str] = None) -> dict:
        """增量幂等写入单篇文档。

        返回 dict，含 doc_id / status / version；成功附 content_hash；
        跳过/错误时附 reason。永不上抛异常。
        """
        try:
            norm_text = (text or "").strip()
            if not norm_text:
                return {"status": "skipped", "reason": "empty"}
            content_hash = self._content_hash(norm_text)
            doc_id = self._resolve_doc_id(doc_id, source, project_id)

            existing = self.repo._execute(
                "SELECT id, content_hash, version FROM knowledge_docs WHERE id=?",
                (doc_id,)).fetchone()
            if existing and existing["content_hash"] == content_hash:
                return {"doc_id": doc_id, "status": "skipped",
                        "version": existing["version"], "reason": "unchanged",
                        "content_hash": content_hash}

            # 先切分并校验，再执行任何破坏性操作，避免更新时新内容无 chunk
            # 却已删除旧文档导致静默数据丢失。
            chunks = chunk_text(norm_text)
            if not chunks:
                return {"doc_id": doc_id, "status": "skipped",
                        "reason": "no_chunks", "content_hash": content_hash}

            if existing:
                # 内容变化且新内容有效：级联清旧 chunk 后重写，version 递增
                self.delete_document(doc_id)
                version = (existing["version"] or 1) + 1
                status = "updated"
            else:
                version = 1
                status = "ingested"

            self.repo._execute(
                "INSERT INTO knowledge_docs "
                "(id, project_id, asset_id, title, source, created_at, "
                " doc_format, content_hash, version) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (doc_id, project_id, asset_id, title, source, self.repo._now(),
                 doc_format, content_hash, version))
            chunk_records = []
            for i, ch in enumerate(chunks):
                cid = self.repo._generate_id()
                self.repo._execute(
                    "INSERT INTO knowledge_chunks "
                    "(id, doc_id, idx, content, section, metadata_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (cid, doc_id, i, ch.content, ch.section,
                     self.repo._json_dumps(ch.meta)))
                chunk_records.append({"id": cid, "content": ch.content,
                                      "doc_id": doc_id})
            self.repo._commit()
            self._index_chunks(chunk_records)
            return {"doc_id": doc_id, "status": status, "version": version,
                    "content_hash": content_hash}
        except Exception as e:
            logger.error("ingest_text failed: %s", e)
            return {"status": "error", "reason": str(e)}

    def ingest(self, text: str, project_id: str = "", asset_id: str = "",
               title: str = "", source: str = "") -> Optional[str]:
        res = self.ingest_text(text, project_id=project_id, asset_id=asset_id,
                               title=title, source=source)
        return res.get("doc_id")

    def _fetch_candidates(self, ids_with_scores, project_id: Optional[str] = None) -> List[dict]:
        """按 (chunk_id, score) 列表拉取候选结果。

        保留现有 retrieve 的候选拉取逻辑（SQL / 返回字段 / project 过滤 /
        doc_title 兜底）不变，仅抽成可复用方法。
        """
        results = []
        for cid, score in ids_with_scores:
            row = self.repo._execute(
                "SELECT c.content AS content, c.section AS section, c.idx AS idx, d.title AS doc_title "
                "FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
                "WHERE c.id=? AND d.project_id = ?",
                (cid, project_id or "")).fetchone()
            if row:
                results.append({
                    "chunk_id": cid,
                    "content": row["content"],
                    "section": row["section"] or "",
                    "idx": row["idx"] or 0,
                    "score": score,
                    "doc_title": row["doc_title"] or "未知来源",
                })
        return results

    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> List[dict]:
        if not query or not query.strip():
            return []
        if not project_id:                      # L1: 强隔离，project_id 必填
            return []
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        vec_ids = self.backends["vector"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
        if not fused:
            return []
        do_rerank = rerank if rerank is not None else settings.RERANK_ENABLED
        top_n = rerank_top_n if rerank_top_n is not None else settings.RERANK_TOP_N
        if top_n < top_k:
            top_n = top_k
        if do_rerank:
            try:
                candidates = self._fetch_candidates(fused[:top_n], project_id)
                return get_reranker().rerank(query, candidates, top_k)
            except Exception as e:
                logger.warning("rerank 失败, 回退融合顺序: %s", e)
        return self._fetch_candidates(fused[:top_k], project_id)

    def list_documents(self, project_id: Optional[str] = None,
                       limit: int = 100, offset: int = 0) -> dict:
        where = ""
        params: list = []
        if project_id:
            where = "WHERE d.project_id=? "
            params.append(project_id)
        rows = self.repo._execute(
            f"SELECT d.id, d.title, d.source, d.project_id, d.created_at, "
            f"COUNT(c.id) AS chunk_count "
            f"FROM knowledge_docs d LEFT JOIN knowledge_chunks c ON c.doc_id=d.id "
            f"{where}GROUP BY d.id ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
            tuple(params + [limit, offset])).fetchall()
        docs = [dict(r) for r in rows]
        total_row = self.repo._execute(
            f"SELECT COUNT(*) AS cnt FROM knowledge_docs d {where}", tuple(params)
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        return {"documents": docs, "total": total}

    def delete_document(self, doc_id: str) -> bool:
        if not self.repo._execute(
                "SELECT id FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone():
            return False
        chunk_ids = [r["id"] for r in self.repo._execute(
            "SELECT id FROM knowledge_chunks WHERE doc_id=?", (doc_id,)).fetchall()]
        for cid in chunk_ids:
            self.repo._execute("DELETE FROM knowledge_fts WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_tfidf WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_vectors WHERE chunk_id=?", (cid,))
        self.repo._execute("DELETE FROM knowledge_chunks WHERE doc_id=?", (doc_id,))
        self.repo._execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
        self.repo._commit()
        return True
