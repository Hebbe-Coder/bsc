"""RAG Trace：记录完整 RAG 链路，支持全链路追踪与问题排查。

生产级 RAG 的核心：
- 记录 query→rewrite→recall→rerank→prompt→LLM输出→用户反馈
- 类似 AI 领域的 APM（Application Performance Monitoring）
- 支持按 trace_id 查询全链路
- 便于分析失败原因与持续优化
"""
from __future__ import annotations
import json
import logging
import time
import uuid
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class RAGTrace:
    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.start_time = time.time()
        self.steps: List[dict] = []
        self.metrics: Dict = {}
        self.user_feedback: Optional[Dict] = None

    def add_step(self, step_name: str, data: Dict, duration_ms: Optional[float] = None):
        step = {
            "step_name": step_name,
            "timestamp": time.time(),
            "duration_ms": duration_ms,
            "data": data,
        }
        self.steps.append(step)

    def set_metrics(self, metrics: Dict):
        self.metrics.update(metrics)

    def record_query(self, query: str):
        self.add_step("query", {"query": query})

    def record_rewrite(self, rewrite_result: Dict):
        self.add_step("rewrite", rewrite_result)

    def record_retrieval(self, chunks: List[Dict], duration_ms: float):
        self.add_step("retrieval", {
            "chunk_count": len(chunks),
            "chunks": [{"chunk_id": c.get("chunk_id"), "score": c.get("score"),
                       "doc_title": c.get("doc_title"), "section": c.get("section")}
                      for c in chunks]
        }, duration_ms=duration_ms)

    def record_rerank(self, reranked: List[Dict], duration_ms: float):
        self.add_step("rerank", {
            "rerank_count": len(reranked),
            "scores": [c.get("rerank_score") for c in reranked]
        }, duration_ms=duration_ms)

    def record_generation(self, answer: str, citations: List[Dict], metrics: Dict, duration_ms: float):
        self.add_step("generation", {
            "answer_length": len(answer),
            "citation_count": len(citations),
            "metrics": metrics,
        }, duration_ms=duration_ms)

    def record_prompt(self, prompt: str):
        self.add_step("prompt", {"prompt_length": len(prompt)})

    def record_feedback(self, rating: int, comment: Optional[str] = None):
        self.user_feedback = {
            "rating": rating,
            "comment": comment,
            "timestamp": time.time(),
        }

    def finalize(self) -> Dict:
        total_duration = (time.time() - self.start_time) * 1000
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": round(total_duration, 2),
            "steps": self.steps,
            "metrics": self.metrics,
            "user_feedback": self.user_feedback,
            "timestamp": self.start_time,
        }


class TraceStore:
    def __init__(self, repo=None):
        self.repo = repo
        self._ensure_table()

    def _ensure_table(self):
        if self.repo is None:
            return
        try:
            self.repo._execute("""
                CREATE TABLE IF NOT EXISTS rag_traces (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    query TEXT,
                    steps_json TEXT,
                    metrics_json TEXT,
                    feedback_json TEXT,
                    total_duration_ms REAL,
                    created_at INTEGER
                )
            """)
            self.repo._commit()
        except Exception as e:
            logger.warning("创建 rag_traces 表失败: %s", e)

    def save(self, trace: RAGTrace):
        if self.repo is None:
            logger.debug(f"Trace {trace.trace_id} not saved (no repo)")
            return
        data = trace.finalize()
        try:
            self.repo._execute("""
                INSERT OR REPLACE INTO rag_traces 
                (id, trace_id, query, steps_json, metrics_json, feedback_json, 
                 total_duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                trace.trace_id,
                data["steps"][0]["data"].get("query", "") if data["steps"] else "",
                json.dumps(data["steps"], ensure_ascii=False),
                json.dumps(data["metrics"], ensure_ascii=False),
                json.dumps(data["user_feedback"], ensure_ascii=False) if data["user_feedback"] else None,
                data["total_duration_ms"],
                int(data["timestamp"]),
            ))
            self.repo._commit()
        except Exception as e:
            logger.warning("保存 trace 失败: %s", e)

    def get_by_trace_id(self, trace_id: str) -> Optional[Dict]:
        if self.repo is None:
            return None
        try:
            row = self.repo._execute(
                "SELECT * FROM rag_traces WHERE trace_id=?",
                (trace_id,)).fetchone()
            if not row:
                return None
            return {
                "trace_id": row["trace_id"],
                "query": row["query"],
                "steps": json.loads(row["steps_json"]) if row["steps_json"] else [],
                "metrics": json.loads(row["metrics_json"]) if row["metrics_json"] else {},
                "user_feedback": json.loads(row["feedback_json"]) if row["feedback_json"] else None,
                "total_duration_ms": row["total_duration_ms"],
                "created_at": row["created_at"],
            }
        except Exception as e:
            logger.warning("查询 trace 失败: %s", e)
            return None

    def list_recent(self, limit: int = 20) -> List[Dict]:
        if self.repo is None:
            return []
        try:
            rows = self.repo._execute(
                "SELECT trace_id, query, total_duration_ms, created_at "
                "FROM rag_traces ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("查询 trace 列表失败: %s", e)
            return []


class MockTraceStore(TraceStore):
    def __init__(self):
        super().__init__(repo=None)
        self._memory = {}

    def save(self, trace: RAGTrace):
        data = trace.finalize()
        self._memory[trace.trace_id] = data

    def get_by_trace_id(self, trace_id: str) -> Optional[Dict]:
        return self._memory.get(trace_id)

    def list_recent(self, limit: int = 20) -> List[Dict]:
        items = list(self._memory.values())
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        result = []
        for item in items[:limit]:
            query = ""
            if item.get("steps"):
                for step in item["steps"]:
                    if step.get("step_name") == "query":
                        query = step["data"].get("query", "")[:50]
                        break
            result.append({
                "trace_id": item["trace_id"],
                "query": query,
                "total_duration_ms": item["total_duration_ms"],
                "created_at": item["timestamp"],
            })
        return result


def get_trace_store(repo=None) -> TraceStore:
    if repo is None:
        return MockTraceStore()
    return TraceStore(repo)
