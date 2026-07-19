"""P1 - Business Memory: Cross-run learning and industry knowledge accumulation.

ADR-010 vision: The AI consultant improves over time, not just within a single run.

Three memory layers:
  1. CapabilityMemory  — tracks success_rate, avg_duration per capability
  2. IndustryMemory    — accumulates domain-specific patterns and templates
  3. RunMemory         — links runs together for longitudinal analysis

Stored as JSON files (nanobot-aligned: pure file I/O).
"""

from __future__ import annotations

import json
import time
import logging
from pathlib import Path
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability Memory
# ---------------------------------------------------------------------------

class CapabilityMemory:
    """Tracks capability execution statistics across runs.

    Updates capability.success_rate and capability.avg_duration_ms
    based on actual execution outcomes.
    """

    def __init__(self, data_dir: str = "./data/memory"):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "capability_memory.json"
        self._stats: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._stats = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._stats = {}

    def _save(self):
        self._path.write_text(
            json.dumps(self._stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(
        self,
        capability_name: str,
        success: bool,
        duration_ms: float,
        artifacts_produced: int,
        backend: str = "local",
    ):
        """Record a capability execution result."""
        entry = self._stats.setdefault(capability_name, {
            "total_runs": 0,
            "successes": 0,
            "failures": 0,
            "total_artifacts": 0,
            "total_duration_ms": 0.0,
            "avg_duration_ms": 0.0,
            "success_rate": 1.0,
            "last_run": "",
            "backend": backend,
        })

        entry["total_runs"] += 1
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1

        entry["total_artifacts"] += artifacts_produced
        entry["total_duration_ms"] += duration_ms
        entry["avg_duration_ms"] = (
            entry["total_duration_ms"] / entry["total_runs"]
        )
        entry["success_rate"] = (
            entry["successes"] / entry["total_runs"]
        )
        entry["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry["backend"] = backend

        self._save()
        logger.debug(
            "Memory: %s success_rate=%.2f (%d runs)",
            capability_name, entry["success_rate"], entry["total_runs"],
        )

    def get(self, capability_name: str) -> dict[str, Any]:
        """Get stats for a capability."""
        return self._stats.get(capability_name, {})

    def get_all(self) -> dict[str, dict[str, Any]]:
        return dict(self._stats)

    def best_capabilities(self, min_runs: int = 3) -> list[tuple[str, float]]:
        """Return capabilities ranked by success_rate (min runs threshold)."""
        ranked = [
            (name, s["success_rate"])
            for name, s in self._stats.items()
            if s["total_runs"] >= min_runs
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def weakest_capabilities(self, min_runs: int = 3) -> list[tuple[str, float]]:
        """Return capabilities with lowest success_rate."""
        ranked = self.best_capabilities(min_runs)
        ranked.sort(key=lambda x: x[1])
        return ranked


# ---------------------------------------------------------------------------
# Industry Memory
# ---------------------------------------------------------------------------

class IndustryMemory:
    """Accumulates domain-specific patterns across projects.

    Example: after analyzing 5 fintech projects, the system "knows"
    that fintech projects always need compliance_check and regulatory_analysis.
    """

    def __init__(self, data_dir: str = "./data/memory"):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "industry_memory.json"
        self._patterns: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._patterns = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._patterns = {}

    def _save(self):
        self._path.write_text(
            json.dumps(self._patterns, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_project(
        self,
        industry: str,
        capabilities_used: list[str],
        gaps_found: int,
        success: bool,
    ):
        """Record a project execution for an industry."""
        entry = self._patterns.setdefault(industry, {
            "total_projects": 0,
            "capability_frequency": {},
            "avg_gaps": 0.0,
            "success_rate": 1.0,
            "common_risks": [],
            "common_assumptions": [],
            "last_project": "",
        })

        entry["total_projects"] += 1
        for cap in capabilities_used:
            entry["capability_frequency"][cap] = (
                entry["capability_frequency"].get(cap, 0) + 1
            )

        prev_gaps = entry["avg_gaps"]
        n = entry["total_projects"]
        entry["avg_gaps"] = prev_gaps + (gaps_found - prev_gaps) / n

        prev_sr = entry["success_rate"]
        entry["success_rate"] = prev_sr + ((1.0 if success else 0.0) - prev_sr) / n

        entry["last_project"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()
        logger.info("Industry memory: %s — %d projects", industry, n)

    def get_industry(self, industry: str) -> dict[str, Any]:
        """Get accumulated knowledge for an industry."""
        return self._patterns.get(industry, {})

    def recommended_capabilities(self, industry: str, top_n: int = 5) -> list[str]:
        """Get most-used capabilities for an industry."""
        entry = self._patterns.get(industry, {})
        freq = entry.get("capability_frequency", {})
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in ranked[:top_n]]

    def all_industries(self) -> list[str]:
        return sorted(self._patterns.keys())


# ---------------------------------------------------------------------------
# Run Memory (longitudinal tracking)
# ---------------------------------------------------------------------------

class RunMemory:
    """Tracks individual runs for longitudinal analysis.

    Stores: run_id → {timestamp, domain, capabilities, artifacts, gaps, duration}
    """

    def __init__(self, data_dir: str = "./data/memory"):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "run_memory.json"
        self._runs: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._runs = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._runs = {}

    def _save(self):
        self._path.write_text(
            json.dumps(self._runs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, run_id: str, **kwargs):
        """Record a completed run."""
        self._runs[run_id] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **kwargs,
        }
        self._save()

    def get(self, run_id: str) -> dict[str, Any]:
        return self._runs.get(run_id, {})

    def recent_runs(self, n: int = 10) -> list[dict[str, Any]]:
        """Get most recent runs."""
        sorted_runs = sorted(
            self._runs.items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True,
        )
        return [
            {"run_id": rid, **data}
            for rid, data in sorted_runs[:n]
        ]

    def compare_runs(self, run_a: str, run_b: str) -> dict[str, Any]:
        """Compare two runs side by side."""
        a = self._runs.get(run_a, {})
        b = self._runs.get(run_b, {})
        return {
            "run_a": {"id": run_a, "artifacts": a.get("total_artifacts", 0),
                      "gaps": a.get("gaps_found", 0), "duration_ms": a.get("duration_ms", 0)},
            "run_b": {"id": run_b, "artifacts": b.get("total_artifacts", 0),
                      "gaps": b.get("gaps_found", 0), "duration_ms": b.get("duration_ms", 0)},
        }

    def count(self) -> int:
        return len(self._runs)


# ---------------------------------------------------------------------------
# Unified Business Memory
# ---------------------------------------------------------------------------

class BusinessMemory:
    """Convenience wrapper over all three memory layers.

    Usage:
        mem = BusinessMemory("./data/memory")
        mem.record_capability("risk_analysis", success=True, duration_ms=1200, artifacts=2)
        mem.record_project("fintech", ["risk_analysis", "compliance"], gaps=3)
        mem.record_run("run_001", domain="fintech", total_artifacts=12)
    """

    def __init__(self, data_dir: str = "./data/memory"):
        self.capability = CapabilityMemory(data_dir)
        self.industry = IndustryMemory(data_dir)
        self.run = RunMemory(data_dir)

    def record_capability(
        self, name: str, success: bool, duration_ms: float,
        artifacts_produced: int, backend: str = "local",
    ):
        self.capability.record(name, success, duration_ms, artifacts_produced, backend)

    def record_project(
        self, industry: str, capabilities: list[str],
        gaps_found: int, success: bool = True,
    ):
        self.industry.record_project(industry, capabilities, gaps_found, success)

    def record_run(self, run_id: str, **kwargs):
        self.run.record(run_id, **kwargs)

    def summary(self) -> dict[str, Any]:
        """Return a summary of all memory."""
        return {
            "capabilities_tracked": len(self.capability._stats),
            "industries_tracked": len(self.industry._patterns),
            "total_runs": self.run.count(),
            "best_capabilities": self.capability.best_capabilities(min_runs=1)[:5],
            "weakest_capabilities": self.capability.weakest_capabilities(min_runs=1)[:3],
        }
