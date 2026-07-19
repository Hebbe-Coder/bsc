"""
Prompt Layer — Double-layer architecture for prompt management.

Layer 1: prompts/          — Base prompts (version-controlled)
Layer 2: prompt_library/   — Industry-specific prompt variants

Features:
  - Version management (semver)
  - Hot-reload capability
  - Industry coverage
  - A/B testing support
  - Prompt scoring
  - Prompt rollback
"""
from __future__ import annotations
import os
import json
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Data Classes ──

@dataclass
class PromptVersion:
    version: int
    content: str
    created_at: float = field(default_factory=time.time)
    score: float = 0.0
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {"version": self.version, "score": self.score, "usage_count": self.usage_count, "created_at": self.created_at}


@dataclass
class PromptRecord:
    name: str
    path: str
    current_version: int = 1
    active: bool = True
    versions: list[PromptVersion] = field(default_factory=list)
    industry: str = "general"

    def get_active(self) -> Optional[PromptVersion]:
        for v in self.versions:
            if v.version == self.current_version:
                return v
        return self.versions[-1] if self.versions else None

    def to_dict(self) -> dict:
        return {
            "name": self.name, "path": self.path, "active": self.active,
            "current_version": self.current_version, "industry": self.industry,
            "versions": [v.to_dict() for v in self.versions],
        }


# ── Prompt Loader ──

class PromptLoader:
    """Load prompts from filesystem with caching."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")
        self.base_dir = base_dir
        self._cache: dict[str, tuple[float, str]] = {}

    def load(self, name: str, industry: str = None) -> str:
        """Load a prompt by name, with optional industry override."""
        cache_key = f"{name}:{industry or 'default'}"
        
        # Check cache
        if cache_key in self._cache:
            mtime, content = self._cache[cache_key]
            path = self._resolve_path(name, industry)
            if path and os.path.getmtime(path) <= mtime:
                return content

        path = self._resolve_path(name, industry)
        if not path or not os.path.exists(path):
            return self._fallback(name)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        self._cache[cache_key] = (os.path.getmtime(path), content)
        return content

    def _resolve_path(self, name: str, industry: str = None) -> Optional[str]:
        # Industry override takes priority
        if industry:
            ind_path = os.path.join(os.path.dirname(self.base_dir), "prompt_library", "industries", industry, f"{name}.md")
            if os.path.exists(ind_path):
                return ind_path

        # Base prompt
        base_path = os.path.join(self.base_dir, f"{name}.md")
        if os.path.exists(base_path):
            return base_path

        return None

    def _fallback(self, name: str) -> str:
        fallbacks = {
            "system": "You are BSC Studio. Convert business documents into structured Business System JSON.",
            "semantic": "Extract business semantics: roles, actions, states, rules, exceptions, inputs, outputs, dependencies.",
            "blueprint": "Compile semantic model into business blueprint: process model, state machine, RACI, SLA, risk model.",
            "metrics": "Generate KPI tree, metrics catalog, alert rules, and health score formula.",
            "insight": "Analyze operational data: identify problems, root causes, impacts, recommendations, ROI.",
            "dashboard": "Design executive dashboard: KPI cards, trend charts, SLA matrix, health score, workflow diagram.",
        }
        return fallbacks.get(name, f"# {name.upper()} PROMPT\n\nAnalyze and generate structured output.")


# ── Prompt Registry ──

class PromptRegistry:
    """Central registry of all prompts with version tracking."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.base_dir = base_dir
        self.loader = PromptLoader(os.path.join(base_dir, "prompts"))
        self._prompts: dict[str, PromptRecord] = {}
        self._load_registry()

    def _load_registry(self):
        reg_path = os.path.join(self.base_dir, "prompt_library", "registry.json")
        if os.path.exists(reg_path):
            with open(reg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, cfg in data.get("prompts", {}).items():
                self._prompts[name] = PromptRecord(
                    name=name, path=cfg["path"],
                    current_version=cfg.get("version", 1),
                    active=cfg.get("active", True),
                )
            for ind, cfg in data.get("industries", {}).items():
                self._prompts[f"industry:{ind}"] = PromptRecord(
                    name=f"industry:{ind}", path=cfg["path"],
                    current_version=cfg.get("version", 1),
                    industry=ind,
                )

    def get(self, name: str, industry: str = None) -> PromptRecord:
        """Get prompt record, creating if not exists."""
        key = f"industry:{industry}" if industry else name
        if key not in self._prompts:
            self._prompts[key] = PromptRecord(name=name, path=f"prompts/{name}.md")
        return self._prompts[key]

    def list_all(self) -> list[dict]:
        return [p.to_dict() for p in self._prompts.values()]

    def get_prompt(self, name: str, industry: str = None) -> str:
        """Load prompt content."""
        return self.loader.load(name, industry)


# ── Prompt Evaluator ──

class PromptEvaluator:
    """Score and track prompt effectiveness."""

    def __init__(self):
        self._scores: dict[str, list[float]] = {}

    def record(self, prompt_name: str, score: float):
        if prompt_name not in self._scores:
            self._scores[prompt_name] = []
        self._scores[prompt_name].append(score)

    def get_score(self, prompt_name: str) -> float:
        scores = self._scores.get(prompt_name, [])
        if not scores:
            return 0.0
        recent = scores[-20:]
        return sum(recent) / len(recent)

    def compare(self, prompt_a: str, prompt_b: str) -> dict:
        return {
            "a": {"name": prompt_a, "score": self.get_score(prompt_a)},
            "b": {"name": prompt_b, "score": self.get_score(prompt_b)},
            "winner": prompt_a if self.get_score(prompt_a) > self.get_score(prompt_b) else prompt_b,
        }


# ── Prompt Manager (main facade) ──

class PromptManager:
    """Unified prompt management facade."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.registry = PromptRegistry(base_dir)
        self.loader = PromptLoader(os.path.join(base_dir, "prompts"))
        self.evaluator = PromptEvaluator()

    def resolve(self, name: str, industry: str = None) -> str:
        """Resolve and load the best prompt for given name + industry."""
        content = self.loader.load(name, industry)
        self.registry.get(name, industry)
        return content

    def resolve_all(self, names: list[str], industry: str = None) -> dict[str, str]:
        return {name: self.resolve(name, industry) for name in names}

    def record_score(self, name: str, score: float):
        self.evaluator.record(name, score)

    def list_prompts(self) -> dict:
        return {
            "registry": self.registry.list_all(),
            "scores": {k: self.evaluator.get_score(k) for k in self.evaluator._scores},
        }

    def hot_reload(self):
        """Clear cache for hot-reload support."""
        self.loader._cache.clear()
        self.registry._load_registry()


# ── Singleton ──

_prompt_manager: Optional[PromptManager] = None

def get_prompt_manager() -> PromptManager:
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
