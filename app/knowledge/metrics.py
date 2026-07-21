"""轻量进程内指标收集器（无外部依赖）。"""
from __future__ import annotations
import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.retrieval_latency_ms: Dict[str, float] = {"count": 0.0, "sum": 0.0, "max": 0.0}
        self.rerank_hit_rate: Dict[str, float] = {"count": 0.0, "sum": 0.0}
        self.eval_regressions: int = 0
        self.auth_failures: int = 0
        self.knowledge_runs: Dict[str, Any] = {
            "outcomes": {},
            "queue_delay_ms": {"count": 0, "sum": 0.0, "max": 0.0},
            "runtime_ms": {"count": 0, "sum": 0.0, "max": 0.0},
            "retries": 0,
            "distillation_freshness_seconds": None,
        }

    def record_retrieval(self, ms: float):
        with self._lock:
            s = self.retrieval_latency_ms
            s["count"] += 1; s["sum"] += ms; s["max"] = max(s["max"], ms)
            logger.debug("knowledge.retrieval latency_ms=%.3f", ms)

    def record_rerank_hit_rate(self, rate: float):
        with self._lock:
            self.rerank_hit_rate["count"] += 1
            self.rerank_hit_rate["sum"] += rate

    def record_eval_regression(self):
        with self._lock:
            self.eval_regressions += 1

    def record_auth_failure(self):
        with self._lock:
            self.auth_failures += 1
            logger.info("knowledge.auth_failure")

    def record_knowledge_run(
        self,
        *,
        status: str,
        queue_delay_ms: float,
        runtime_ms: float,
        retry_count: int = 0,
        distillation_freshness_seconds: float | None = None,
    ) -> None:
        with self._lock:
            outcomes = self.knowledge_runs["outcomes"]
            outcomes[status] = outcomes.get(status, 0) + 1
            for key, value in (("queue_delay_ms", queue_delay_ms), ("runtime_ms", runtime_ms)):
                bucket = self.knowledge_runs[key]
                bucket["count"] += 1
                bucket["sum"] += max(0.0, value)
                bucket["max"] = max(bucket["max"], max(0.0, value))
            self.knowledge_runs["retries"] += max(0, retry_count)
            if distillation_freshness_seconds is not None:
                self.knowledge_runs["distillation_freshness_seconds"] = max(0.0, distillation_freshness_seconds)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            s = self.retrieval_latency_ms
            avg = (s["sum"] / s["count"]) if s["count"] else 0.0
            return {
                "retrieval_latency_ms": {"count": int(s["count"]), "avg": round(avg, 3), "max": round(s["max"], 3)},
                "rerank_hit_rate": {"count": int(self.rerank_hit_rate["count"]),
                                    "avg": round(self.rerank_hit_rate["sum"] / self.rerank_hit_rate["count"], 4)
                                    if self.rerank_hit_rate["count"] else 0.0},
                "eval_regressions": self.eval_regressions,
                "auth_failures": self.auth_failures,
                "knowledge_runs": {
                    "outcomes": dict(self.knowledge_runs["outcomes"]),
                    "queue_delay_ms": self._timing_snapshot(self.knowledge_runs["queue_delay_ms"]),
                    "runtime_ms": self._timing_snapshot(self.knowledge_runs["runtime_ms"]),
                    "retries": self.knowledge_runs["retries"],
                    "distillation_freshness_seconds": self.knowledge_runs["distillation_freshness_seconds"],
                },
            }

    @staticmethod
    def _timing_snapshot(bucket: Dict[str, float]) -> Dict[str, float | int]:
        count = int(bucket["count"])
        return {
            "count": count,
            "avg": round(bucket["sum"] / count, 3) if count else 0.0,
            "max": round(bucket["max"], 3),
        }

    def reset(self):
        with self._lock:
            self.retrieval_latency_ms = {"count": 0.0, "sum": 0.0, "max": 0.0}
            self.rerank_hit_rate = {"count": 0.0, "sum": 0.0}
            self.eval_regressions = 0
            self.auth_failures = 0
            self.knowledge_runs = {
                "outcomes": {},
                "queue_delay_ms": {"count": 0, "sum": 0.0, "max": 0.0},
                "runtime_ms": {"count": 0, "sum": 0.0, "max": 0.0},
                "retries": 0,
                "distillation_freshness_seconds": None,
            }


metrics = Metrics()
