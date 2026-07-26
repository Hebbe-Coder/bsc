from app.knowledge.growth_contracts import (
    KnowledgeFailureCode,
    KnowledgeFailurePattern,
    KnowledgeFailureRecord,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


def test_failure_records_are_project_scoped_linked_to_real_run_events_and_resolvable(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "failures.db"))
    try:
        run = repository.create_run(KnowledgeRun(
            id="run-a", project_id="project-a", run_type="growth_daily",
            trigger="manual", status=RunStatus.RUNNING,
        ))
        event = repository.append_run_event(
            project_id="project-a", run_id=run["id"], event_type="knowledge.capture.failed",
            payload={"code": "timeout"},
        )
        created = repository.create_failure_record(KnowledgeFailureRecord(
            id="failure-a", project_id="project-a",
            code=KnowledgeFailureCode.SOURCE_CAPTURE_FAILURE,
            summary="Horizon adapter timed out before an immutable source was captured.",
            run_id=run["id"], event_sequence=event["sequence"],
            evidence_refs=["horizon:2026-07-25", "run:run-a"], retryable=True,
        ))

        assert created["status"] == "open"
        assert created["diagnostic_pattern"] == KnowledgeFailurePattern.P10_DEPENDENCY_READINESS.value
        assert created["secondary_diagnostic_patterns"] == []
        assert created["evidence_refs"] == ["horizon:2026-07-25", "run:run-a"]
        assert repository.list_failure_records("project-b") == []
        assert repository.list_failure_records("project-a", run_id="run-a")[0]["id"] == "failure-a"

        resolved = repository.resolve_failure_record(
            "project-a", "failure-a", actor_id="operator-a",
            resolution_note="Retry was queued after restoring the source channel.", retry_scheduled=True,
        )
        assert resolved["status"] == "retry_scheduled"
        assert resolved["resolution"]["actor_id"] == "operator-a"
        assert resolved["resolution"]["retry_scheduled"] is True
    finally:
        repository.close()


def test_failure_records_default_to_p01_p12_and_reject_repeated_diagnoses(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "failure-patterns.db"))
    try:
        created = repository.create_failure_record(KnowledgeFailureRecord(
            id="failure-pattern-a", project_id="project-a",
            code=KnowledgeFailureCode.ROUTING_MISMATCH,
            summary="A routing choice selected the wrong project method.",
            secondary_diagnostic_patterns=[KnowledgeFailurePattern.P09_EVAL_BLIND_SPOT],
            minimal_structural_fix="Add a project-scoped near-negative routing regression case.",
        ))
        assert created["diagnostic_pattern"] == "P05"
        assert created["secondary_diagnostic_patterns"] == ["P09"]
        assert created["minimal_structural_fix"].startswith("Add a project")

        try:
            KnowledgeFailureRecord(
                project_id="project-a", code=KnowledgeFailureCode.ROUTING_MISMATCH,
                summary="Repeated diagnostic patterns must be rejected.",
                secondary_diagnostic_patterns=[KnowledgeFailurePattern.P05_ROUTER_MISALIGNMENT],
            )
        except ValueError as exc:
            assert "repeat the primary" in str(exc)
        else:
            raise AssertionError("primary pattern must not also be secondary")
    finally:
        repository.close()


def test_failure_records_reject_cross_project_or_missing_run_event_references(tmp_path):
    repository = GrowthRepository(db_path=str(tmp_path / "failure-scope.db"))
    try:
        repository.create_run(KnowledgeRun(
            id="run-b", project_id="project-b", run_type="growth_daily",
            trigger="manual", status=RunStatus.RUNNING,
        ))
        failure = KnowledgeFailureRecord(
            project_id="project-a", code=KnowledgeFailureCode.PROJECT_SCOPE_INTERFERENCE,
            summary="A project-scoped record attempted to reference another project run.", run_id="run-b",
        )
        try:
            repository.create_failure_record(failure)
        except KeyError as exc:
            assert "project" in str(exc)
        else:
            raise AssertionError("cross-project run reference must be rejected")
    finally:
        repository.close()
