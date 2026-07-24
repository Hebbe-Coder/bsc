import hashlib

import pytest

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGate, ProposalGateError
from app.knowledge.wiki_contracts import KnowledgeRun, SourceRecord, SourceStatus, WikiOperation, WikiOperationType, WikiProposal
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
            WikiOperation(
                operation=WikiOperationType.CREATE,
                path="wiki/overview.md",
                content="---\ntitle: Overview\nkind: brief\n---\n- [[wiki/concepts/approval.md]] [source:%s]\n" % source_id,
                source_ids=[source_id],
            ),
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


def test_gate_rejects_horizon_signal_without_current_project_triage(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-horizon-admission.db"))
    vault = InMemoryWikiVault()
    source = repo.create_source(
        SourceRecord(
            id="horizon-pending", project_id="project-a", source_type="horizon_signal",
            content_hash="e" * 64, raw_content="Discovery signal pending project triage.",
            status=SourceStatus.ELIGIBLE, trust_level="reviewed",
            metadata={"admission_gate": "project_triage"},
        )
    )
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal)
    try:
        with pytest.raises(ProposalGateError, match="current project triage"):
            ProposalGate(repo, vault).publish(
                proposal=proposal,
                rules_text=build_default_agents_rules("project-a"),
            )
    finally:
        repo.close()


def test_gate_uses_operation_level_sources_for_lint_evaluation_and_processing(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-operation-sources.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"]).model_copy(update={"source_ids": []})
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(
        project_id="project-a",
        case_id="operation-source",
        case_type="citation",
        expected={"source_ids": [source["id"]]},
    )
    try:
        result = ProposalGate(repo, vault).publish(
            proposal=proposal,
            rules_text=build_default_agents_rules("project-a"),
        )

        assert result["status"] == "published"
        assert repo.get_source("project-a", source["id"])["status"] == "processed"
        assert repo.get_proposal("project-a", proposal.id)["eval_summary"]["evaluation"]["status"] == "passed"
    finally:
        repo.close()


def test_gate_allows_a_governance_repair_when_all_saved_cases_are_path_scoped_elsewhere(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-not-applicable-evaluation.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(
        project_id="project-a",
        case_id="other-page-citation",
        case_type="citation",
        expected={"source_ids": [source["id"]], "scope_paths": ["wiki/concepts/other.md"]},
    )
    try:
        result = ProposalGate(repo, vault).publish(
            proposal=proposal,
            rules_text=build_default_agents_rules("project-a"),
        )

        assert result["status"] == "published"
        assert repo.get_proposal("project-a", proposal.id)["eval_summary"]["evaluation"]["status"] == "not_applicable"
    finally:
        repo.close()


def test_gate_publishes_a_versioned_agents_rules_replacement_with_audit_log(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-agents-rules.db"))
    initial_rules = build_default_agents_rules("project-a")
    next_rules = initial_rules.replace(
        "Write concise, factual, audience-appropriate material.",
        "Write concise, factual, audience-appropriate material for a defined project audience.",
    )
    vault = InMemoryWikiVault({"AGENTS.md": initial_rules, "wiki/log.md": "# Log\n"})
    source = _source(repo)
    proposal = WikiProposal(
        project_id="project-a",
        source_ids=[source["id"]],
        base_revision=ProposalGate.project_revision(vault.contents),
        operations=[
            WikiOperation(
                operation=WikiOperationType.REPLACE,
                path="AGENTS.md",
                content=next_rules,
                expected_content_hash=hashlib.sha256(initial_rules.encode("utf-8")).hexdigest(),
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content=f"\n- Updated governed project rules. [source:{source['id']}]\n",
                source_ids=[source["id"]],
            ),
        ],
    )
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(
        project_id="project-a", case_id="rules-citation", case_type="citation", expected={"source_ids": [source["id"]]}
    )
    try:
        result = ProposalGate(repo, vault).publish(proposal=proposal, rules_text=initial_rules)

        assert result["status"] == "published"
        assert vault.contents["AGENTS.md"] == next_rules
        assert repo.get_proposal("project-a", proposal.id)["status"] == "published"
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
        assert repo.get_proposal("project-a", proposal.id)["status"] == "failed"
        assert repo.get_proposal("project-a", proposal.id)["eval_summary"]["evaluation"]["status"] == "unavailable"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
    finally:
        repo.close()


def test_gate_rejects_a_compiled_snapshot_after_the_project_wiki_changes(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-revision.db"))
    vault = InMemoryWikiVault({"AGENTS.md": "rules", "wiki/index.md": "# Index\n", "wiki/log.md": "# Log\n"})
    source = _source(repo)
    proposal = _proposal(source["id"])
    proposal = proposal.model_copy(update={"base_revision": ProposalGate.project_revision(vault.contents)})
    repo.create_proposal(proposal)
    WikiEvaluator(repo).save_case(project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]})
    vault.contents["wiki/index.md"] = "# Index\n- User changed this page\n"
    try:
        with pytest.raises(ProposalGateError, match="revision conflict"):
            ProposalGate(repo, vault).publish(proposal=proposal, rules_text=build_default_agents_rules("project-a"))

        assert repo.get_proposal("project-a", proposal.id)["status"] == "draft"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
    finally:
        repo.close()


def test_gate_allows_a_compensating_proposal_to_reuse_published_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-compensation.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    initial = _proposal(source["id"])
    repo.create_proposal(initial)
    WikiEvaluator(repo).save_case(project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]})
    rules = build_default_agents_rules("project-a")
    try:
        ProposalGate(repo, vault).publish(proposal=initial, rules_text=rules)
        assert repo.get_source("project-a", source["id"])["status"] == "processed"

        compensation = WikiProposal(
            project_id="project-a",
            source_ids=[source["id"]],
            manual=True,
            operations=[
                WikiOperation(
                    operation=WikiOperationType.REPLACE,
                    path="wiki/concepts/approval.md",
                    content=(
                        "---\ntitle: Approval\nkind: concept\n---\n"
                        f"Human approval remains mandatory after review. [source:{source['id']}]"
                    ),
                    source_ids=[source["id"]],
                ),
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/index.md",
                    content="\n- [[wiki/concepts/approval.md]] reviewed compensation\n",
                    source_ids=[source["id"]],
                ),
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/overview.md",
                    content=f"\n- [[wiki/concepts/approval.md]] compensation reviewed. [source:{source['id']}]\n",
                    source_ids=[source["id"]],
                ),
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/log.md",
                    content=f"\n- Approval compensation recorded. [source:{source['id']}]\n",
                    source_ids=[source["id"]],
                ),
            ],
        )
        repo.create_proposal(compensation)

        result = ProposalGate(repo, vault).publish(proposal=compensation, rules_text=rules)

        assert result["status"] == "published"
        assert repo.get_proposal("project-a", compensation.id)["status"] == "published"
        assert "after review" in vault.contents["wiki/concepts/approval.md"]
        page = next(page for page in repo.list_pages("project-a") if page["path"] == "wiki/concepts/approval.md")
        assert len(repo.list_page_revisions("project-a", page["id"])) == 2
    finally:
        repo.close()


def test_gate_auto_publishes_only_when_project_policy_and_sources_are_trusted(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-auto.db"))
    repo.configure_vault("project-a", "projects/project-a", metadata={"auto_publish_enabled": True})
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal, actor_id="knowledge-task")
    WikiEvaluator(repo).save_case(
        project_id="project-a", case_id="citation", case_type="citation", expected={"source_ids": [source["id"]]}
    )
    run = KnowledgeRun(project_id="project-a", run_type="wiki_publish", trigger="automatic")
    repo.create_run(run)
    try:
        result = ProposalGate(repo, vault).publish(
            proposal=proposal,
            rules_text=build_default_agents_rules("project-a"),
            publication_mode="automatic",
            actor_id="knowledge-task",
            actor_role="system",
            audit_run_id=run.id,
        )

        assert result["status"] == "published"
        assert result["publication_policy"]["mode"] == "automatic"
        events = repo.list_run_events(project_id="project-a", run_id=run.id)
        assert any(event["event_type"] == "knowledge.proposal.publication.policy.accepted" for event in events)
    finally:
        repo.close()


def test_gate_admin_override_keeps_failed_gate_evidence_and_reason_in_audit(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "gate-override.db"))
    vault = InMemoryWikiVault()
    source = _source(repo)
    proposal = _proposal(source["id"])
    repo.create_proposal(proposal, actor_id="global-admin")
    run = KnowledgeRun(project_id="project-a", run_type="wiki_publish", trigger="manual", actor_id="global-admin")
    repo.create_run(run)
    reason = "Incident recovery approved by the knowledge owner"
    try:
        with pytest.raises(ProposalGateError, match="administrator permission"):
            ProposalGate(repo, vault).publish(
                proposal=proposal,
                rules_text=build_default_agents_rules("project-a"),
                actor_id="project-admin",
                actor_role="project_admin",
                override_reason=reason,
                audit_run_id=run.id,
            )
        assert repo.get_proposal("project-a", proposal.id)["status"] == "draft"

        result = ProposalGate(repo, vault).publish(
            proposal=proposal,
            rules_text=build_default_agents_rules("project-a"),
            actor_id="global-admin",
            actor_role="admin",
            override_reason=reason,
            audit_run_id=run.id,
        )

        assert result["status"] == "published"
        persisted = repo.get_proposal("project-a", proposal.id)
        assert persisted["eval_summary"]["evaluation"]["status"] == "unavailable"
        assert persisted["eval_summary"]["publication_policy"]["override_reason"] == reason
        event = next(
            item for item in repo.list_run_events(project_id="project-a", run_id=run.id)
            if item["event_type"] == "knowledge.proposal.override.applied"
        )
        assert event["payload"]["evaluation_status"] == "unavailable"
        assert event["payload"]["override_reason"] == reason
    finally:
        repo.close()
