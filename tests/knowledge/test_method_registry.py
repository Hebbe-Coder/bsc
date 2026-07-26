from pathlib import Path

import pytest

from app.knowledge.growth_contracts import MethodProposal
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_registry import MethodPublicationConflict, MethodRegistry


def _manifest(**overrides):
    return {
        "task_family": "weekly-report", "name": "Weekly report", "prompt_only": True,
        "applicability": ["weekly project reporting"], "exclusions": ["incident response"],
        "inputs": [{"name": "evidence"}], "outputs": [{"name": "report"}],
        "steps": ["Review evidence", "Draft report"], "evidence_rules": ["Cite registered sources"],
        "failure_handling": ["Stop when evidence is unavailable"], "eval_cases": [],
        **overrides,
    }


def _registry(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "methods.db"))
    repo.configure_vault("project-a", "projects/project-a", "owner")
    repo.configure_vault("project-b", "projects/project-b", "owner")
    return repo, MethodRegistry(repo, vault), vault


def _approve(repo, proposal):
    summary = {"eligible": True, "average_quality": 90, "groundedness": 0.95}
    if proposal.get("operation") == "update":
        # These registry tests model a proposal that has already passed the
        # evaluator; detailed holdout behavior belongs to method evolution tests.
        summary["evolution"] = {"passed": True, "status": "fixture"}
    return repo.update_method_proposal_evaluation(
        proposal["project_id"], proposal["id"],
        summary, "approved",
    )


def test_registry_publishes_immutable_revision_and_resolves_exact_version(tmp_path):
    repo, registry, vault = _registry(tmp_path)
    try:
        method = registry.create_candidate("project-a", slug="weekly-report", name="Weekly report")
        proposal = registry.create_proposal(project_id="project-a", method_id=method["id"], operation="create",
                                            body="# Weekly method\n\nUse evidence.", manifest=_manifest(), source_output_ids=[])
        proposal = _approve(repo, proposal)
        published = registry.publish_proposal(proposal, expected_active_revision_id="")
        resolved = registry.resolve("project-a", method_id=method["id"])
        assert resolved["revision"]["id"] == published["revision"]["id"]
        assert resolved["revision"]["version"] == 1
        skill = vault / "projects" / "project-a" / "methods" / "weekly-report" / "SKILL.md"
        assert "bsc_managed: true" in skill.read_text(encoding="utf-8")
        assert (skill.parent / "evals.md").exists()
        assert (skill.parent / "revisions" / f"0001-{resolved['revision']['id']}" / "SKILL.md").exists()
        with pytest.raises(ValueError, match="immutable"):
            registry.publish_proposal({**proposal, "body": "changed"}, expected_active_revision_id=resolved["revision"]["id"])
    finally:
        repo.close()


def test_duplicate_proposal_and_optimistic_publication_are_safe(tmp_path):
    repo, registry, _ = _registry(tmp_path)
    try:
        method = registry.create_candidate("project-a", slug="weekly-report", name="Weekly report")
        kwargs = dict(project_id="project-a", method_id=method["id"], operation="create", body="# Method", manifest=_manifest(), source_output_ids=[])
        first = registry.create_proposal(**kwargs)
        second = registry.create_proposal(**kwargs)
        assert first["id"] == second["id"]
        first = _approve(repo, first)
        published = registry.publish_proposal(first, expected_active_revision_id="")
        newer = registry.create_proposal(**{**kwargs, "operation": "update", "body": "# Method v2"})
        newer = _approve(repo, newer)
        with pytest.raises(MethodPublicationConflict):
            registry.publish_proposal(newer, expected_active_revision_id="stale")
        assert registry.resolve("project-a", method_id=method["id"])["revision"]["id"] == published["revision"]["id"]
    finally:
        repo.close()


def test_deprecation_rollback_and_project_isolation(tmp_path):
    repo, registry, _ = _registry(tmp_path)
    try:
        method = registry.create_candidate("project-a", slug="weekly-report", name="Weekly report")
        first_proposal = _approve(repo, registry.create_proposal(project_id="project-a", method_id=method["id"], operation="create",
                                                                 body="# V1", manifest=_manifest(), source_output_ids=[]))
        first = registry.publish_proposal(first_proposal, expected_active_revision_id="")
        second_proposal = _approve(repo, registry.create_proposal(project_id="project-a", method_id=method["id"], operation="update",
                                                                  body="# V2", manifest=_manifest(), source_output_ids=[]))
        second = registry.publish_proposal(second_proposal,
                                           expected_active_revision_id=first["revision"]["id"])
        rolled = registry.rollback("project-a", method["id"], target_revision_id=first["revision"]["id"],
                                   expected_active_revision_id=second["revision"]["id"], actor_id="admin")
        assert rolled["revision"]["version"] == 3
        assert rolled["revision"]["body"] == "# V1"
        with pytest.raises(KeyError):
            registry.resolve("project-b", method_id=method["id"])
        revisions = registry.list_revisions("project-a", method["id"])
        assert [revision["version"] for revision in revisions] == [3, 2, 1]
        deprecated = registry.deprecate(
            "project-a",
            method["id"],
            actor_id="admin",
            reason="superseded operational guidance",
            expected_active_revision_id=rolled["revision"]["id"],
        )
        assert deprecated["active_revision_id"] == rolled["revision"]["id"]
        with pytest.raises(ValueError, match="not published"):
            registry.resolve("project-a", method_id=method["id"])
    finally:
        repo.close()


def test_registry_rejects_unmanaged_overwrite_and_untrusted_manifest_payload(tmp_path):
    repo, registry, vault = _registry(tmp_path)
    try:
        method = registry.create_candidate("project-a", slug="weekly-report", name="Weekly report")
        method_dir = vault / "projects" / "project-a" / "methods" / "weekly-report"
        method_dir.mkdir(parents=True)
        (method_dir / "SKILL.md").write_text("user-authored", encoding="utf-8")
        proposal = registry.create_proposal(project_id="project-a", method_id=method["id"], operation="create",
                                            body="# Method", manifest=_manifest(), source_output_ids=[])
        proposal = _approve(repo, proposal)
        with pytest.raises(FileExistsError, match="unmanaged"):
            registry.publish_proposal(proposal, expected_active_revision_id="")
        with pytest.raises(ValueError, match="JSON-compatible"):
            registry.create_proposal(project_id="project-a", method_id=method["id"], operation="create",
                                     body="# Binary", manifest=_manifest(payload=b"unsafe"), source_output_ids=[])
    finally:
        repo.close()


def test_registry_blocks_gate_bypass_and_supports_explicit_supersession(tmp_path):
    repo, registry, _ = _registry(tmp_path)
    try:
        old = registry.create_candidate("project-a", slug="old-method", name="Old method")
        replacement = registry.create_candidate("project-a", slug="new-method", name="New method")
        proposal = registry.create_proposal(project_id="project-a", method_id=old["id"], operation="create",
                                            body="# Method", manifest=_manifest(task_family="old-method"), source_output_ids=[])
        with pytest.raises(ValueError, match="promotion gates"):
            registry.publish_proposal(proposal, expected_active_revision_id="")
        superseded = registry.supersede("project-a", old["id"], replacement_method_id=replacement["id"], actor_id="admin")
        assert superseded["status"] == "superseded"
        assert repo.list_lineage("project-a", relation="method_supersedes_method")[0]["to_id"] == replacement["id"]
        with pytest.raises(ValueError):
            registry.create_candidate("project-a", slug="../unsafe", name="Unsafe")
    finally:
        repo.close()
