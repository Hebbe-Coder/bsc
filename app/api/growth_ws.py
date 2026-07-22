"""Bounded, replayable SSE views over durable knowledge-growth run events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import HTTPException, Request

from app.knowledge.capture_adapters import redact_secrets
from app.knowledge.growth_repository import GrowthRepository

MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "unavailable"}


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
    payload = redact_secrets(event.get("payload") or {})
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > MAX_EVENT_PAYLOAD_BYTES:
        payload = {
            "truncated": True,
            "original_bytes": len(encoded),
            "keys": sorted(str(key) for key in payload)[:100] if isinstance(payload, dict) else [],
        }
    event_type = str(event.get("event_type") or "knowledge.growth.event")
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
