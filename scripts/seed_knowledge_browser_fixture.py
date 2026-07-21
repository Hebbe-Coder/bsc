"""Create isolated, realistic data for manual or automated Knowledge Workspace acceptance."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.tasks.knowledge_tasks import execute_knowledge_run


def seed(*, db_path: Path, vault_root: Path, project_id: str) -> dict[str, str]:
    vault_root.mkdir(parents=True, exist_ok=True)
    repository = WikiRepository(db_path=str(db_path))
    try:
        vault_path = f"projects/{project_id}"
        repository.configure_vault(project_id, vault_path, actor_id="browser-fixture")
        vault = FilesystemWikiVault(vault_root, project_id, vault_path)
        source = SourceCaptureService(repository).capture(
            CapturedSourceInput(
                project_id=project_id,
                source_type="manual_upload",
                origin="approval-brief.md",
                raw_content="# Approval brief\nTwo owners must approve every high-impact release.",
                trust_level="trusted",
            )
        ).source
        initial = {
            "AGENTS.md": build_default_agents_rules(project_id),
            "wiki/index.md": "# Index\n- [[decisions/release-approval]]\n",
            "wiki/log.md": "# Log\n- Initial governed approval decision.\n",
            "wiki/overview.md": "---\ntitle: Overview\nkind: brief\n---\n# Overview\nRelease controls are evidence-backed.\n",
            "wiki/decisions/release-approval.md": (
                "---\ntitle: Release Approval\nkind: decision\n---\n"
                f"Every high-impact release requires two owners. [source:{source['id']}]\n"
            ),
        }
        vault.commit(initial)
        repository.record_publication(project_id=project_id, contents=initial, source_ids=[source["id"]])

        current = dict(initial)
        current["wiki/decisions/release-approval.md"] = (
            "---\ntitle: Release Approval\nkind: decision\n---\n"
            f"Every high-impact release requires two owners and a rollback owner. [source:{source['id']}]\n"
        )
        current["wiki/log.md"] += "- Added explicit rollback ownership.\n"
        vault.commit(current)
        repository.record_publication(project_id=project_id, contents=current, source_ids=[source["id"]])

        weekly_source = SourceCaptureService(repository).capture(
            CapturedSourceInput(
                project_id=project_id,
                source_type="manual_upload",
                origin="weekly-signal.md",
                raw_content="# Weekly signal\nRollback ownership needs a named accountable role.",
                trust_level="trusted",
            )
        ).source
        proposal = WikiCommandService(repository).create_proposal(
            {
                "project_id": project_id,
                "operations": [
                    {
                        "operation": "create",
                        "path": "wiki/briefs/rollback-accountability.md",
                        "content": (
                            "---\ntitle: Rollback Accountability\nkind: brief\n---\n"
                            f"Name a rollback owner before release. [source:{weekly_source['id']}]\n"
                        ),
                        "source_ids": [weekly_source["id"]],
                    }
                ],
                "source_ids": [weekly_source["id"]],
                "rationale": "Review the proposed rollback-accountability guidance.",
            },
            actor_id="browser-fixture",
        )
        failed = KnowledgeRun(project_id=project_id, run_type="wiki_maintenance", trigger="browser-fixture")
        repository.create_run(failed)
        repository.update_run_status(project_id, failed.id, RunStatus.FAILED, error="Fixture: provider review required")
        weekly = KnowledgeRun(project_id=project_id, run_type="weekly_distillation", trigger="browser-fixture")
        repository.create_run(weekly)
        result = execute_knowledge_run(project_id, weekly.id, week="2026-W30", repository=repository)
        if result["status"] != "completed":
            raise RuntimeError(f"weekly fixture failed: {result}")
        return {
            "project_id": project_id,
            "proposal_id": proposal["id"],
            "run_id": weekly.id,
            "distillation_id": result["distillation_id"],
        }
    finally:
        repository.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--vault-root", required=True, type=Path)
    parser.add_argument("--project-id", default="browser-demo")
    arguments = parser.parse_args()
    arguments.db_path.parent.mkdir(parents=True, exist_ok=True)
    print(seed(db_path=arguments.db_path, vault_root=arguments.vault_root, project_id=arguments.project_id))


if __name__ == "__main__":
    main()
