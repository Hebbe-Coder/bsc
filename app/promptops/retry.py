"""Pure retry classification for governed model invocations.

The model client may rotate provider keys and repair malformed JSON within one
request. This module governs the separate outer retry after a transient
provider failure, so callers get one durable run and a complete attempt ledger.
"""

from __future__ import annotations

from dataclasses import dataclass


RETRYABLE_CATEGORIES = frozenset(
    {
        "network_error",
        "server_error",
        "transport_timeout",
        # The structured client has already attempted its bounded JSON repair.
        # A fresh provider sampling can still recover an intermittent empty or
        # unsupported completion payload, so allow one outer retry only.
        "response_payload_invalid",
        "structured_response_invalid",
    }
)
RATE_LIMIT_CATEGORY = "rate_limited"


@dataclass(frozen=True)
class RetryDecision:
    """A side-effect-free decision consumed by ``PromptOps``."""

    retry: bool
    delay_seconds: float = 0.0


def decide_retry(
    category: str,
    *,
    retry_count: int,
    max_attempts: int,
    max_rate_limit_retries: int,
    rate_limit_retries: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
) -> RetryDecision:
    """Retry only transient failures within a small, explicit budget.

    Client configuration, policy, and request-shape errors are terminal. An
    invalid structured response is different: no business action has occurred,
    the request is already governed, and one fresh sample can repair an
    intermittent provider payload without widening authority or retry budget.
    """

    normalized = category.strip().lower()
    if retry_count + 1 >= max_attempts:
        return RetryDecision(retry=False)
    if normalized == RATE_LIMIT_CATEGORY:
        if rate_limit_retries >= max_rate_limit_retries:
            return RetryDecision(retry=False)
    elif normalized not in RETRYABLE_CATEGORIES:
        return RetryDecision(retry=False)

    delay = min(initial_backoff_seconds * (2**retry_count), max_backoff_seconds)
    return RetryDecision(retry=True, delay_seconds=delay)
