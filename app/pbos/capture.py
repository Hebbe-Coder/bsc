"""Local, read-only evidence receipts for PBOS execution records."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def local_receipts(root: str, paths: list[str] | None = None) -> list[dict[str, Any]]:
    workspace = Path(root).resolve()
    receipts: list[dict[str, Any]] = []
    if not workspace.is_dir():
        return receipts
    try:
        completed = subprocess.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
        if completed.returncode == 0:
            receipts.append({"kind": "git_commit", "value": completed.stdout.strip(), "verified": True})
    except (OSError, subprocess.TimeoutExpired):
        pass
    for relative in paths or []:
        candidate = (workspace / relative).resolve()
        if workspace not in candidate.parents or not candidate.is_file():
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        receipts.append({"kind": "local_file", "path": candidate.relative_to(workspace).as_posix(), "sha256": digest, "bytes": candidate.stat().st_size, "verified": True})
    return receipts
