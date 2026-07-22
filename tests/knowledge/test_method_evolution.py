from app.knowledge.growth_contracts import MethodAsset, OutputAsset, OutputEvaluation
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry


def _accepted_output(repo, output_id: str, run_id: str, body: str = "# Method"):
    repo.register_output(
        OutputAsset(
            id=output_id, project_id="project-a", kind="report", title=output_id,
            content_hash=output_id.ljust(64, "a")[:64], vault_path=f"outputs/2026/{output_id}/report.md",
            idempotency_key=run_id, run_id=run_id,
            metadata={"task_family": "weekly-report", "method_candidate": {"body": body, "manifest": {"prompt_only": True}}},
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
