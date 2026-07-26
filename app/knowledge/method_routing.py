"""Deterministic routing for governed, published knowledge methods."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


_ROUTING_STOP_WORDS = frozenset({
    "a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with",
    "mention", "mentions", "need", "prepare", "review", "run", "use",
})


@dataclass(frozen=True)
class MethodRouteMatch:
    slug: str
    score: int
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]


@dataclass(frozen=True)
class MethodRouteDecision:
    selected_slug: str | None
    matches: tuple[MethodRouteMatch, ...]


class MethodRouter:
    """Apply a persisted trigger contract without executing method bodies."""

    def select(self, methods: Iterable[dict[str, Any]], task: str) -> MethodRouteDecision:
        normalized_task = self._normalize(task)
        if not normalized_task:
            return MethodRouteDecision(selected_slug=None, matches=())

        matches: list[MethodRouteMatch] = []
        for method in methods:
            if not isinstance(method, dict):
                continue
            slug = self._slug(method)
            if not slug:
                continue
            contract = self._trigger_contract(method)
            positives = self._signals(contract.get("positive_signals"), method.get("applicability"))
            negatives = self._signals(contract.get("negative_signals"), method.get("exclusions"))
            matched_negative = tuple(signal for signal in negatives if self._contains(normalized_task, signal))
            if matched_negative:
                continue
            matched_positive = tuple(signal for signal in positives if self._contains(normalized_task, signal))
            if not matched_positive:
                continue
            score = sum(self._weight(signal) for signal in matched_positive)
            matches.append(MethodRouteMatch(slug, score, matched_positive, matched_negative))

        matches.sort(key=lambda item: (-item.score, item.slug))
        return MethodRouteDecision(
            selected_slug=matches[0].slug if matches else None,
            matches=tuple(matches),
        )

    @staticmethod
    def _slug(method: dict[str, Any]) -> str:
        manifest = method.get("manifest") if isinstance(method.get("manifest"), dict) else {}
        return str(method.get("slug") or method.get("method_slug") or manifest.get("task_family") or "").strip()

    @staticmethod
    def _trigger_contract(method: dict[str, Any]) -> dict[str, Any]:
        """Read the canonical trigger contract for direct and distilled methods."""
        manifest = method.get("manifest") if isinstance(method.get("manifest"), dict) else {}
        direct = manifest.get("trigger_contract")
        if isinstance(direct, dict):
            return direct
        distillation = manifest.get("distillation")
        nested = distillation.get("trigger_contract") if isinstance(distillation, dict) else None
        return nested if isinstance(nested, dict) else {}

    @classmethod
    def _signals(cls, primary: Any, fallback: Any) -> tuple[str, ...]:
        values = primary if isinstance(primary, list) and primary else fallback
        if not isinstance(values, list):
            return ()
        seen: set[str] = set()
        signals: list[str] = []
        for value in values:
            normalized = cls._normalize(value)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            signals.append(normalized)
        return tuple(signals)

    @classmethod
    def _contains(cls, task: str, signal: str) -> bool:
        if signal in task:
            return True
        tokens = cls._signal_tokens(signal)
        if not tokens:
            return False
        matched = [token for token in tokens if token in task]
        if len(matched) == len(tokens):
            return True
        # Long source-derived labels often include harmless framing such as
        # "mentions of". Permit a bounded two-term majority match for those
        # labels, while short signals keep their exact all-term boundary.
        return len(tokens) >= 4 and len(matched) >= 2 and (len(matched) / len(tokens)) >= 0.5

    @staticmethod
    def _signal_tokens(signal: str) -> tuple[str, ...]:
        return tuple(
            token
            for token in re.findall(r"[a-z0-9]+", signal)
            if token not in _ROUTING_STOP_WORDS
        )

    @staticmethod
    def _weight(signal: str) -> int:
        return max(1, min(len(signal), 32))

    @staticmethod
    def _normalize(value: Any) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[-_/]+", " ", str(value or "").strip().lower()))
