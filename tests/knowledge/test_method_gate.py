import pytest

from app.knowledge.growth_contracts import MethodProposal
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry


def _manifest(**overrides):
    return {
        "task_family": "weekly-report", "name": "Weekly report", "prompt_only": True,
        "applicability": ["weekly reporting"], "exclusions": [], "inputs": [{"name": "evidence"}],
        "outputs": [{"name": "report"}], "steps": ["Review evidence"], "evidence_rules": ["cite sources"],
        "failure_handling": ["stop"], "eval_cases": [], **overrides,
    }


def _gate(tmp_path, manifest=None):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "gate.db"))
    repo.configure_vault("project-a", "projects/project-a", "owner")
    registry = MethodRegistry(repo, vault)
    method = registry.create_candidate("project-a", slug="weekly-report", name="Weekly report")
    proposal = registry.create_proposal(project_id="project-a", method_id=method["id"], operation="create", body="# Method",
                                        manifest=manifest or _manifest(), source_output_ids=[])
    repo.update_method_proposal_evaluation("project-a", proposal["id"], {"eligible": True, "findings": []}, "approved")
    return repo, MethodGate(repo, registry), proposal


def test_prompt_only_automatic_publication_requires_both_policies(tmp_path):
    repo, gate, proposal = _gate(tmp_path)
    try:
        with pytest.raises(PermissionError, match="global policy"):
            gate.publish_prompt_method(project_id="project-a", proposal_id=proposal["id"], actor_id="owner",
                                       actor_role="project_admin", project_policy_allows=True, global_policy_allows=False,
                                       automatic=True, policy_revision="policy-v1")
        published = gate.publish_prompt_method(project_id="project-a", proposal_id=proposal["id"], actor_id="owner",
                                               actor_role="project_admin", project_policy_allows=True, global_policy_allows=True,
                                               automatic=True, policy_revision="policy-v2")
        assert published["status"] == "published"
        assert published["active_revision_id"]
        audits = [run for run in repo.list_runs("project-a") if run["run_type"] == "method_publish"]
        assert any(run["status"] == "failed" for run in audits)
        assert any(run["status"] == "completed" for run in audits)
    finally:
        repo.close()


def test_privileged_method_requires_explicit_system_admin_approval(tmp_path):
    repo, gate, proposal = _gate(tmp_path, _manifest(prompt_only=False, requires_code=True, commands=["echo unsafe"]))
    try:
        with pytest.raises(PermissionError, match="system administrator"):
            gate.publish_prompt_method(project_id="project-a", proposal_id=proposal["id"], actor_id="owner",
                                       actor_role="project_admin", project_policy_allows=True, global_policy_allows=True)
        published = gate.publish_prompt_method(project_id="project-a", proposal_id=proposal["id"], actor_id="root",
                                               actor_role="admin", project_policy_allows=True, global_policy_allows=True,
                                               system_admin_approved=True, approval_reason="Reviewed capability request")
        assert published["status"] == "published"
    finally:
        repo.close()


def test_gate_denies_unapproved_or_ineligible_proposal_and_resolver_never_uses_draft(tmp_path):
    repo, gate, proposal = _gate(tmp_path)
    try:
        repo.update_method_proposal_evaluation("project-a", proposal["id"], {"eligible": False, "findings": ["regression"]}, "rejected")
        with pytest.raises(ValueError, match="promotion gates"):
            gate.publish_prompt_method(project_id="project-a", proposal_id=proposal["id"], actor_id="owner",
                                       actor_role="project_admin", project_policy_allows=True, global_policy_allows=True)
        with pytest.raises(ValueError, match="not published"):
            gate.registry.resolve("project-a", method_id=proposal["method_id"])
    finally:
        repo.close()
