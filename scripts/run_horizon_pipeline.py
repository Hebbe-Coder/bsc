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
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(exc: Exception) -> str:
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", str(exc))
    return message[:1000]


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


async def _run(args: argparse.Namespace, horizon_home: Path) -> dict:
    sys.path.insert(0, str(horizon_home))
    from src.mcp.service import HorizonPipelineService

    service = HorizonPipelineService(runs_root=horizon_home / "data" / "mcp-runs")
    fetched = await service.fetch_items(
        hours=args.hours,
        horizon_path=str(horizon_home),
        sources=args.sources or None,
    )
    run_id = fetched["run_id"]
    scored = await service.score_items(run_id=run_id, horizon_path=str(horizon_home))
    filtered = await service.filter_items(
        run_id=run_id,
        threshold=args.threshold,
        topic_dedup=True,
        horizon_path=str(horizon_home),
    )
    enriched = None
    ready_stage = "filtered"
    if args.enrich and filtered["kept"] > 0:
        enriched = await service.enrich_items(
            run_id=run_id,
            source_stage="filtered",
            horizon_path=str(horizon_home),
        )
        ready_stage = "enriched"
    service.run_store.update_meta(
        run_id,
        {"bsc_ready_at": _utc_now(), "bsc_ready_stage": ready_stage, "producer": "bsc-scheduled"},
    )
    return {
        "status": "completed",
        "run_id": run_id,
        "fetched": fetched.get("fetched"),
        "scored": scored.get("scored"),
        "kept": filtered.get("kept"),
        "enriched": enriched.get("enriched") if enriched else 0,
        "ready_stage": ready_stage,
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
            result = asyncio.run(_run(args, horizon_home))
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
