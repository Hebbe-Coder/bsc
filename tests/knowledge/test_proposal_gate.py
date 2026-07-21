import pytest

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGate, ProposalGateError
from app.knowledge.wiki_contracts import WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def _source(repo):
    return SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="brief.md",
            raw_content="Human approval is mandatory.", trust_level="trusted",
        )
    ).source


def _proposal(source_id, expected_content_hash=""):
    return WikiProposal(
        project_id="project-a", source_ids=[source_id],
        operations=[
            WikiOperation(
                operation=WikiOperationType.CREATE, path="wiki/concepts/approval.md",
                content="---\ntitle: Approval\nkind: concept\n---\nHuman approval is mandatory. [source:%s]" % source_id,
                source_ids=[source_id], expected_content_hash=expected_content_hash,
            ),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/index.md", content="\n- [[wiki/concepts/approval.md]]\n", source_ids=[source_id]),
            WikiOperation(operation=WikiOperationType.APPEND, path="wiki/log.md", content="\n- Approval added. [source:%s]\n" % source_id, source_ids=[source_id]),
        ],
    )


def test_gate_publishes_all_pages_only_after_lint_and_baseline_pass(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]})
    try:
        result = ProposalGate(repo, vault).publish(
            proposal=proposal, rules_text=build_default_agents_rules("project-a")
        )

        assert result["status"] == "published"
        assert "wiki/concepts/approval.md" in vault.contents
        assert repo.get_proposal("project-a", proposal.id)["status"] == "published"
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
    finally:
        repo.close()


def test_gate_failure_leaves_vault_proposal_and_sources_unchanged(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-failure.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal)
    try:
        with pytest.raises(ProposalGateError, match="baseline"):
            ProposalGate(repo, vault).publish(proposal=proposal, rules_text=build_default_agents_rules("project-a"))

        assert vault.contents == {}
        assert repo.get_proposal("project-a", proposal.id)["status"] == "draft"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
    finally:
        repo.close()
