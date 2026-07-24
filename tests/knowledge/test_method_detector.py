from app.knowledge.growth_contracts import FeedbackType, OutputAsset, OutputFeedback
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector


def _manifest():
    return {
        "prompt_only": True, "applicability": ["weekly reports"], "exclusions": [],
        "inputs": [{"name": "evidence"}], "outputs": [{"name": "report"}], "steps": ["Review evidence"],
        "evidence_rules": ["cite sources"], "failure_handling": ["stop"], "eval_cases": [],
    }


def _output(repo, output_id, run_id, *, family="weekly-report", status="accepted", input_contract="evidence-v1", security_failure=False):
    repo.register_output(OutputAsset(
        id=output_id, project_id="project-a", kind="report", content_hash=(output_id[-1] * 64),
        vault_path=f"outputs/2026/{output_id}/report.md", idempotency_key=output_id, run_id=run_id, status=status,
        quality={"quality": 90, "groundedness": 0.95},
        metadata={"task_family": family, "input_contract": input_contract, "output_contract": "report-v1",
                  "method_lineage": "base-v1", "security_failure": security_failure,
                  "method_candidate": {"body": "# Observed method", "manifest": _manifest()}},
    ))


def test_detector_requires_three_comparable_uses_and_collapses_retries(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "detector.db"))
    try:
        _output(repo, "output-1", "run-1")
        _output(repo, "output-2", "run-1")
        _output(repo, "output-3", "run-2")
        assert MethodDetector(repo).detect("project-a") == []
        _output(repo, "output-4", "run-3", status="filed")
        proposals = MethodDetector(repo).detect("project-a")
        assert len(proposals) == 1
        assert len(proposals[0]["source_output_ids"]) == 3
        assert "output-4" in proposals[0]["source_output_ids"]
        assert proposals[0]["manifest"]["detector_revision"]
    finally:
        repo.close()


def test_detector_separates_contracts_and_excludes_corrected_or_security_failed_outputs(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "detector-filter.db"))
    try:
        _output(repo, "output-1", "run-1")
        _output(repo, "output-2", "run-2", input_contract="other")
        _output(repo, "output-3", "run-3", security_failure=True)
        _output(repo, "output-4", "run-4")
        repo.add_output_feedback(OutputFeedback(id="feedback-4", project_id="project-a", output_id="output-4",
                                                feedback_type=FeedbackType.CORRECTED, actor_id="owner", correction="fix"))
        _output(repo, "output-5", "run-5", status="rejected")
        assert MethodDetector(repo).detect("project-a") == []
    finally:
        repo.close()


def test_user_proposal_can_be_created_below_detection_threshold(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "user-proposal.db"))
    try:
        proposal = MethodDetector(repo).create_user_proposal(
            "project-a", "manual-method", "# User method", [], _manifest(), actor_id="owner"
        )
        assert proposal["manifest"]["user_created"] is True
        assert proposal["source_output_ids"] == []
    finally:
        repo.close()
