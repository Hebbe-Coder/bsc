"""Bounded, replayable SSE views over durable knowledge-growth run events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Mapping

from fastapi import HTTPException, Request

from app.knowledge.capture_adapters import redact_secrets
from app.knowledge.growth_repository import GrowthRepository

MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "unavailable"}
_MODEL_USAGE_INTEGER_FIELDS = frozenset(
    {
        "provider_calls",
        "reported_calls",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "reasoning_tokens",
    }
)
_MODEL_EVENT_STRING_FIELDS = frozenset(
    {
        "prompt_run_id",
        "agent_manifest_fingerprint",
        "task",
        "revision",
        "provider",
        "model",
    }
)
_MODEL_RETRY_CATEGORIES = frozenset(
    {
        "network_error",
        "rate_limited",
        "server_error",
        "transport_timeout",
    }
)


def validate_event_cursor(
    repository: GrowthRepository,
    *,
    project_id: str,
    run_id: str,
    after_sequence: int,
) -> None:
    if after_sequence < 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "growth_invalid_cursor", "message": "after_sequence must be non-negative"},
        )
    latest = repository.latest_run_event_sequence(project_id=project_id, run_id=run_id)
    if after_sequence > latest:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "growth_event_sequence_ahead",
                "message": "after_sequence is ahead of persisted run history",
            },
        )


def public_event(event: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "knowledge.growth.event")
    raw_payload = event.get("payload") or {}
    payload = redact_secrets(raw_payload)
    if event_type == "knowledge.growth.model.completed" and isinstance(raw_payload, Mapping):
        payload = _public_model_event(raw_payload)
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > MAX_EVENT_PAYLOAD_BYTES:
        payload = {
            "truncated": True,
            "original_bytes": len(encoded),
            "keys": sorted(str(key) for key in payload)[:100] if isinstance(payload, dict) else [],
        }
    status = str((payload if isinstance(payload, dict) else {}).get("status") or run.get("status") or "")
    return {
        "id": str(event.get("id") or ""),
        "project_id": str(event.get("project_id") or run.get("project_id") or ""),
        "run_id": str(event.get("run_id") or run.get("id") or ""),
        "asset_id": _asset_id(payload),
        "sequence": int(event.get("sequence") or 0),
        "event_type": event_type,
        "actor": str(run.get("actor_id") or "system"),
        "terminal": event_type.rsplit(".", 1)[-1] in TERMINAL_RUN_STATES or status in TERMINAL_RUN_STATES,
        "payload": payload,
        "created_at": str(event.get("created_at") or ""),
    }


def _public_model_usage(value: Any) -> dict[str, int | bool | None]:
    """Return only provider-reported model metrics that are safe for the run UI."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int | bool | None] = {}
    complete = value.get("complete")
    if isinstance(complete, bool):
        result["complete"] = complete
    for field in _MODEL_USAGE_INTEGER_FIELDS:
        metric = value.get(field)
        if metric is None and field in value:
            result[field] = None
        elif isinstance(metric, int) and not isinstance(metric, bool) and metric >= 0:
            result[field] = metric
    return result


def _public_model_event(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project the model ledger through a strict, non-content event contract."""
    result: dict[str, Any] = {}
    for field in _MODEL_EVENT_STRING_FIELDS:
        item = value.get(field)
        if isinstance(item, str) and item and len(item) <= 256:
            result[field] = item
    for field, maximum in (("attempt_count", 3), ("retry_count", 2)):
        item = value.get(field)
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= maximum:
            result[field] = item
    categories = value.get("retry_categories")
    if isinstance(categories, (list, tuple)):
        result["retry_categories"] = [
            item for item in categories if isinstance(item, str) and item in _MODEL_RETRY_CATEGORIES
        ][:2]
    result["usage"] = _public_model_usage(value.get("usage"))
    return result


async def stream_run_events(
    request: Request,
    repository: GrowthRepository,
    *,
    project_id: str,
    run_id: str,
    after_sequence: int,
    page_limit: int,
) -> AsyncIterator[str]:
    sequence = after_sequence
    for _ in range(60):
        run = repository.get_run(project_id, run_id)
        if not run:
            return
        events = repository.list_run_events(
            project_id=project_id,
            run_id=run_id,
            after_sequence=sequence,
            limit=page_limit,
        )
        for event in events:
            item = public_event(event, run)
            sequence = item["sequence"]
            yield (
                f"id: {sequence}\n"
                f"event: {item['event_type']}\n"
                f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            )
        if run.get("status") in TERMINAL_RUN_STATES and not events:
            return
        if run.get("status") in TERMINAL_RUN_STATES and events:
            latest = repository.latest_run_event_sequence(project_id=project_id, run_id=run_id)
            if sequence >= latest:
                return
        if await request.is_disconnected():
            return
        yield ": keep-alive\n\n"
        await asyncio.sleep(1)


def _asset_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("asset_id", "source_id", "page_id", "method_id", "output_id", "feedback_id", "proposal_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""
