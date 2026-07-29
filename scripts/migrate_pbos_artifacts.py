"""Export or import a scoped PBOS Artifact Graph bundle without raw Vault data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.artifacts import ArtifactGraphStore
from app.pbos.migration import export_bundle, import_bundle


def _store(path: str, tenant_id: str, project_id: str, session_id: str) -> ArtifactGraphStore:
    return ArtifactGraphStore(path, tenant_id=tenant_id, project_id=project_id, session_id=session_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "import"))
    parser.add_argument("--store", required=True, help="source store for export or destination store for import")
    parser.add_argument("--bundle", required=True, help="JSON bundle path")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--session-id", default="dbos")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    store = _store(args.store, args.tenant_id, args.project_id, args.session_id)
    bundle_path = Path(args.bundle)
    if args.mode == "export":
        bundle = export_bundle(store)
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"state": "exported", "artifact_count": len(bundle["artifacts"]), "bundle": str(bundle_path)}, ensure_ascii=False))
        return 0

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    print(json.dumps(import_bundle(store, bundle, dry_run=args.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
