"""SQLite/PostgreSQL parity for the complete growth persistence lifecycle."""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from app.core.database import PostgreSQLBackend
from app.knowledge.growth_contracts import (
    FeedbackType,
    MethodAsset,
    MethodProposal,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputEvaluation,
    OutputFeedback,
    ProjectKnowledgeProfile,
    SourceTriage,
    TriageDisposition,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def _exercise_lifecycle(repo: GrowthRepository, project_id: str) -> dict:
    prefix = hashlib.sha256(project_id.encode()).hexdigest()[:10]
    repo.configure_vault(project_id, f"projects/{project_id}", "postgres-test")
    repo.save_profile(
        ProjectKnowledgeProfile(project_id=project_id, user_role="researcher"),
        actor_id="postgres-test",
    )
    profile = repo.save_profile(
        ProjectKnowledgeProfile(project_id=project_id, user_role="knowledge operator"),
        actor_id="postgres-test",
    )
    source_id = f"src-{prefix}"
    repo.create_source(
        SourceRecord(
            id=source_id,
            project_id=project_id,
            source_type="postgres_fixture",
            content_hash=hashlib.sha256(source_id.encode()).hexdigest(),
            raw_content="PostgreSQL and SQLite must preserve equivalent growth state.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        )
    )
    triage = repo.save_triage(
        SourceTriage(
            id=f"tri-{prefix}",
            project_id=project_id,
            source_id=source_id,
            profile_revision=profile["revision"],
            relevance=95,
            value=90,
            freshness=85,
            outputability=90,
            connectedness=80,
            reliability_pass=True,
            disposition=TriageDisposition.KNOWLEDGE_CANDIDATE,
            reasons=["postgres parity fixture"],
        )
    )
    method = repo.create_method(
        MethodAsset(
            id=f"met-{prefix}",
            project_id=project_id,
            slug=f"parity-{prefix}",
            name="Parity method",
            status=MethodStatus.APPROVED,
        )
    )
    revision = repo.save_method_revision(
        MethodRevision(
            id=f"rev-{prefix}",
            method_id=method["id"],
            project_id=project_id,
            version=1,
            body="# Parity method\n\nUse eligible evidence.",
            manifest={"prompt_only": True},
            eval_summary={"eligible": True, "baseline": 90},
            status=MethodStatus.PUBLISHED,
        )
    )
    repo.publish_method_revision(project_id, method["id"], revision["id"])
    proposal = repo.save_method_proposal(
        MethodProposal(
            id=f"pro-{prefix}",
            project_id=project_id,
            method_id=method["id"],
            operation="revise",
            body="# Candidate revision",
            manifest={"prompt_only": True},
            source_output_ids=[],
            rationale="parity",
        )
    )
    output = repo.register_output(
        OutputAsset(
            id=f"out-{prefix}",
            project_id=project_id,
            kind="report",
            content_hash=hashlib.sha256(f"output:{prefix}".encode()).hexdigest(),
            vault_path=f"outputs/2026/out-{prefix}/report.md",
            method_revision_id=revision["id"],
            source_refs=[source_id],
            idempotency_key=f"parity:{prefix}",
            metadata={"goal": "prove parity"},
        )
    )
    duplicate = repo.register_output(
        OutputAsset(
            id=f"ignored-{prefix}",
            project_id=project_id,
            kind="report",
            content_hash=output["content_hash"],
            vault_path=f"outputs/2026/out-{prefix}/report.md",
            method_revision_id=revision["id"],
            source_refs=[source_id],
            idempotency_key=f"parity:{prefix}",
            metadata={"goal": "prove parity"},
        )
    )
    evaluation = repo.save_output_evaluation(
        OutputEvaluation(
            id=f"eval-{prefix}",
            project_id=project_id,
            output_id=output["id"],
            groundedness=0.95,
            task_fit=0.90,
            usefulness=0.90,
            coherence=0.90,
            format_quality=0.85,
        )
    )
    feedback = repo.add_output_feedback(
        OutputFeedback(
            id=f"fb-{prefix}",
            project_id=project_id,
            output_id=output["id"],
            feedback_type=FeedbackType.ACCEPTED,
            actor_id="postgres-test",
        )
    )
    repo.mark_feedback_processed(project_id, feedback["id"], proposal["id"])
    distillation = repo.record_growth_distillation(
        project_id=project_id,
        period="2026-W30",
        kind="weekly",
        input_hash=hashlib.sha256(f"inputs:{prefix}".encode()).hexdigest(),
        paths=["distillations/weekly/2026-W30/manifest.json"],
        manifest={"input_count": 1, "source_cutoff": "2026-07-22T00:00:00Z"},
    )
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    first_claim = scheduler.claim_run(
        project_id=project_id,
        job_type="growth_daily",
        idempotency_key=f"parity:{prefix}:daily",
    )
    duplicate_claim = scheduler.claim_run(
        project_id=project_id,
        job_type="growth_daily",
        idempotency_key=f"parity:{prefix}:daily",
    )
    return {
        "profile_revision": profile["revision"],
        "triage_priority": triage["priority"],
        "method_status": repo.get_method(project_id, method["id"])["status"],
        "method_version": repo.latest_method_version(project_id, method["id"]),
        "output_status": repo.get_output(project_id, output["id"])["status"],
        "output_idempotent": duplicate["id"] == output["id"],
        "quality": evaluation["quality"],
        "feedback_status": repo.get_feedback(project_id, feedback["id"])["status"],
        "lineage_count": len(repo.list_lineage(project_id)),
        "distillation_id": distillation["id"],
        "schedule_claim_idempotent": duplicate_claim == {
            "claimed": False,
            "run_id": first_claim["run_id"],
        },
        "other_project_outputs": repo.list_outputs(f"{project_id}-other"),
    }


def _cleanup_postgres(repo: GrowthRepository, project_id: str) -> None:
    tables = (
        "knowledge_growth_distillations",
        "knowledge_output_feedback",
        "knowledge_output_evaluations",
        "knowledge_graph_edges",
        "knowledge_outputs",
        "knowledge_method_proposals",
        "knowledge_method_revisions",
        "knowledge_methods",
        "knowledge_source_triage",
        "knowledge_project_profile_revisions",
        "knowledge_project_profiles",
        "knowledge_run_events",
        "knowledge_schedule_claims",
        "knowledge_schedules",
        "knowledge_runs",
        "knowledge_eval_runs",
        "knowledge_eval_cases",
        "knowledge_citations",
        "knowledge_wiki_page_revisions",
        "knowledge_wiki_pages",
        "knowledge_proposal_operations",
        "knowledge_proposals",
        "knowledge_sources",
        "knowledge_vaults",
    )
    for table in tables:
        repo._execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))  # nosec B608
    repo._commit()


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required")
def test_growth_lifecycle_is_equivalent_on_sqlite_and_postgresql(tmp_path):
    sqlite_project = f"growth-sqlite-{uuid4().hex[:10]}"
    postgres_project = f"growth-postgres-{uuid4().hex[:10]}"
    sqlite = GrowthRepository(db_path=str(tmp_path / "growth-parity.db"))
    postgres = GrowthRepository(backend=PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"]))
    try:
        sqlite_result = _exercise_lifecycle(sqlite, sqlite_project)
        postgres_result = _exercise_lifecycle(postgres, postgres_project)
        for field in (
            "profile_revision",
            "triage_priority",
            "method_status",
            "method_version",
            "output_status",
            "output_idempotent",
            "quality",
            "feedback_status",
            "lineage_count",
            "schedule_claim_idempotent",
            "other_project_outputs",
        ):
            assert postgres_result[field] == sqlite_result[field], field

        postgres.close()
        restarted = GrowthRepository(backend=PostgreSQLBackend(os.environ["TEST_POSTGRES_URL"]))
        try:
            assert restarted.get_profile(postgres_project)["revision"] == 2
            assert len(restarted.list_outputs(postgres_project)) == 1
            assert len(restarted.list_growth_distillations(postgres_project)) == 1
            _cleanup_postgres(restarted, postgres_project)
        finally:
            restarted.close()
    finally:
        sqlite.close()
        try:
            postgres.close()
        except Exception:
            pass
