from app.knowledge.feedback_router import FeedbackRouter
import pytest

from app.knowledge.growth_contracts import FeedbackType, OutputAsset, OutputEvaluation, OutputFeedback
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def test_feedback_routes_correction_to_regression_case_and_is_idempotent(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "feedback.db"))
    try:
        repo.register_output(
            OutputAsset(
                id="output-a", project_id="project-a", kind="report", title="Report", content_hash="a" * 64,
                vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a",
            )
        )
        feedback = repo.add_output_feedback(
            OutputFeedback(
                id="feedback-a", project_id="project-a", output_id="output-a", feedback_type=FeedbackType.CORRECTED,
                actor_id="owner", correction="Use the approved metric definition", comment="metric drift",
            )
        )
        router = FeedbackRouter(repo)
        first = router.process("project-a", feedback["id"], actor_id="owner", actor_role="project_admin")
        second = router.process("project-a", feedback["id"], actor_id="owner", actor_role="project_admin")
        assert first["route"] == "regression_case"
        assert first["case_id"] == second["case_id"]
        assert len(repo.list_eval_cases("project-a")) == 1
    finally:
        repo.close()


def test_accepted_feedback_requires_external_evidence_for_wiki_route(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "wiki-route.db"))
    try:
        operation = {"operation": "create", "path": "wiki/finding.md", "content": "Claim [source:source-a]", "source_ids": ["source-a"]}
        repo.register_output(OutputAsset(
            id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
            vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", status="accepted",
            metadata={"wiki_proposal": {"operations": [operation]}},
        ))
        feedback = repo.add_output_feedback(OutputFeedback(id="feedback-a", project_id="project-a", output_id="output-a",
                                                            feedback_type=FeedbackType.ACCEPTED, actor_id="owner"))
        with pytest.raises(ValueError, match="external A-layer evidence"):
            FeedbackRouter(repo).process("project-a", feedback["id"], actor_id="owner", actor_role="project_admin")
        failed = repo.get_feedback("project-a", feedback["id"])
        assert failed["status"] == "failed"
        assert failed["processed_ref"].startswith("error:")
    finally:
        repo.close()


def test_feedback_routes_wiki_method_and_failure_with_lineage(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "routes.db"))
    try:
        repo.create_source(SourceRecord(id="source-a", project_id="project-a", source_type="article", content_hash="s" * 64,
                                        raw_content="evidence", status=SourceStatus.ELIGIBLE))
        operation = {"operation": "create", "path": "wiki/finding.md", "content": "Claim [source:source-a]", "source_ids": ["source-a"]}
        method_manifest = {
            "task_family": "weekly-report", "prompt_only": True, "applicability": ["weekly reporting"], "exclusions": [],
            "inputs": [{"name": "evidence"}], "outputs": [{"name": "report"}], "steps": ["Review evidence"],
            "evidence_rules": ["Cite source IDs"], "failure_handling": ["Stop on missing evidence"], "eval_cases": [],
        }
        for output_id, feedback_type, metadata in (
            ("output-wiki", FeedbackType.ACCEPTED, {"wiki_proposal": {"operations": [operation]}}),
            ("output-method", FeedbackType.REUSED, {"method_candidate": {"body": "# Method", "manifest": method_manifest}}),
            ("output-failure", FeedbackType.REJECTED, {}),
        ):
            repo.register_output(OutputAsset(
                id=output_id, project_id="project-a", kind="report", content_hash=(output_id[7] * 64),
                vault_path=f"outputs/2026/{output_id}/report.md", idempotency_key=output_id,
                status="filed" if output_id in {"output-wiki", "output-method"} else "accepted",
                source_refs=["source-a"], quality={"quality": 90}, metadata=metadata,
            ))
            feedback = repo.add_output_feedback(OutputFeedback(id=f"feedback-{output_id}", project_id="project-a", output_id=output_id,
                                                                feedback_type=feedback_type, actor_id="owner"))
            result = FeedbackRouter(repo).process("project-a", feedback["id"], actor_id="owner", actor_role="project_admin")
            assert result["route"] in {"wiki_proposal", "method_proposal", "failure_pattern"}
        relations = {edge["edge_type"] for edge in repo.list_lineage("project-a")}
        assert {"feedback_evaluates_output", "output_proposes_page", "output_proposes_method"}.issubset(relations)
    finally:
        repo.close()


def test_accepted_plugin_output_uses_attached_lineage_without_mutating_registration(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "plugin-output-feedback.db"))
    try:
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="s" * 64,
                raw_content="External evidence",
                status=SourceStatus.ELIGIBLE,
            )
        )
        operation = {
            "operation": "create",
            "path": "wiki/plugin-finding.md",
            "content": "Claim [source:source-a]",
            "source_ids": ["source-a"],
        }
        repo.register_output(
            OutputAsset(
                id="plugin-output",
                project_id="project-a",
                kind="external_plugin_output",
                content_hash="p" * 64,
                vault_path="outputs/2026/pending/plugin.md",
                idempotency_key="obsidian-plugin|plugin.md|hash",
                metadata={"obsidian_adapter": "filesystem_output", "wiki_proposal": {"operations": [operation]}},
            )
        )
        before = repo.get_output("project-a", "plugin-output")
        assert before is not None
        immutable = {
            key: before[key]
            for key in ("content_hash", "vault_path", "idempotency_key", "source_refs", "page_refs", "metadata", "created_at", "updated_at")
        }

        repo.attach_output_evidence_references(
            "project-a", "plugin-output", source_ids=["source-a"], page_ids=[]
        )
        evidence = repo.list_output_evidence_references("project-a", "plugin-output")
        after_attachment = repo.get_output("project-a", "plugin-output")
        assert evidence == {"source_ids": ["source-a"], "page_ids": []}
        assert after_attachment is not None
        assert {key: after_attachment[key] for key in immutable} == immutable

        repo.save_output_evaluation(
            OutputEvaluation(
                project_id="project-a",
                output_id="plugin-output",
                groundedness=0.95,
                task_fit=0.90,
                usefulness=0.90,
                coherence=0.90,
                format_quality=0.90,
            )
        )
        feedback = repo.add_output_feedback(
            OutputFeedback(
                id="plugin-accepted",
                project_id="project-a",
                output_id="plugin-output",
                feedback_type=FeedbackType.ACCEPTED,
                actor_id="owner",
            )
        )
        result = FeedbackRouter(repo).process(
            "project-a", feedback["id"], actor_id="owner", actor_role="project_admin"
        )

        assert result["route"] == "wiki_proposal"
        proposal = repo.get_proposal("project-a", result["reference_id"])
        assert proposal is not None
        assert proposal["source_ids"] == ["source-a"]
    finally:
        repo.close()


def test_feedback_router_enforces_actor_and_project_scope(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "permissions.db"))
    try:
        repo.register_output(OutputAsset(id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
                                         vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a"))
        feedback = repo.add_output_feedback(OutputFeedback(id="feedback-a", project_id="project-a", output_id="output-a",
                                                            feedback_type=FeedbackType.RATED, rating=80, actor_id="owner"))
        with pytest.raises(PermissionError):
            FeedbackRouter(repo).process("project-a", feedback["id"], actor_id="intruder", actor_role="project_writer")
        with pytest.raises(KeyError):
            FeedbackRouter(repo).process("project-b", feedback["id"], actor_id="admin", actor_role="admin")
        assert repo.get_feedback("project-a", feedback["id"])["status"] == "pending"
    finally:
        repo.close()


def test_accepted_feedback_cannot_promote_output_after_source_admission_drift(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "feedback-source-drift.db"))
    try:
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        repo.register_output(OutputAsset(
            id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
            vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", status="accepted",
            source_refs=["source-a"], quality={"quality": 90},
        ))
        repo.update_source_status("project-a", "source-a", SourceStatus.REJECTED)
        feedback = repo.add_output_feedback(OutputFeedback(
            id="feedback-a", project_id="project-a", output_id="output-a",
            feedback_type=FeedbackType.ACCEPTED, actor_id="owner",
        ))

        with pytest.raises(ValueError, match="regenerate the output"):
            FeedbackRouter(repo).process("project-a", feedback["id"], actor_id="owner", actor_role="project_admin")

        assert repo.get_feedback("project-a", feedback["id"])["status"] == "failed"
        assert repo.get_output("project-a", "output-a")["status"] == "accepted"
    finally:
        repo.close()
