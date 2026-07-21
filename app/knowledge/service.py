"""知识层门面：ingest / retrieve + 可插拔后端注册表 + 权限控制。永不向上抛异常。"""
from __future__ import annotations
import hashlib
import logging
import re
import time
from typing import List, Optional

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.chunker import chunk_text
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.backends.vector import VectorBackend
from app.core.config import settings
from app.knowledge.reranker import rrf_fuse, get_reranker
from app.knowledge import metrics as _metrics
from app.knowledge.permission import get_permission_manager
from app.knowledge.knowledge_domains import get_domain_registry

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
                    doc_id: Optional[str] = None,
                    doc_access: Optional[str] = None,
                    chunk_access_map: Optional[dict] = None) -> dict:
        """增量幂等写入单篇文档。

        Args:
            text: 文档内容
            project_id: 项目ID
            asset_id: 资产ID
            title: 文档标题
            source: 来源
            doc_format: 文档格式
            doc_id: 文档ID
            doc_access: 文档访问级别 (public/internal/private/confidential)
            chunk_access_map: 章节级访问级别映射 {section_name: access_level}

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

            # 自动推断知识域
            registry = get_domain_registry()
            doc_domain = registry.infer_from_doc_title(title) or registry.infer_from_text(norm_text[:500])

            # 文档访问级别：默认 public
            final_doc_access = doc_access or "public"

            self.repo._execute(
                "INSERT INTO knowledge_docs "
                "(id, project_id, asset_id, title, source, created_at, "
                " doc_format, content_hash, version, domain, access_level) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, project_id, asset_id, title, source, self.repo._now(),
                 doc_format, content_hash, version, doc_domain, final_doc_access))
            chunk_records = []
            chunk_access_map = chunk_access_map or {}
            for i, ch in enumerate(chunks):
                cid = self.repo._generate_id()
                # 章节访问级别：从 chunk_access_map 中查找，否则继承文档级别
                chunk_access = chunk_access_map.get(ch.section, "public")
                self.repo._execute(
                    "INSERT INTO knowledge_chunks "
                    "(id, doc_id, idx, content, section, metadata_json, access_level) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (cid, doc_id, i, ch.content, ch.section,
                     self.repo._json_dumps(ch.meta), chunk_access))
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

    def _fetch_candidates(self, ids_with_scores, project_id: Optional[str] = None,
                          filters: Optional[dict] = None) -> List[dict]:
        if not ids_with_scores:
            return []
        ids = [cid for cid, _ in ids_with_scores]
        placeholders = ",".join("?" for _ in ids)
        params = list(ids)
        
        where_clauses = [f"c.id IN ({placeholders})", "d.project_id = ?"]
        params.append(project_id or "")
        
        filters = filters or {}
        if filters.get("section"):
            where_clauses.append("c.section = ?")
            params.append(filters["section"])
        if filters.get("doc_type"):
            where_clauses.append("d.doc_format = ?")
            params.append(filters["doc_type"])
        if filters.get("title"):
            where_clauses.append("d.title LIKE ?")
            params.append(f"%{filters['title']}%")
        
        where_sql = " AND ".join(where_clauses)
        
        rows = self.repo._execute(
            f"SELECT c.id AS cid, c.content AS content, c.section AS section, "  # nosec B608
            f"c.idx AS idx, c.access_level AS chunk_access, "
            f"d.id AS doc_id, d.title AS doc_title, d.source AS source, d.doc_format AS doc_format, "
            f"d.domain AS domain, d.access_level AS doc_access "
            f"FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
            f"WHERE {where_sql}",
            tuple(params)).fetchall()
        
        by_id = {r["cid"]: r for r in rows}
        results = []
        for cid, score in ids_with_scores:
            row = by_id.get(cid)
            if row:
                results.append({
                    "chunk_id": cid,
                    "content": row["content"],
                    "section": row["section"] or "",
                    "idx": row["idx"] or 0,
                    "score": score,
                    "doc_id": row["doc_id"] or "",
                    "source": row["source"] or "",
                    "doc_title": row["doc_title"] or "未知来源",
                    "doc_format": row["doc_format"] or "",
                    "domain": row["domain"] or "general",
                    "doc_access": row["doc_access"] or "public",
                    "chunk_access": row["chunk_access"] or "public",
                })
        return results

    def _query_to_domain(self, query: str) -> List[str]:
        """委托给 DomainRegistry 统一推断。"""
        return get_domain_registry().infer_from_query(query)

    def _doc_title_to_domain(self, doc_title: str) -> str:
        """委托给 DomainRegistry 统一推断。"""
        return get_domain_registry().infer_from_doc_title(doc_title)

    def _filter_by_query_domain(self, chunks: List[dict], query: str) -> List[dict]:
        query_domains = self._query_to_domain(query)
        if "general" in query_domains and len(query_domains) == 1:
            return chunks

        filtered = []
        for chunk in chunks:
            # 优先使用数据库持久化的 domain，回退到标题推断
            chunk_domain = chunk.get("domain") or self._doc_title_to_domain(chunk.get("doc_title", ""))
            if chunk_domain in query_domains:
                chunk["domain"] = chunk_domain
                filtered.append(chunk)

        if filtered:
            logger.debug("域名过滤: query='%s', query_domains=%s, 原始=%d, 过滤后=%d", 
                        query, query_domains, len(chunks), len(filtered))
        else:
            logger.debug("域名过滤无匹配结果，回退全部结果")
            filtered = chunks

        return filtered

    def _apply_permission_filter(self, chunks: List[dict], user_id: str) -> List[dict]:
        if not user_id:
            return chunks

        pm = get_permission_manager(mock=True)
        filtered = pm.filter_chunks_by_permission(user_id, chunks)

        logger.info("权限过滤完成: user_id=%s, role=%s, 原始结果=%d, 过滤后=%d", 
                    user_id, pm.get_user_role(user_id), len(chunks), len(filtered))
        return filtered

    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None,
                 filters: Optional[dict] = None, user_id: Optional[str] = None) -> List[dict]:
        _t0 = time.perf_counter()
        try:
            if not query or not query.strip():
                return []
            if not project_id:                      # L1: 强隔离，project_id 必填
                return []

            kw_ids = self.backends["keyword"].search(query, project_id=project_id, limit=top_k*4)
            tf_ids = self.backends["tfidf"].search(query, project_id=project_id, limit=top_k*4)
            vec_ids: list = []
            if settings.VECTOR_FUSE_ENABLED and settings.EMBEDDING_PROVIDER != "mock":
                vec_ids = self.backends["vector"].search(query, project_id=project_id, limit=top_k*4)
            fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
            if not fused:
                return []
            do_rerank = rerank if rerank is not None else settings.RERANK_ENABLED
            top_n = rerank_top_n if rerank_top_n is not None else settings.RERANK_TOP_N
            if top_n < top_k:
                top_n = top_k

            if do_rerank:
                try:
                    candidates = self._fetch_candidates(fused[:top_n], project_id, filters=filters)
                    candidates = self._filter_by_query_domain(candidates, query)
                    candidates = self._apply_permission_filter(candidates, user_id)
                    return get_reranker(project_id=project_id, repo=self.repo).rerank(query, candidates, top_k)
                except Exception as e:
                    logger.warning("rerank 失败, 回退融合顺序: %s", e)
            candidates = self._fetch_candidates(fused[:top_k], project_id, filters=filters)
            candidates = self._filter_by_query_domain(candidates, query)
            return self._apply_permission_filter(candidates, user_id)
        finally:
            _metrics.metrics.record_retrieval((time.perf_counter() - _t0) * 1000.0)

    def list_documents(self, project_id: Optional[str] = None,
                       limit: int = 100, offset: int = 0) -> dict:
        where = ""
        params: list = []
        if project_id:
            where = "WHERE d.project_id=? "
            params.append(project_id)
        rows = self.repo._execute(
            f"SELECT d.id, d.title, d.source, d.project_id, d.created_at, "  # nosec B608
            f"COUNT(c.id) AS chunk_count "
            f"FROM knowledge_docs d LEFT JOIN knowledge_chunks c ON c.doc_id=d.id "
            f"{where}GROUP BY d.id ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
            tuple(params + [limit, offset])).fetchall()
        docs = [dict(r) for r in rows]
        total_row = self.repo._execute(
            f"SELECT COUNT(*) AS cnt FROM knowledge_docs d {where}", tuple(params)  # nosec B608
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

    def reindex_stale_vectors(self, project_id: Optional[str] = None) -> int:
        return self.backends["vector"].reindex_stale(project_id)
