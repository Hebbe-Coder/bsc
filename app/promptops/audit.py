"""Append-only, redacted PromptOps run ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PromptAuditStore:
    """Persists hashes and operational metadata, never prompt/output bodies."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> None:
        project_id = str(entry["project_id"])
        path = self.root / f"{project_id}.jsonl"
        payload = {
            **entry,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
            handle.flush()

    def list(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        path = self.root / f"{project_id}.jsonl"
        if not path.exists():
            return []
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return records[-limit:]
