import pytest

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_source_gate import OutputSourceAdmissionError
from app.knowledge.output_evaluator import OutputEvaluator
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def test_output_quality_uses_component_score_and_updates_lifecycle(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "eval.db"))
    try:
        repo.create_source(
            SourceRecord(id="source-a", project_id="project-a", source_type="article", content_hash="s" * 64,
                         raw_content="evidence", status=SourceStatus.ELIGIBLE)
        )
        repo.register_output(
            OutputAsset(
                id="output-a", project_id="project-a", kind="report", title="Report", content_hash="a" * 64,
                vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", source_refs=["source-a"],
            )
        )
        result = OutputEvaluator(repo).evaluate(
            project_id="project-a", output_id="output-a",
            components={"groundedness": 0.95, "task_fit": 0.9, "usefulness": 0.9, "coherence": 0.9, "format_quality": 0.8},
        )
        assert result["quality"] == 91
        assert repo.get_output("project-a", "output-a")["status"] == "accepted"
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("groundedness", "expected_quality", "expected_status"),
    [(0.0, 59, "rejected"), (0.04, 60, "evaluating"), (0.84, 84, "evaluating"), (0.87, 85, "accepted")],
)
def test_output_evaluation_threshold_boundaries(tmp_path, groundedness, expected_quality, expected_status):
    repo = GrowthRepository(db_path=str(tmp_path / f"boundary-{expected_quality}.db"))
    try:
        repo.create_source(SourceRecord(id="source-a", project_id="project-a", source_type="article", content_hash="s" * 64,
                                        raw_content="evidence", status=SourceStatus.ELIGIBLE))
        repo.register_output(OutputAsset(id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
                                         vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", source_refs=["source-a"]))
        result = OutputEvaluator(repo).evaluate(
            project_id="project-a", output_id="output-a", evaluator_revision=f"boundary-{expected_quality}",
            components={"groundedness": groundedness, "task_fit": 1.0, "usefulness": 1.0, "coherence": 0.6, "format_quality": 0.5},
        )
        assert result["quality"] == expected_quality
        assert repo.get_output("project-a", "output-a")["status"] == expected_status
    finally:
        repo.close()


def test_output_evaluator_does_not_invent_score_when_unavailable(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "unavailable.db"))
    try:
        repo.register_output(OutputAsset(id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
                                         vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a"))
        result = OutputEvaluator(repo).evaluate(
            project_id="project-a", output_id="output-a", evaluator_revision="remote-v1", evaluator_available=False,
        )
        assert result["status"] == "unavailable"
        assert result["quality"] is None
        assert result["score_available"] is False
        assert repo.get_output("project-a", "output-a")["status"] == "registered"
        assert repo.list_output_evaluations("project-a", "output-a")[0]["status"] == "unavailable"
    finally:
        repo.close()


def test_output_evaluator_rejects_claimed_grounding_without_external_ancestry(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "hallucination.db"))
    try:
        repo.register_output(OutputAsset(id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
                                         vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a"))
        with pytest.raises(ValueError, match="external evidence ancestry"):
            OutputEvaluator(repo).evaluate(
                project_id="project-a", output_id="output-a",
                components={"groundedness": 0.95, "task_fit": 0.9, "usefulness": 0.9, "coherence": 0.9, "format_quality": 0.9},
            )
    finally:
        repo.close()


def test_output_evaluator_rechecks_source_admission_after_registration(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "source-drift.db"))
    try:
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        output = repo.register_output(OutputAsset(
            id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
            vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", source_refs=["source-a"],
        ))
        repo.update_source_status("project-a", "source-a", SourceStatus.REJECTED)

        with pytest.raises(OutputSourceAdmissionError, match="regenerate the output") as error:
            OutputEvaluator(repo).evaluate(
                project_id="project-a", output_id=output["id"],
                components={"groundedness": 0, "task_fit": 0.8, "usefulness": 0.8, "coherence": 0.8, "format_quality": 0.8},
            )

        assert error.value.issues == [{"source_id": "source-a", "code": "source_status_not_admitted", "status": "rejected"}]
        assert repo.get_output("project-a", output["id"])["status"] == "registered"
        assert repo.list_output_evaluations("project-a", output_id=output["id"]) == []
    finally:
        repo.close()


def test_output_evaluation_revision_is_immutable_and_retry_is_idempotent(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "idempotent.db"))
    try:
        repo.create_source(SourceRecord(id="source-a", project_id="project-a", source_type="article", content_hash="s" * 64,
                                        raw_content="evidence", status=SourceStatus.ELIGIBLE))
        repo.register_output(OutputAsset(id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
                                         vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", source_refs=["source-a"]))
        evaluator = OutputEvaluator(repo)
        components = {"groundedness": 0.9, "task_fit": 0.9, "usefulness": 0.9, "coherence": 0.9, "format_quality": 0.9}
        first = evaluator.evaluate(project_id="project-a", output_id="output-a", components=components, evaluator_revision="v1", latency_ms=17)
        second = evaluator.evaluate(project_id="project-a", output_id="output-a", components=components, evaluator_revision="v1", latency_ms=17)
        assert first["id"] == second["id"]
        with pytest.raises(ValueError, match="immutable"):
            evaluator.evaluate(project_id="project-a", output_id="output-a", components={**components, "task_fit": 0.8}, evaluator_revision="v1")
    finally:
        repo.close()
