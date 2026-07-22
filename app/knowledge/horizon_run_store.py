"""Safe local reader for Horizon MCP run artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.knowledge.horizon_client import HorizonClientError, HorizonStageResponse


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_STAGE_FILES = {
    "filtered": "filtered_items.json",
    "enriched": "enriched_items.json",
}


class HorizonRunStoreClient:
    """Read Horizon's native MCP artifacts without requiring a Horizon REST service."""

    def __init__(self, *, runs_root: str | Path, max_response_bytes: int = 2_000_000) -> None:
        root = Path(runs_root).expanduser()
        self.runs_root = root.resolve()
        self.max_response_bytes = max_response_bytes
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
