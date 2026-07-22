from concurrent.futures import ThreadPoolExecutor

import pytest

from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeLineageEdge,
    MethodAsset,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputEvaluation,
    OutputFeedback,
    OutputStatus,
    ProjectKnowledgeProfile,
    SourceTriage,
    TriageDisposition,
)
from app.knowledge.growth_repository import (
    GrowthRepository,
    LifecycleConflictError,
    LineageConflictError,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def test_growth_records_are_project_scoped_and_profile_revisions_are_immutable(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth.db"))
    try:
        saved = repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        assert saved["revision"] == 1
        updated = repo.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", user_role="researcher"), actor_id="owner"
        )
        assert updated["revision"] == 2
        assert repo.get_profile("project-a")["user_role"] == "researcher"
        assert repo.get_profile("project-b") is None

        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="evidence",
                status=SourceStatus.VALIDATED,
            )
        )
        triage = SourceTriage(
            project_id="project-a",
            source_id="source-a",
            profile_revision=2,
            relevance=90,
            value=90,
            freshness=80,
            outputability=80,
            connectedness=70,
            reliability_pass=True,
            disposition=TriageDisposition.KNOWLEDGE_CANDIDATE,
        )
        row = repo.save_triage(triage)
        assert row["priority"] == 84
        assert repo.list_triage("project-b") == []
    finally:
        repo.close()


def test_output_registration_evaluation_feedback_and_lineage_are_idempotent(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "output.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="c" * 64,
                raw_content="evidence",
                status=SourceStatus.ELIGIBLE,
            )
        )
        output = OutputAsset(
            id="output-a",
            project_id="project-a",
            kind="report",
            title="Report",
            content_hash="d" * 64,
            vault_path="outputs/2026/output-a/report.md",
            idempotency_key="run-a|report|d",
            source_refs=["source-a"],
        )
        first = repo.register_output(output)
        second = repo.register_output(output)
        assert first["id"] == second["id"] == "output-a"

        evaluation = repo.save_output_evaluation(
            OutputEvaluation(
                project_id="project-a",
                output_id="output-a",
                groundedness=0.95,
                task_fit=0.9,
                usefulness=0.9,
                coherence=0.9,
                format_quality=0.8,
                evaluator_revision="deterministic-v1",
            )
        )
        assert evaluation["quality"] == 91
        feedback = repo.add_output_feedback(
            OutputFeedback(
                project_id="project-a",
                output_id="output-a",
                feedback_type=FeedbackType.ACCEPTED,
                actor_id="owner",
            )
        )
        assert feedback["feedback_type"] == "accepted"

        edge = KnowledgeLineageEdge(
            project_id="project-a",
            from_type="source",
            from_id="source-a",
            to_type="output",
            to_id="output-a",
            relation="output_used_source",
        )
        assert repo.add_lineage_edge(edge)["id"] == repo.add_lineage_edge(edge)["id"]
        assert len(repo.list_lineage("project-a")) == 1
        assert repo.list_lineage("project-b") == []
    finally:
        repo.close()


def test_lineage_rejects_cross_project_and_cycles(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "lineage.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.register_output(
            OutputAsset(
                id="output-a",
                project_id="project-a",
                kind="report",
                title="Report",
                content_hash="e" * 64,
                vault_path="outputs/2026/output-a/report.md",
                idempotency_key="output-a",
            )
        )
        repo.register_output(
            OutputAsset(
                id="output-b",
                project_id="project-a",
                kind="report",
                title="Report B",
                content_hash="f" * 64,
                vault_path="outputs/2026/output-b/report.md",
                idempotency_key="output-b",
            )
        )
        repo.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id="project-a", from_type="output", from_id="output-a", to_type="output", to_id="output-b", relation="output_used_page"
            )
        )
        with pytest.raises(LineageConflictError):
            repo.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id="project-a", from_type="output", from_id="output-b", to_type="output", to_id="output-a", relation="output_used_page"
                )
            )
        with pytest.raises(LineageConflictError):
            repo.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id="project-b", from_type="output", from_id="output-a", to_type="output", to_id="output-b", relation="output_used_page"
                )
            )
    finally:
        repo.close()


def test_method_revisions_are_bounded_ordered_and_project_scoped(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-revisions.db"))
    try:
        method = MethodAsset(
            id="method-a",
            project_id="project-a",
            slug="weekly-report",
            name="Weekly report",
        )
        repo.create_method(method)
        for version in range(1, 4):
            repo.save_method_revision(
                MethodRevision(
                    id=f"revision-{version}",
                    project_id="project-a",
                    method_id=method.id,
                    version=version,
                    body=f"version {version}",
                )
            )

        assert [row["version"] for row in repo.list_method_revisions("project-a", method.id, limit=2)] == [3, 2]
        assert [row["version"] for row in repo.list_method_revisions(
            "project-a", method.id, before_version=3
        )] == [2, 1]
        with pytest.raises(KeyError, match="not found in project"):
            repo.list_method_revisions("project-b", method.id)
    finally:
        repo.close()


def test_method_deprecation_is_guarded_idempotent_and_audited(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-deprecate.db"))
    try:
        method = MethodAsset(
            id="method-a",
            project_id="project-a",
            slug="weekly-report",
            name="Weekly report",
            status=MethodStatus.PUBLISHED,
            active_revision_id="revision-a",
        )
        repo.create_method(method)
        repo.save_method_revision(
            MethodRevision(
                id="revision-a",
                project_id="project-a",
                method_id=method.id,
                version=1,
                body="published body",
                status=MethodStatus.PUBLISHED,
            )
        )

        first = repo.deprecate_method(
            "project-a",
            method.id,
            actor_id="owner",
            reason="replaced by a better method",
            expected_active_revision_id="revision-a",
        )
        second = repo.deprecate_method(
            "project-a",
            method.id,
            actor_id="owner",
            reason="replaced by a better method",
            expected_active_revision_id="revision-a",
        )

        assert first["status"] == second["status"] == "deprecated"
        assert first["active_revision_id"] == "revision-a"
        audits = [run for run in repo.list_runs("project-a") if run["run_type"] == "method_deprecate"]
        assert len(audits) == 1
        assert audits[0]["actor_id"] == "owner"
        assert audits[0]["input_refs"]["reason"] == "replaced by a better method"
        assert repo.list_run_events(project_id="project-a", run_id=audits[0]["id"])[0]["event_type"] == "knowledge.method.deprecated"

        with pytest.raises(KeyError, match="not found in project"):
            repo.deprecate_method(
                "project-b", method.id, actor_id="owner", reason="cross project"
            )
        with pytest.raises(LifecycleConflictError, match="active revision conflict"):
            repo.deprecate_method(
                "project-a",
                method.id,
                actor_id="owner",
                reason="stale writer",
                expected_active_revision_id="stale-revision",
            )

        candidate = repo.create_method(
            MethodAsset(
                id="candidate-a",
                project_id="project-a",
                slug="candidate",
                name="Candidate",
            )
        )
        with pytest.raises(LifecycleConflictError, match="published to deprecated"):
            repo.deprecate_method(
                "project-a", candidate["id"], actor_id="owner", reason="invalid state"
            )
        assert repo.get_method("project-a", candidate["id"])["status"] == "candidate"
    finally:
        repo.close()


def test_output_filing_is_guarded_concurrent_idempotent_and_audited(tmp_path):
    db_path = str(tmp_path / "output-file.db")
    repo = GrowthRepository(db_path=db_path)
    try:
        output = repo.register_output(
            OutputAsset(
                id="output-a",
                project_id="project-a",
                kind="report",
                content_hash="a" * 64,
                vault_path="outputs/2026/output-a/report.md",
                idempotency_key="output-a",
                status=OutputStatus.ACCEPTED,
                metadata={"immutable": "preserved"},
            )
        )

        def file_once(actor_id: str):
            return repo.file_output(
                "project-a",
                output["id"],
                actor_id=actor_id,
                reason="approved delivery",
                expected_status=OutputStatus.ACCEPTED,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(file_once, ["owner-a", "owner-b"]))

        assert {result["status"] for result in results} == {"filed"}
        filed = repo.get_output("project-a", output["id"])
        assert filed["metadata"] == {"immutable": "preserved"}
        audits = [run for run in repo.list_runs("project-a") if run["run_type"] == "output_file"]
        assert len(audits) == 1
        assert repo.list_run_events(project_id="project-a", run_id=audits[0]["id"])[0]["event_type"] == "knowledge.output.filed"

        with pytest.raises(KeyError, match="not found in project"):
            repo.file_output(
                "project-b", output["id"], actor_id="owner", reason="cross project"
            )

        rejected = repo.register_output(
            OutputAsset(
                id="output-rejected",
                project_id="project-a",
                kind="report",
                content_hash="b" * 64,
                vault_path="outputs/2026/output-rejected/report.md",
                idempotency_key="output-rejected",
                status=OutputStatus.REJECTED,
            )
        )
        with pytest.raises(LifecycleConflictError, match="accepted to filed"):
            repo.file_output(
                "project-a",
                rejected["id"],
                actor_id="owner",
                reason="invalid state",
                expected_status=OutputStatus.REJECTED,
            )
        assert repo.get_output("project-a", rejected["id"])["status"] == "rejected"
    finally:
        repo.close()


def test_lifecycle_audit_failure_rolls_back_method_and_output_state(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "lifecycle-rollback.db"))
    try:
        method = repo.create_method(
            MethodAsset(
                id="method-a",
                project_id="project-a",
                slug="published-method",
                name="Published method",
                status=MethodStatus.PUBLISHED,
                active_revision_id="revision-a",
            )
        )
        repo.save_method_revision(
            MethodRevision(
                id="revision-a",
                project_id="project-a",
                method_id=method["id"],
                version=1,
                body="published body",
                status=MethodStatus.PUBLISHED,
            )
        )
        output = repo.register_output(
            OutputAsset(
                id="output-a",
                project_id="project-a",
                kind="report",
                content_hash="c" * 64,
                vault_path="outputs/2026/output-a/report.md",
                idempotency_key="output-a",
                status=OutputStatus.ACCEPTED,
            )
        )

        def fail_audit(**_kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(repo, "_record_lifecycle_audit", fail_audit)
        with pytest.raises(RuntimeError, match="audit unavailable"):
            repo.deprecate_method(
                "project-a", method["id"], actor_id="owner", reason="retire"
            )
        with pytest.raises(RuntimeError, match="audit unavailable"):
            repo.file_output(
                "project-a", output["id"], actor_id="owner", reason="file"
            )

        assert repo.get_method("project-a", method["id"])["status"] == "published"
        assert repo.get_method_revision("project-a", "revision-a")["status"] == "published"
        assert repo.get_output("project-a", output["id"])["status"] == "accepted"
        assert repo.list_runs("project-a") == []
    finally:
        repo.close()
