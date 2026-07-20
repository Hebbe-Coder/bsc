"""Deterministic prompt-context budgeting for capability execution."""

from __future__ import annotations

import math
import string
from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel, Field


def estimate_prompt_tokens(value: str) -> int:
    """Conservatively estimate tokens without coupling execution to one tokenizer."""
    if not value:
        return 0
    # UTF-8 bytes / 3 overestimates ordinary English while remaining safer for
    # CJK business documents than the conventional bytes / 4 heuristic.
    return math.ceil(len(value.encode("utf-8")) / 3)


def truncate_prompt_text(value: str, max_tokens: int) -> str:
    """Keep both the beginning and end of a text within an estimated budget."""
    if max_tokens <= 0 or not value:
        return ""
    if estimate_prompt_tokens(value) <= max_tokens:
        return value

    marker = "\n...[truncated by context budget]...\n"
    marker_tokens = estimate_prompt_tokens(marker)
    if marker_tokens >= max_tokens:
        return _slice_to_budget(value, max_tokens)

    content_budget = max_tokens - marker_tokens
    head_budget = max(1, math.ceil(content_budget * 0.7))
    tail_budget = max(1, content_budget - head_budget)
    result = (
        _slice_to_budget(value, head_budget)
        + marker
        + _slice_to_budget(value, tail_budget, from_end=True)
    )
    return result if estimate_prompt_tokens(result) <= max_tokens else _slice_to_budget(value, max_tokens)


def _slice_to_budget(value: str, max_tokens: int, *, from_end: bool = False) -> str:
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = value[-middle:] if from_end else value[:middle]
        if estimate_prompt_tokens(candidate) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return value[-low:] if from_end and low else value[:low]


class PromptContextUsage(BaseModel):
    """Non-sensitive evidence of how one capability prompt used its budget."""

    max_tokens: int = Field(ge=1)
    estimated_tokens: int = Field(ge=0)
    template_tokens: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    artifact_tokens: int = Field(ge=0)
    artifacts_available: int = Field(ge=0)
    artifacts_included: int = Field(ge=0)
    artifacts_omitted: int = Field(ge=0)
    artifacts_truncated: int = Field(ge=0)
    input_truncated: bool = False


@dataclass(frozen=True)
class PromptContextItem:
    text: str
    artifact_id: str = ""


@dataclass(frozen=True)
class RenderedPrompt:
    prompt: str
    usage: PromptContextUsage


class CapabilityPromptBudget:
    """Render capability templates within one deterministic, artifact-aware budget."""

    def __init__(
        self,
        *,
        max_tokens: int = 12_000,
        input_max_tokens: int = 4_000,
        artifact_max_tokens: int = 1_200,
    ) -> None:
        if max_tokens < 64:
            raise ValueError("max_tokens must be at least 64")
        if input_max_tokens < 1 or artifact_max_tokens < 1:
            raise ValueError("per-item prompt budgets must be positive")
        self.max_tokens = max_tokens
        self.input_max_tokens = input_max_tokens
        self.artifact_max_tokens = artifact_max_tokens

    def render(
        self,
        template: str,
        *,
        input_text: str,
        context_blocks: Iterable[tuple[str, list[PromptContextItem]]],
    ) -> RenderedPrompt:
        blocks = list(context_blocks)
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(template)
            if field_name
        }
        values = {field_name: "(none)" for field_name in fields}
        baseline = template.format(**values)
        available_ids = {
            item.artifact_id
            for field_name, items in blocks
            if field_name in fields
            for item in items
            if item.artifact_id
        }
        included_ids: set[str] = set()
        omitted_ids: set[str] = set()
        artifacts_truncated = 0
        input_truncated = False

        if "input_text" in fields and input_text:
            bounded = truncate_prompt_text(input_text, self.input_max_tokens)
            input_truncated = bounded != input_text
            accepted, was_truncated = self._append_within_budget(
                template, values, "input_text", bounded
            )
            input_truncated = input_truncated or was_truncated
            if not accepted:
                values["input_text"] = "(none)"

        for field_name, items in blocks:
            if field_name not in fields:
                continue
            for item in items:
                bounded = truncate_prompt_text(item.text, self.artifact_max_tokens)
                accepted, was_truncated = self._append_within_budget(
                    template, values, field_name, bounded
                )
                if not accepted:
                    if item.artifact_id:
                        omitted_ids.add(item.artifact_id)
                    continue
                if item.artifact_id:
                    included_ids.add(item.artifact_id)
                if bounded != item.text or was_truncated:
                    artifacts_truncated += 1

        prompt = template.format(**values)
        if estimate_prompt_tokens(prompt) > self.max_tokens:
            raise RuntimeError("prompt budget allocation exceeded its configured maximum")

        input_value = values.get("input_text", "")
        artifact_values = [
            value for field_name, value in values.items()
            if field_name != "input_text" and value != "(none)"
        ]
        return RenderedPrompt(
            prompt=prompt,
            usage=PromptContextUsage(
                max_tokens=self.max_tokens,
                estimated_tokens=estimate_prompt_tokens(prompt),
                template_tokens=estimate_prompt_tokens(baseline),
                input_tokens=estimate_prompt_tokens(
                    input_value if input_value != "(none)" else ""
                ),
                artifact_tokens=sum(estimate_prompt_tokens(value) for value in artifact_values),
                artifacts_available=len(available_ids),
                artifacts_included=len(included_ids),
                artifacts_omitted=len(available_ids - included_ids | omitted_ids),
                artifacts_truncated=artifacts_truncated,
                input_truncated=input_truncated,
            ),
        )

    def _append_within_budget(
        self,
        template: str,
        values: dict[str, str],
        field_name: str,
        text: str,
    ) -> tuple[bool, bool]:
        if not text:
            return False, False
        previous = values[field_name]
        separator = "" if previous == "(none)" else "\n"
        candidate = text if not separator else previous + separator + text
        if self._fits(template, values, field_name, candidate):
            values[field_name] = candidate
            return True, False

        low, high = 0, estimate_prompt_tokens(text)
        best = ""
        while low < high:
            middle = (low + high + 1) // 2
            shortened = truncate_prompt_text(text, middle)
            candidate = shortened if not separator else previous + separator + shortened
            if self._fits(template, values, field_name, candidate):
                best = shortened
                low = middle
            else:
                high = middle - 1
        if not best:
            return False, False
        values[field_name] = best if not separator else previous + separator + best
        return True, best != text

    def _fits(
        self,
        template: str,
        values: dict[str, str],
        field_name: str,
        candidate: str,
    ) -> bool:
        rendered = template.format(**(values | {field_name: candidate}))
        return estimate_prompt_tokens(rendered) <= self.max_tokens
