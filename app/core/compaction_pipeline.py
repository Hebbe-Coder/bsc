"""Token-aware context budgeting for long business compilation sessions."""

from __future__ import annotations

import copy
import json
import logging
import math
import time
from typing import Any, Callable, Optional

from app.core.pipeline_enhanced import ReminderPolicy

logger = logging.getLogger(__name__)


def estimate_tokens(value: Any) -> int:
    """Estimate model tokens from UTF-8 bytes without a tokenizer dependency."""
    if not isinstance(value, str):
        value = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    if not value:
        return 0
    return math.ceil(len(value.encode("utf-8")) / 4)


class ContextManager:
    """Track context usage and compact older agent outputs deterministically."""

    def __init__(
        self,
        max_chars: int = 200_000,
        compaction_threshold_pct: float = 0.75,
        keep_last_n_agents: int = 3,
        summarizer: Optional[Callable[[list[dict]], Any]] = None,
    ):
        if max_chars < 4:
            raise ValueError("max_chars must be at least 4")
        if not 0 < compaction_threshold_pct <= 1:
            raise ValueError("compaction_threshold_pct must be in (0, 1]")
        if keep_last_n_agents < 1:
            raise ValueError("keep_last_n_agents must be at least 1")

        self._max_tokens = max(1, max_chars // 4)
        self._threshold_tokens = max(
            1,
            math.floor(self._max_tokens * compaction_threshold_pct),
        )
        self._keep_last_n = keep_last_n_agents
        self._summarizer = summarizer
        self._reminder = ReminderPolicy(
            show_token_usage=True,
            show_elapsed_time=True,
        )
        self._accumulated: list[dict] = []
        self._total_tokens = 0
        self._peak_tokens = 0
        self._compaction_count = 0
        self._tokens_saved = 0

    def add_agent_result(
        self,
        agent_name: str,
        result: dict,
        elapsed_s: float = 0,
    ):
        stored = copy.deepcopy(result)
        serialized = self._serialize(stored)
        tokens = estimate_tokens(serialized)
        self._accumulated.append({
            "agent": agent_name,
            "tokens": tokens,
            "chars": len(serialized),
            "elapsed_s": elapsed_s,
            "result": stored,
        })
        self._total_tokens += tokens
        self._peak_tokens = max(self._peak_tokens, self._total_tokens)

    @property
    def needs_compaction(self) -> bool:
        return self._total_tokens >= self._threshold_tokens

    def get_context_for_next_agent(self, next_agent: str) -> dict:
        tokens_before = self._total_tokens
        compacted_now = False
        if self.needs_compaction and len(self._accumulated) > self._keep_last_n:
            compacted_now = self._compact()

        reminder = self._reminder.build_reminder(
            tokens_used=self._total_tokens,
            elapsed_s=sum(
                entry.get("elapsed_s", 0) for entry in self._accumulated
            ),
        )
        return {
            "agent_results": copy.deepcopy(self._accumulated),
            "total_chars": sum(entry["chars"] for entry in self._accumulated),
            "estimated_tokens": self._total_tokens,
            "tokens_before": tokens_before,
            "peak_tokens": self._peak_tokens,
            "tokens_saved": self._tokens_saved,
            "compacted": compacted_now,
            "compaction_count": self._compaction_count,
            "reminder": reminder,
            "next_agent": next_agent,
        }

    def get_stats(self) -> dict:
        return {
            "total_chars": sum(entry["chars"] for entry in self._accumulated),
            "estimated_tokens": self._total_tokens,
            "peak_tokens": self._peak_tokens,
            "tokens_saved": self._tokens_saved,
            "agent_count": len(self._accumulated),
            "needs_compaction": self.needs_compaction,
            "threshold_tokens": self._threshold_tokens,
            "max_tokens": self._max_tokens,
            "compaction_count": self._compaction_count,
        }

    def _compact(self) -> bool:
        older = self._accumulated[:-self._keep_last_n]
        recent = self._accumulated[-self._keep_last_n:]
        before = self._total_tokens
        summary = self._summary_entry(older, self._summary_for(older))
        candidate = [summary, *recent]
        after = sum(entry["tokens"] for entry in candidate)

        if after >= before:
            minimal = {
                "summary": f"Compacted {len(older)} prior agent outputs",
                "agents": [entry["agent"] for entry in older],
            }
            summary = self._summary_entry(older, minimal)
            candidate = [summary, *recent]
            after = sum(entry["tokens"] for entry in candidate)
        if after >= before:
            logger.warning(
                "ContextManager: compaction skipped because it would not save tokens"
            )
            return False

        self._accumulated = candidate
        self._total_tokens = after
        self._compaction_count += 1
        self._tokens_saved += before - after
        logger.info(
            "ContextManager: compacted %d -> %d tokens",
            before,
            after,
        )
        return True

    def _summary_entry(self, entries: list[dict], result: Any) -> dict:
        serialized = self._serialize(result)
        return {
            "agent": "context_summary",
            "tokens": estimate_tokens(serialized),
            "chars": len(serialized),
            "elapsed_s": sum(entry.get("elapsed_s", 0) for entry in entries),
            "result": result,
        }

    def _summary_for(self, entries: list[dict]) -> Any:
        if self._summarizer is not None:
            summary = self._summarizer(copy.deepcopy(entries))
            if summary not in (None, "", {}, []):
                return summary
            logger.warning("ContextManager: custom summarizer returned empty output")
        return {
            "summary": f"Compacted {len(entries)} prior agent outputs",
            "agents": [entry["agent"] for entry in entries],
            "result_keys": {
                entry["agent"]: sorted(entry["result"].keys())
                for entry in entries
                if isinstance(entry.get("result"), dict)
            },
        }

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )


def compile_with_compaction(
    prd_content: str,
    llm_service=None,
    output_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Compile and attach measured context statistics to the result."""
    from app.capabilities.runner import run_legacy_bsc_runtime_sync

    started = time.perf_counter()
    context = ContextManager()
    result = run_legacy_bsc_runtime_sync(
        input_text=prd_content,
        llm_service=llm_service,
        async_mode=False,
    )
    for stage in result.get("pipeline", {}).get("stages", []):
        context.add_agent_result(
            agent_name=stage.get("key", stage.get("agent", "unknown")),
            result={
                "display": stage.get("display", ""),
                "status": stage.get("status", ""),
            },
            elapsed_s=stage.get("duration_ms", 0) / 1000,
        )

    stats = context.get_stats()
    result.setdefault("pipeline", {})["context"] = stats
    result["pipeline"]["compaction_enabled"] = True
    logger.info(
        "CompactionPipeline: %d agents, %d tokens, %.3fs",
        stats["agent_count"],
        stats["estimated_tokens"],
        time.perf_counter() - started,
    )
    return result
