"""Run a bounded Horizon producer cycle and publish native MCP stage artifacts."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Iterator


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produce auditable Horizon MCP run artifacts for BSC.")
    parser.add_argument("--horizon-home", required=True)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--source", action="append", dest="sources", default=[])
    parser.add_argument("--threshold", type=float, default=7.0)
    parser.add_argument("--enrich", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--lock-timeout-seconds", type=int, default=7200)
    parser.add_argument("--stage-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--enrichment-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--cycle-timeout-seconds", type=float, default=480.0)
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(exc: Exception) -> str:
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", str(exc))
    return message[:1000]


class HorizonProducerTimeout(RuntimeError):
    """A required Horizon producer stage exceeded BSC's bounded execution window."""


def _positive_timeout(value: float, *, name: str) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return timeout


async def _bounded_stage(awaitable, *, stage: str, timeout_seconds: float):
    timeout = _positive_timeout(timeout_seconds, name=f"{stage} timeout")
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise HorizonProducerTimeout(f"Horizon {stage} stage exceeded {timeout:g} seconds") from exc


def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def _producer_lock(path: Path, *, stale_after_seconds: int) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age <= stale_after_seconds:
            raise RuntimeError("Horizon producer cycle is already running")
        path.unlink()
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        try:
            os.write(descriptor, f"pid={os.getpid()} started_at={_utc_now()}".encode("ascii"))
        finally:
            os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


async def _run(args: argparse.Namespace, horizon_home: Path, *, service_factory=None) -> dict:
    if service_factory is None:
        sys.path.insert(0, str(horizon_home))
        from src.mcp.service import HorizonPipelineService

        service_factory = HorizonPipelineService
    service = service_factory(runs_root=horizon_home / "data" / "mcp-runs")
    fetched = await _bounded_stage(
        service.fetch_items(hours=args.hours, horizon_path=str(horizon_home), sources=args.sources or None),
        stage="fetch",
        timeout_seconds=args.stage_timeout_seconds,
    )
    run_id = fetched["run_id"]
    scored = await _bounded_stage(
        service.score_items(run_id=run_id, horizon_path=str(horizon_home)),
        stage="score",
        timeout_seconds=args.stage_timeout_seconds,
    )
    filtered = await _bounded_stage(
        service.filter_items(
            run_id=run_id,
            threshold=args.threshold,
            topic_dedup=True,
            horizon_path=str(horizon_home),
        ),
        stage="filter",
        timeout_seconds=args.stage_timeout_seconds,
    )
    enriched = None
    ready_stage = "filtered"
    enrichment = {"status": "not_requested"}
    degradations: list[str] = []
    if args.enrich and filtered["kept"] > 0:
        try:
            enriched = await _bounded_stage(
                service.enrich_items(
                    run_id=run_id,
                    source_stage="filtered",
                    horizon_path=str(horizon_home),
                ),
                stage="enrichment",
                timeout_seconds=args.enrichment_timeout_seconds,
            )
            ready_stage = "enriched"
            enrichment = {"status": "completed"}
        except HorizonProducerTimeout:
            enrichment = {
                "status": "timed_out",
                "timeout_seconds": _positive_timeout(
                    args.enrichment_timeout_seconds, name="enrichment timeout"
                ),
            }
            degradations.append("enrichment_timeout")
    service.run_store.update_meta(
        run_id,
        {
            "bsc_ready_at": _utc_now(),
            "bsc_ready_stage": ready_stage,
            "producer": "bsc-scheduled",
            "enrichment": enrichment,
        },
    )
    return {
        "status": "completed_with_degradation" if degradations else "completed",
        "run_id": run_id,
        "fetched": fetched.get("fetched"),
        "scored": scored.get("scored"),
        "kept": filtered.get("kept"),
        "enriched": enriched.get("enriched") if enriched else 0,
        "ready_stage": ready_stage,
        "enrichment": enrichment,
        "degradations": degradations,
        "completed_at": _utc_now(),
    }


def main() -> int:
    args = _arguments()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    horizon_home = Path(args.horizon_home).expanduser().resolve()
    runs_root = horizon_home / "data" / "mcp-runs"
    state_path = runs_root / "producer-state.json"
    try:
        if not (horizon_home / "pyproject.toml").is_file():
            raise RuntimeError("Horizon home is invalid")
        with _producer_lock(runs_root / ".bsc-producer.lock", stale_after_seconds=args.lock_timeout_seconds):
            cycle_timeout = _positive_timeout(args.cycle_timeout_seconds, name="cycle timeout")
            result = asyncio.run(asyncio.wait_for(_run(args, horizon_home), timeout=cycle_timeout))
        _write_state(state_path, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result = {"status": "failed", "error": _safe_error(exc), "failed_at": _utc_now()}
        _write_state(state_path, result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
