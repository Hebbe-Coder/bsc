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
            }

    def reset(self):
        with self._lock:
            self.retrieval_latency_ms = {"count": 0.0, "sum": 0.0, "max": 0.0}
            self.rerank_hit_rate = {"count": 0.0, "sum": 0.0}
            self.eval_regressions = 0
            self.auth_failures = 0


metrics = Metrics()
