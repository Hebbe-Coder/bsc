import pytest

from app.knowledge.growth_contracts import FeedbackType, MethodProposal, OutputAsset, OutputEvaluation, OutputFeedback
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_evaluator import MethodEvaluator


def _manifest(**overrides):
    return {
        "task_family": "weekly-report", "prompt_only": True, "applicability": ["weekly reporting"], "exclusions": [],
        "inputs": [{"name": "evidence"}], "outputs": [{"name": "report"}], "steps": ["Review evidence"],
        "evidence_rules": ["cite sources"], "failure_handling": ["stop on missing evidence"],
        "eval_cases": [{"id": "case-positive", "input": "evidence", "expected": "grounded report"}],
        **overrides,
    }


def _proposal_with_outputs(
    repo,
    qualities=(90, 88, 87),
    groundedness=(0.95, 0.92, 0.91),
    statuses=("accepted", "accepted", "accepted"),
):
    ids = []
    for index, (quality, grounding, status) in enumerate(zip(qualities, groundedness, statuses), 1):
        output_id = f"output-{index}"
        ids.append(output_id)
        repo.register_output(OutputAsset(id=output_id, project_id="project-a", kind="report", content_hash=(str(index) * 64),
                                         vault_path=f"outputs/2026/{output_id}/report.md", idempotency_key=output_id,
                                         run_id=f"run-{index}", status=status))
        repo.save_output_evaluation(OutputEvaluation(id=f"eval-{index}", project_id="project-a", output_id=output_id,
                                                      groundedness=grounding, task_fit=quality / 100, usefulness=quality / 100,
                                                      coherence=quality / 100, format_quality=quality / 100,
                                                      evaluator_revision=f"eval-v{index}"))
    proposal = MethodProposal(id="proposal-a", project_id="project-a", operation="create", body="# Method",
                              manifest=_manifest(), source_output_ids=ids)
    return repo.save_method_proposal(proposal)


def test_evaluator_derives_thresholds_from_immutable_output_records(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-eval.db"))
    try:
        proposal = _proposal_with_outputs(repo)
        result = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda case, _proposal: {"passed": True, "actual": case["expected"]},
                                                evaluator_revision="method-eval-v1", model_revision="deterministic", latency_ms=12)
        assert result["eligible"] is True
        assert result["comparable_uses"] == 3
        assert result["average_quality"] >= 85
        assert result["groundedness"] >= 0.90
        assert result["case_results"][0]["passed"] is True
        assert repo.get_method_proposal("project-a", proposal["id"])["status"] == "approved"
        assert repo.list_eval_runs("project-a")[0]["summary"]["evaluator_revision"] == "method-eval-v1"
    finally:
        repo.close()


def test_evaluator_treats_durably_filed_outputs_as_verified_support(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-filed.db"))
    try:
        proposal = _proposal_with_outputs(
            repo,
            statuses=("accepted", "filed", "accepted"),
        )
        result = MethodEvaluator(repo).evaluate(
            proposal,
            case_runner=lambda case, _proposal: {"passed": True, "actual": case["expected"]},
        )
        assert result["eligible"] is True
        assert result["accepted_or_reused"] is True
    finally:
        repo.close()


def test_evaluator_blocks_regression_security_and_unavailable_replay(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-regression.db"))
    try:
        proposal = _proposal_with_outputs(repo)
        repo.upsert_eval_case("project-a", "security-1", "security", {"output_id": "output-1", "expected": "deny"})
        blocked = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda *_args: False)
        assert blocked["eligible"] is False
        assert blocked["regression_failures"] >= 1
        unavailable = MethodEvaluator(repo).evaluate(proposal, case_runner=None, evaluator_revision="unavailable-v1")
        assert unavailable["eligible"] is False
        assert unavailable["evaluator_status"] == "unavailable"
    finally:
        repo.close()


def test_evaluator_rejects_manifest_schema_mismatch_and_low_grounding(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-schema.db"))
    try:
        proposal = _proposal_with_outputs(repo, groundedness=(0.7, 0.8, 0.85))
        with pytest.raises(ValueError, match="manifest"):
            MethodEvaluator(repo).evaluate({**proposal, "manifest": {"task_family": "weekly-report"}}, case_runner=lambda *_args: True)
        result = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda *_args: True)
        assert result["eligible"] is False
        assert result["groundedness"] < 0.90
    finally:
        repo.close()
