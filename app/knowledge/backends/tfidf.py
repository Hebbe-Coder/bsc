"""TF-IDF 后端：numpy 向量（BLOB 存储），全局模型存 tfidf_model 表。"""
from __future__ import annotations
import json
import logging
from collections import Counter
from typing import List, Optional, Tuple

import numpy as np

from app.knowledge.tokenize import tokenize

logger = logging.getLogger(__name__)


class TfidfBackend:
    def __init__(self, repo):
        self.repo = repo

    def _load_model(self) -> Tuple[Optional[dict], Optional[dict]]:
        row = self.repo._execute(
            "SELECT vocab_json, idf_json FROM tfidf_model WHERE id=1").fetchone()
        if not row:
            return None, None
        return json.loads(row["vocab_json"]), json.loads(row["idf_json"])

    def _build_and_store_model(self) -> Tuple[Optional[dict], Optional[dict], bool]:
        rows = self.repo._execute("SELECT content FROM knowledge_chunks").fetchall()
        docs = [r["content"] for r in rows]
        vocab: dict = {}
        doc_term_counts: List[dict] = []
        for doc in docs:
            tf: dict = {}
            for tok in tokenize(doc):
                if tok not in vocab:
                    vocab[tok] = len(vocab)
                tf[tok] = tf.get(tok, 0) + 1
            doc_term_counts.append(tf)
        num_docs = max(len(docs), 1)
        idf: dict = {}
        for term in vocab:
            df = sum(1 for dt in doc_term_counts if term in dt)
            idf[term] = float(np.log((num_docs + 1) / (df + 1)) + 1)
        # 仅在词表变化时落库重建，否则复用（changed=False）
        existing = self.repo._execute(
            "SELECT vocab_json FROM tfidf_model WHERE id=1").fetchone()
        changed = True
        if existing:
            try:
                if json.loads(existing["vocab_json"]) == vocab:
                    changed = False
            except Exception:
                changed = True
        if changed:
            self.repo._execute("DELETE FROM tfidf_model")
            self.repo._execute(
                "INSERT INTO tfidf_model (id, vocab_json, idf_json) VALUES (1, ?, ?)",
                (json.dumps(vocab, ensure_ascii=False), json.dumps(idf, ensure_ascii=False)))
            self.repo._commit()
        return vocab, idf, changed

    def _vectorize(self, text: str, vocab: dict, idf: dict) -> np.ndarray:
        vec = np.zeros(len(vocab))
        for tok, cnt in Counter(tokenize(text)).items():
            if tok in vocab:
                vec[vocab[tok]] = cnt * idf.get(tok, 1.0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        try:
            vocab, idf, changed = self._build_and_store_model()
        except Exception as e:
            logger.warning("tfidf model build failed: %s", e)
            return
        if not vocab:
            return
        if changed:
            # 词表维度变化，必须为全部 chunk 重新向量化
            all_rows = self.repo._execute(
                "SELECT id, content FROM knowledge_chunks").fetchall()
            targets = [{"id": r["id"], "content": r["content"]} for r in all_rows]
        else:
            # 词表不变，仅向量化本次新增/变更 chunk（增量）
            targets = chunk_records
        for rec in targets:
            vec = self._vectorize(rec["content"], vocab, idf)
            self.repo._execute(
                "INSERT OR REPLACE INTO knowledge_tfidf (chunk_id, vector) VALUES (?, ?)",
                (rec["id"], vec.tobytes()))
        self.repo._commit()

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        vocab, idf = self._load_model()
        if not vocab:
            return []
        qv = self._vectorize(query, vocab, idf)
        rows = self.repo._execute("SELECT chunk_id, vector FROM knowledge_tfidf").fetchall()
        scored = []
        for r in rows:
            cv = np.frombuffer(r["vector"], dtype=np.float64)
            sim = float(np.dot(qv, cv))
            if sim > 0:
                scored.append((r["chunk_id"], sim))
        scored.sort(key=lambda x: -x[1])
        return [cid for cid, _ in scored[:limit]]
