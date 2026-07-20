"""Explicit context inheritance policies for agent executions.

The policy is intentionally deterministic. It does not call an LLM to create a
summary, so a fork or resume request cannot silently change meaning because a
summarizer failed. Hosts may replace the compacted summary later while keeping
the same contract and budget metadata.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field

from app.core.prompt_context import estimate_prompt_tokens, truncate_prompt_text


class ContextPolicy(str, Enum):
    FRESH = "fresh"
    FORK = "fork"
    RESUME = "resume"


class ContextItem(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = ""
    source_session_id: str = ""
    priority: int = Field(default=0, ge=0, le=100)


class ContextUsage(BaseModel):
    policy: ContextPolicy
    max_tokens: int = Field(ge=64)
    estimated_tokens: int = Field(ge=0)
    inherited_items: int = Field(ge=0)
    included_items: int = Field(ge=0)
    summarized_items: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    context_truncated: bool = False


class ContextPacket(BaseModel):
    policy: ContextPolicy
    rendered_input: str
    usage: ContextUsage


class ContextManager:
    """Build a bounded context packet for one runtime invocation."""

    def __init__(self, *, max_tokens: int = 12_000, max_verbatim_items: int = 6) -> None:
        if max_tokens < 64:
            raise ValueError("max_tokens must be at least 64")
        if max_verbatim_items < 1:
            raise ValueError("max_verbatim_items must be positive")
        self.max_tokens = max_tokens
        self.max_verbatim_items = max_verbatim_items

    def build(
        self,
        input_text: str,
        *,
        policy: ContextPolicy | str = ContextPolicy.FRESH,
        inherited_items: Iterable[ContextItem | dict] = (),
    ) -> ContextPacket:
        selected_policy = ContextPolicy(policy)
        current = input_text
        source = [
            item if isinstance(item, ContextItem) else ContextItem.model_validate(item)
            for item in inherited_items
            if (item.content if isinstance(item, ContextItem) else item.get("content", "")).strip()
        ]
        if selected_policy is ContextPolicy.RESUME and not source:
            raise ValueError("resume context requires a source session")

        if selected_policy is ContextPolicy.FRESH:
            bounded_input = truncate_prompt_text(current, self.max_tokens)
            return ContextPacket(
                policy=selected_policy,
                rendered_input=bounded_input,
                usage=ContextUsage(
                    policy=selected_policy,
                    max_tokens=self.max_tokens,
                    estimated_tokens=estimate_prompt_tokens(bounded_input),
                    inherited_items=0,
                    included_items=0,
                    summarized_items=0,
                    input_tokens=estimate_prompt_tokens(bounded_input),
                    context_truncated=bounded_input != current,
                ),
            )
        else:
            # Priority first, then source order. The newest caller input is
            # always appended last so it cannot be displaced by inherited data.
            history = sorted(enumerate(source), key=lambda pair: (pair[1].priority, pair[0]))
            history = [item for _, item in history]

        input_budget = max(1, self.max_tokens // 3)
        bounded_input = truncate_prompt_text(current, input_budget)
        input_truncated = bounded_input != current
        history_budget = max(1, self.max_tokens - estimate_prompt_tokens(bounded_input) - 32)
        included: list[ContextItem] = []
        summarized: list[ContextItem] = []
        used = 0

        for item in reversed(history):
            if len(included) >= self.max_verbatim_items:
                summarized.append(item)
                continue
            item_text = f"[{item.role}] {item.content.strip()}"
            item_tokens = estimate_prompt_tokens(item_text)
            if used + item_tokens > history_budget:
                summarized.append(item)
                continue
            included.append(item)
            used += item_tokens
        included.reverse()

        sections: list[str] = []
        if summarized:
            summary_text = "\n".join(
                f"[{item.role}] {truncate_prompt_text(item.content.strip(), 180)}"
                for item in reversed(summarized)
            )
            sections.append("[inherited context summary]\n" + summary_text)
        if included:
            sections.append(
                "[inherited context]\n"
                + "\n".join(f"[{item.role}] {item.content.strip()}" for item in included)
            )
        sections.append("[current request]\n" + bounded_input)
        rendered = "\n\n".join(sections)
        if estimate_prompt_tokens(rendered) > self.max_tokens:
            rendered = truncate_prompt_text(rendered, self.max_tokens)
            input_truncated = True

        return ContextPacket(
            policy=selected_policy,
            rendered_input=rendered,
            usage=ContextUsage(
                policy=selected_policy,
                max_tokens=self.max_tokens,
                estimated_tokens=estimate_prompt_tokens(rendered),
                inherited_items=len(source),
                included_items=len(included),
                summarized_items=len(summarized),
                input_tokens=estimate_prompt_tokens(bounded_input),
                context_truncated=input_truncated or bool(summarized),
            ),
        )
