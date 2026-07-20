"""Provider-reported LLM usage normalization without cost or token guesses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    """Normalized usage returned by a provider for one model invocation."""

    provider: str = ""
    model: str = ""
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    reported: bool = False
    complete: bool = False


def extract_model_usage(response: Any, *, provider: str, model: str) -> ModelUsage:
    """Normalize only usage values supplied in an OpenAI-compatible response."""
    raw_usage = _value(response, "usage")
    if raw_usage is None:
        return ModelUsage(provider=provider, model=model)

    prompt_tokens = _token_value(raw_usage, "prompt_tokens", "input_tokens")
    completion_tokens = _token_value(raw_usage, "completion_tokens", "output_tokens")
    total_tokens = _token_value(raw_usage, "total_tokens")
    prompt_details = _value(raw_usage, "prompt_tokens_details")
    completion_details = _value(raw_usage, "completion_tokens_details")
    cached_tokens = _token_value(prompt_details, "cached_tokens")
    reasoning_tokens = _token_value(completion_details, "reasoning_tokens")
    return ModelUsage(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        reported=True,
        complete=(
            prompt_tokens is not None
            and completion_tokens is not None
            and total_tokens is not None
        ),
    )


def _token_value(source: Any, *names: str) -> int | None:
    for name in names:
        value = _value(source, name)
        if isinstance(value, bool) or value is None:
            continue
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized >= 0:
            return normalized
    return None


def _value(source: Any, name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)
