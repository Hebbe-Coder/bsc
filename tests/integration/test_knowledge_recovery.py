"""Recovery proof for atomic publication, durable state, and disabled dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGate, ProposalGateError
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class FailOnceVault(InMemoryWikiVault):
    def __init__(self, contents):
        super().__init__(contents)
        self.failures = 1

    def commit(self, staged):
        if self.failures:
            self.failures -= 1
            raise OSError("temporary write failure")
        super().commit(staged)


def test_transient_vault_failure_leaves_no_partial_state_and_same_proposal_can_retry(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "write-recovery.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Approval evidence", trust_level="trusted")
    ).source
    initial = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/overview.md": "---\ntitle: Overview\nkind: brief\n---\n# Overview\n",
        "wiki/index.md": "# Index\n",
        "wiki/log.md": "# Log\n",
    }
    repo.record_publication(project_id="project-a", contents=initial, source_ids=[])
    proposal = WikiProposal(
        project_id="project-a",
        source_ids=[source["id"]],
        operations=[
            WikiOperation(operation=WikiOperationType.CREATE, path="wiki/concepts/approval.md", content=f"---\ntitle: Approval\nkind: concept\n---\nApproval. [source:{source['id']}]", source_ids=[source["id"]]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/overview.md", content=f"\n- [[wiki/concepts/approval.md]] [source:{source['id']}]\n", source_ids=[source["id"]]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/index.md", content="\n- [[wiki/concepts/approval.md]]\n", source_ids=[source["id"]]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/log.md", content=f"\n- Added. [source:{source['id']}]\n", source_ids=[source["id"]]),
        ],
    )
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(project_id="project-a", case_id="source", case_type="citation", expected={"source_ids": [source["id"]]})
    vault = FailOnceVault(initial)
    try:
        with pytest.raises(OSError, match="temporary"):
            ProposalGate(repo, vault).publish(proposal=proposal, rules_text=initial["AGENTS.md"])

        assert vault.contents == initial
        assert repo.get_proposal("project-a", proposal.id)["status"] == "failed"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
        assert "wiki/concepts/approval.md" not in {page["path"] for page in repo.list_pages("project-a")}

        result = ProposalGate(repo, vault).publish(proposal=proposal, rules_text=initial["AGENTS.md"])
        assert result["status"] == "published"
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
    finally:
        repo.close()


def test_repository_restart_preserves_runs_events_revisions_and_schedules(tmp_path):
    database = str(tmp_path / "restart.db")
    first = WikiRepository(db_path=database)
    first.configure_vault("project-a", "projects/project-a")
    first.record_publication(project_id="project-a", contents={"wiki/index.md": "# Index\n"}, source_ids=[])
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    first.create_run(run)
    first.update_run_status("project-a", run.id, RunStatus.COMPLETED, output_refs={"sync": {"created": 0}})
    schedule = KnowledgeScheduler(first, scheduler_available=True).configure(
        project_id="project-a", job_type="source_sync", cron="*/15 * * * *", now=datetime(2026, 7, 22, tzinfo=timezone.utc)
    )
    page = first.list_pages("project-a")[0]
    first.close()

    restarted = WikiRepository(db_path=database)
    try:
        assert restarted.get_run("project-a", run.id)["status"] == "completed"
        assert [event["sequence"] for event in restarted.list_run_events(project_id="project-a", run_id=run.id)] == [1, 2]
        assert restarted.get_schedule("project-a", schedule["id"])["next_run_at"]
        assert restarted.list_page_revisions("project-a", page["id"])[0]["version"] == 1
    finally:
        restarted.close()


def test_disabled_celery_is_truthful_without_contacting_redis(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "disabled-celery.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    try:
        schedule = WikiCommandService(repo).configure_schedule(
            project_id="project-a", job_type="source_sync", cron="*/15 * * * *"
        )

        assert schedule["enabled"] == 0
        with pytest.raises(Exception, match="scheduler unavailable"):
            WikiCommandService(repo).set_schedule_enabled(
                project_id="project-a", schedule_id=schedule["id"], enabled=True
            )
    finally:
        repo.close()
