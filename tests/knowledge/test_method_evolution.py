import pytest

from app.knowledge.growth_contracts import MethodAsset, MethodRevision, MethodStatus, OutputAsset, OutputEvaluation
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry


def _method_manifest():
    return {
        "prompt_only": True,
        "trigger_contract": {"positive_signals": ["weekly report"], "negative_signals": ["quick social post"]},
        "eval_cases": [
            {"id": "weekly-positive-1", "type": "should_trigger", "prompt": "weekly report", "expected_method": "weekly-report"},
            {"id": "weekly-positive-2", "type": "should_trigger", "prompt": "Create a weekly report", "expected_method": "weekly-report"},
            {"id": "weekly-positive-3", "type": "should_trigger", "prompt": "weekly report review", "expected_method": "weekly-report"},
            {"id": "weekly-negative-1", "type": "should_not_trigger", "prompt": "quick social post", "expected_method": ""},
            {"id": "weekly-negative-2", "type": "should_not_trigger", "prompt": "short social post", "expected_method": ""},
            {"id": "weekly-edge", "type": "edge_case", "prompt": "weekly report but quick social post", "expected_method": ""},
        ],
    }

def _accepted_output(repo, output_id: str, run_id: str, body: str = "# Method"):
    repo.register_output(
        OutputAsset(
            id=output_id, project_id="project-a", kind="report", title=output_id,
            content_hash=output_id.ljust(64, "a")[:64], vault_path=f"outputs/2026/{output_id}/report.md",
            idempotency_key=run_id, run_id=run_id,
            metadata={"task_family": "weekly-report", "method_candidate": {"body": body, "manifest": _method_manifest()}},
        )
    )
    repo._execute("UPDATE knowledge_outputs SET status='accepted',quality_json=? WHERE project_id=? AND id=?", ('{"quality":90,"groundedness":0.95}', "project-a", output_id))
    repo._commit()


def test_detector_requires_three_comparable_accepted_outputs(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "methods.db"))
    try:
        for index in range(2):
            _accepted_output(repo, f"output-{index}", f"run-{index}")
        assert MethodDetector(repo).detect("project-a") == []
        _accepted_output(repo, "output-2", "run-2")
        proposals = MethodDetector(repo).detect("project-a")
        assert len(proposals) == 1
        assert len(proposals[0]["source_output_ids"]) == 3
    finally:
        repo.close()


def test_method_evaluator_blocks_regression_and_gate_publishes_prompt_revision(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-gate.db"))
    try:
        vault = tmp_path / "vault"
        vault.mkdir()
        repo.configure_vault("project-a", "projects/project-a", "owner")
        method = repo.create_method(MethodAsset(project_id="project-a", slug="weekly-report", name="Weekly report"))
        for index in range(3):
            _accepted_output(repo, f"output-{index}", f"run-{index}")
            repo.save_output_evaluation(
                OutputEvaluation(
                    project_id="project-a", output_id=f"output-{index}", groundedness=0.95,
                    task_fit=0.9, usefulness=0.9, coherence=0.9, format_quality=0.9,
                    evaluator_revision=f"fixture-{index}",
                )
            )
        proposal = MethodDetector(repo).detect("project-a")[0]
        good = MethodEvaluator(repo).evaluate(proposal)
        assert good["eligible"] is True
        published = MethodGate(repo, MethodRegistry(repo, vault)).publish_prompt_method(
            project_id="project-a", proposal_id=proposal["id"], actor_id="owner", actor_role="project_admin",
            project_policy_allows=True, global_policy_allows=True,
        )
        assert published["status"] == "published"
        assert repo.get_method("project-a", method["id"])["active_revision_id"]
    finally:
        repo.close()


def _evolution_manifest(*, candidate_signal: str, include_protocol: bool = True):
    manifest = {
        "prompt_only": True,
        "trigger_contract": {"positive_signals": [candidate_signal], "negative_signals": ["quick social post"]},
        "applicability": ["weekly reporting"],
        "exclusions": ["quick social post"],
        "inputs": [{"name": "evidence"}],
        "outputs": [{"name": "weekly report"}],
        "steps": ["Review evidence", "Draft the report"],
        "evidence_rules": ["cite sources"],
        "failure_handling": ["stop on missing evidence"],
        "eval_cases": [
            {"id": "positive-1", "type": "should_trigger", "split": "positive", "prompt": f"create {candidate_signal} from evidence", "expected_method": "weekly-report"},
            {"id": "positive-2", "type": "should_trigger", "split": "positive", "prompt": f"prepare {candidate_signal}", "expected_method": "weekly-report"},
            {"id": "positive-3", "type": "should_trigger", "split": "positive", "prompt": f"review {candidate_signal}", "expected_method": "weekly-report"},
            {"id": "near-negative-1", "type": "should_not_trigger", "split": "near_negative", "prompt": "quick social post", "expected_method": ""},
            {"id": "near-negative-2", "type": "should_not_trigger", "split": "near_negative", "prompt": "short social post for a sale", "expected_method": ""},
            {"id": "holdout-1", "type": "should_trigger", "split": "holdout", "prompt": "weekly report for leadership", "expected_method": "weekly-report"},
            {"id": "holdout-2", "type": "edge_case", "split": "holdout", "prompt": "weekly report but quick social post", "expected_method": ""},
        ],
    }
    if include_protocol:
        manifest["evaluation_protocol"] = {
            "revision": "method-evolution-v1",
            "baseline_revision_id": "weekly-report-baseline",
            "mutation": {
                "dimensions": ["body"],
                "rationale": "Refine the evidence presentation without changing the routing boundary.",
            },
        }
    return manifest


def _published_method_with_candidate_outputs(repo, *, candidate_signal: str, include_protocol: bool = True):
    method = repo.create_method(MethodAsset(
        id="weekly-report-method",
        project_id="project-a",
        slug="weekly-report",
        name="Weekly report",
        status=MethodStatus.PUBLISHED,
        active_revision_id="weekly-report-baseline",
    ))
    repo.save_method_revision(MethodRevision(
        id="weekly-report-baseline",
        method_id=method["id"],
        project_id="project-a",
        version=1,
        body="# Weekly report baseline",
        manifest=_evolution_manifest(candidate_signal="weekly report"),
        eval_summary={"average_quality": 90, "groundedness": 0.95},
        status=MethodStatus.PUBLISHED,
    ))
    manifest = _evolution_manifest(candidate_signal=candidate_signal, include_protocol=include_protocol)
    for index in range(3):
        output_id = f"evolution-output-{index}"
        repo.register_output(OutputAsset(
            id=output_id,
            project_id="project-a",
            kind="report",
            content_hash=(chr(ord("a") + index) * 64),
            vault_path=f"outputs/2026/{output_id}/report.md",
            idempotency_key=f"evolution-run-{index}",
            run_id=f"evolution-run-{index}",
            method_revision_id="weekly-report-baseline",
            status="accepted",
            metadata={
                "task_family": "weekly-report",
                "method_lineage": "weekly-report-baseline",
                "method_candidate": {"body": "# Improved weekly report", "manifest": manifest},
            },
        ))
        repo.save_output_evaluation(OutputEvaluation(
            project_id="project-a",
            output_id=output_id,
            groundedness=0.95,
            task_fit=0.90,
            usefulness=0.90,
            coherence=0.90,
            format_quality=0.90,
            evaluator_revision=f"evolution-eval-{index}",
        ))
    proposal = MethodDetector(repo).detect("project-a")[0]
    return method, proposal


def test_detected_method_update_requires_a_separate_holdout_protocol_before_publish(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-update-holdout.db"))
    try:
        vault = tmp_path / "vault"
        vault.mkdir()
        repo.configure_vault("project-a", "projects/project-a", "owner")
        method, proposal = _published_method_with_candidate_outputs(
            repo,
            candidate_signal="weekly report",
            include_protocol=False,
        )

        assert proposal["operation"] == "update"
        assert proposal["method_id"] == method["id"]
        evaluation = MethodEvaluator(repo).evaluate(proposal)
        assert evaluation["eligible"] is False
        assert evaluation["evolution"]["passed"] is False
        assert "evaluation protocol" in " ".join(evaluation["findings"])

        repo.update_method_proposal_evaluation(
            "project-a",
            proposal["id"],
            {"eligible": True, "evolution": {"passed": False}, "findings": []},
            "approved",
        )
        with pytest.raises(ValueError, match="holdout"):
            MethodGate(repo, MethodRegistry(repo, vault)).publish_prompt_method(
                project_id="project-a",
                proposal_id=proposal["id"],
                actor_id="owner",
                actor_role="project_admin",
                project_policy_allows=True,
                global_policy_allows=True,
            )
    finally:
        repo.close()


def test_detected_method_update_blocks_holdout_regression_against_the_active_baseline(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-update-regression.db"))
    try:
        _method, proposal = _published_method_with_candidate_outputs(
            repo,
            candidate_signal="weekly metrics",
        )

        evaluation = MethodEvaluator(repo).evaluate(proposal)

        assert proposal["operation"] == "update"
        assert evaluation["eligible"] is False
        assert evaluation["evolution"]["holdout"]["candidate_passed"] is False
        assert evaluation["evolution"]["holdout"]["baseline_passed"] is True
        assert evaluation["evolution"]["holdout"]["regressed_case_ids"] == ["holdout-1"]
        assert evaluation["evolution"]["mutation"]["passed"] is False
    finally:
        repo.close()


def test_detected_non_regressive_method_update_can_publish_only_after_holdout_evaluation(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-update-publish.db"))
    try:
        vault = tmp_path / "vault"
        vault.mkdir()
        repo.configure_vault("project-a", "projects/project-a", "owner")
        method, proposal = _published_method_with_candidate_outputs(
            repo,
            candidate_signal="weekly report",
        )

        evaluation = MethodEvaluator(repo).evaluate(proposal)
        published = MethodGate(repo, MethodRegistry(repo, vault)).publish_prompt_method(
            project_id="project-a",
            proposal_id=proposal["id"],
            actor_id="owner",
            actor_role="project_admin",
            project_policy_allows=True,
            global_policy_allows=True,
        )

        assert evaluation["eligible"] is True, evaluation
        assert evaluation["evolution"]["passed"] is True
        assert evaluation["evolution"]["holdout"]["candidate_passed"] is True
        assert evaluation["evolution"]["holdout"]["baseline_passed"] is True
        assert evaluation["evolution"]["mutation"]["passed"] is True
        assert evaluation["evolution"]["cost"]["status"] == "not_metered"
        assert published["id"] == method["id"]
        assert published["active_revision_id"] != "weekly-report-baseline"
        revision = repo.get_method_revision("project-a", published["active_revision_id"])
        assert revision["eval_summary"]["evolution"]["passed"] is True
    finally:
        repo.close()
