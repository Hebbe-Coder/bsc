"""Safe local reader for Horizon MCP run artifacts."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.knowledge.horizon_client import HorizonClientError, HorizonStageResponse


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_STAGE_FILES = {
    "filtered": "filtered_items.json",
    "enriched": "enriched_items.json",
}


@dataclass(frozen=True)
class HorizonRunStoreLocation:
    """The usable local artifact store, without exposing its filesystem path."""

    path: Path | None
    mode: str
    configured: bool

    @property
    def available(self) -> bool:
        return self.path is not None


def resolve_horizon_run_store_location(*, runs_root: str | Path, host_path: str | Path = "") -> HorizonRunStoreLocation:
    """Prefer the configured runtime mount and fall back to a local host path.

    Compose mounts the producer store at ``/horizon-runs``. A directly started
    Windows API cannot see that container path, but it can safely consume the
    same read-only producer artifacts from ``HORIZON_RUNS_HOST_PATH``.
    """
    candidates = (("run_store", runs_root), ("host_fallback", host_path))
    configured = False
    seen: set[str] = set()
    for mode, value in candidates:
        raw_path = str(value or "").strip()
        if not raw_path:
            continue
        configured = True
        candidate = Path(raw_path).expanduser()
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            return HorizonRunStoreLocation(
                path=candidate.resolve(),
                mode=mode,
                configured=True,
            )
    return HorizonRunStoreLocation(
        path=None,
        mode="unavailable" if configured else "unconfigured",
        configured=configured,
    )


class HorizonRunStoreEmptyError(HorizonClientError):
    """Raised when discovery finds no unpublished stage artifact."""


class HorizonRunStoreProducerFailureError(HorizonClientError):
    """Raised when a newer Horizon producer failure makes discovery unhealthy."""


class HorizonRunStoreStaleArtifactError(HorizonClientError):
    """Raised when automatic discovery would import an expired artifact."""


class HorizonRunStoreClient:
    """Read Horizon's native MCP artifacts without requiring a Horizon REST service."""

    def __init__(
        self,
        *,
        runs_root: str | Path,
        max_response_bytes: int = 2_000_000,
        max_artifact_age_hours: int = 48,
    ) -> None:
        root = Path(runs_root).expanduser()
        self.runs_root = root.resolve()
        self.max_response_bytes = max_response_bytes
        self.max_artifact_age_seconds = max(0, int(max_artifact_age_hours)) * 3600
        if not self.runs_root.is_dir():
            raise HorizonClientError("Horizon run artifact root does not exist")

    def fetch_stage(self, *, run_id: str, stage: str) -> HorizonStageResponse:
        if stage not in _STAGE_FILES:
            raise HorizonClientError("Horizon stage must be filtered or enriched")
        if not _RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
            raise HorizonClientError("Horizon run_id is invalid")
        run_dir = (self.runs_root / run_id).resolve()
        if not run_dir.is_relative_to(self.runs_root):
            raise HorizonClientError("Horizon run_id is invalid")
        artifact = run_dir / _STAGE_FILES[stage]
        if not artifact.is_file():
            raise HorizonClientError("Horizon stage artifact was not found")
        if artifact.is_symlink():
            raise HorizonClientError("Horizon stage artifact must not be a symlink")
        if artifact.stat().st_size > self.max_response_bytes:
            raise HorizonClientError("Horizon stage artifact exceeded the configured limit")
        try:
            decoded = json.loads(artifact.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HorizonClientError("Horizon stage artifact returned invalid JSON") from exc
        items: Any = decoded.get("items") if isinstance(decoded, dict) else decoded
        if isinstance(decoded, dict) and items is None and isinstance(decoded.get("data"), dict):
            items = decoded["data"].get("items")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise HorizonClientError("Horizon stage response must contain an items array")
        return HorizonStageResponse(run_id=run_id, stage=stage, items=items)

    def fetch_latest_stage(
        self,
        *,
        stages: tuple[str, ...] = ("enriched", "filtered"),
        exclude_run_ids: set[str] | None = None,
    ) -> HorizonStageResponse:
        """Discover the newest safe run, preferring the richest available stage."""
        if not stages or any(stage not in _STAGE_FILES for stage in stages):
            raise HorizonClientError("Horizon stages must contain filtered or enriched")
        excluded = exclude_run_ids or set()
        candidates: list[tuple[int, str, str]] = []
        for run_dir in self.runs_root.iterdir():
            run_id = run_dir.name
            if run_id in excluded or run_dir.is_symlink() or not run_dir.is_dir():
                continue
            if not _RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
                continue
            selected: tuple[int, str, str] | None = None
            for stage in stages:
                artifact = run_dir / _STAGE_FILES[stage]
                if artifact.is_file() and not artifact.is_symlink():
                    selected = (artifact.stat().st_mtime_ns, run_id, stage)
                    break
            if selected:
                candidates.append(selected)
        latest = max(candidates, key=lambda candidate: (candidate[0], candidate[1]), default=None)
        producer_failure = self._latest_producer_failure()
        if producer_failure and (latest is None or producer_failure[0] >= latest[0]):
            raise HorizonRunStoreProducerFailureError(producer_failure[1])
        if latest is None:
            raise HorizonRunStoreEmptyError("No new Horizon stage artifact was found")
        modified_at, run_id, stage = latest
        if self.max_artifact_age_seconds:
            age_seconds = max(0, (time.time_ns() - modified_at) // 1_000_000_000)
            if age_seconds > self.max_artifact_age_seconds:
                age_hours = age_seconds // 3600
                raise HorizonRunStoreStaleArtifactError(
                    f"Latest Horizon artifact is {age_hours} hours old and exceeds the discovery freshness limit"
                )
        return self.fetch_stage(run_id=run_id, stage=stage)

    def _latest_producer_failure(self) -> tuple[int, str] | None:
        """Read the producer's status sidecar without treating it as source evidence.

        The status file is only used to prevent an automated capture run from
        presenting a failed collection as an ordinary "no new artifact" day.
        A later successful stage always supersedes an earlier failure.
        """
        state_path = self.runs_root / "producer-state.json"
        if not state_path.is_file() or state_path.is_symlink():
            return None
        try:
            stat = state_path.stat()
            if stat.st_size > self.max_response_bytes:
                return None
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or str(payload.get("status") or "").lower() != "failed":
            return None
        message = str(payload.get("error") or "Horizon producer failed before publishing a stage artifact")
        return stat.st_mtime_ns, message[:500]
