import pytest

from app.knowledge.wiki_compiler import WikiCompilationError, WikiCompiler
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class FakeCompilerProvider:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def compile_wiki(self, prompt):
        self.prompts.append(prompt)
        return self.response


def _eligible_source(repo):
    return SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="brief.md",
            raw_content="# Product brief\nHuman approval is mandatory.",
            trust_level="trusted",
        )
    ).source


def test_compiler_persists_draft_proposal_without_mutating_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "rationale": "Capture the explicit approval rule.",
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/decisions/human-approval.md",
                    "content": "# Human approval\n\nHuman approval is mandatory. [source:%s]" % source["id"],
                    "source_ids": [source["id"]],
                }
            ],
        }
    )
    try:
        result = WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[source["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
        )

        assert result.proposal["status"] == "draft"
        assert result.proposal["source_ids"] == [source["id"]]
        assert result.run["status"] == "completed"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
        assert "wiki/log.md" in [item["path"] for item in result.proposal["operations"]]
        assert {"wiki/overview.md", "wiki/index.md", "wiki/log.md"} <= {item["path"] for item in result.proposal["operations"]}
        assert provider.prompts
    finally:
        repo.close()


def test_compiler_rejects_horizon_signal_without_current_project_triage(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-horizon-admission.db"))
    repo.create_source(
        SourceRecord(
            id="horizon-pending", project_id="project-a", source_type="horizon_signal",
            content_hash="f" * 64, raw_content="Discovery signal pending project triage.",
            status=SourceStatus.ELIGIBLE, trust_level="reviewed",
            metadata={"admission_gate": "project_triage"},
        )
    )
    try:
        with pytest.raises(WikiCompilationError, match="current project triage"):
            WikiCompiler(repo, FakeCompilerProvider({})).compile_maintenance(
                project_id="project-a",
                source_ids=["horizon-pending"],
                trigger="manual",
                rules_text=build_default_agents_rules("project-a"),
            )
    finally:
        repo.close()


def test_compiler_removes_declared_rule_context_refs_but_keeps_real_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-rule-reference.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "rationale": "Keep the project rule as instruction and cite the source as evidence.",
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/concepts/approval.md",
                    "content": (
                        "---\ntitle: Approval\nkind: concept\n---\n\n"
                        f"Human approval is mandatory. [source:rules:project-a] [source:{source['id']}]"
                    ),
                    "source_ids": ["rules:project-a", source["id"]],
                }
            ],
        }
    )
    try:
        result = WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[source["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
        )

        operation = result.proposal["operations"][0]
        assert operation["source_ids"] == [source["id"]]
        assert "[source:rules:project-a]" not in operation["content"]
        assert f"[source:{source['id']}]" in operation["content"]
        assert result.proposal["eval_summary"]["ignored_internal_context_refs"] == ["rules:project-a"]
    finally:
        repo.close()


def test_compiler_rejects_rule_context_without_real_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-rule-only-reference.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/concepts/approval.md",
                    "content": "---\ntitle: Approval\nkind: concept\n---\n\nRule only. [source:rules:project-a]",
                    "source_ids": ["rules:project-a"],
                }
            ],
        }
    )
    try:
        with pytest.raises(WikiCompilationError, match="immutable source provenance"):
            WikiCompiler(repo, provider).compile_maintenance(
                project_id="project-a",
                source_ids=[source["id"]],
                trigger="manual",
                rules_text=build_default_agents_rules("project-a"),
            )
    finally:
        repo.close()


def test_compiler_prompt_names_only_selected_evidence_as_citable(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-allowed-evidence.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/concepts/approval.md",
                    "content": f"---\ntitle: Approval\nkind: concept\n---\n\nProject decision. [source:{source['id']}]",
                    "source_ids": [source["id"]],
                }
            ],
        }
    )
    try:
        WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[source["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
            page_snapshots=[
                {
                    "project_id": "project-a",
                    "path": "wiki/existing.md",
                    "content": "Old page. [source:other-page-evidence]",
                }
            ],
        )

        assert f"only allowed immutable source IDs for inline citations and source_ids are: {source['id']}" in provider.prompts[0]
        assert "Existing Wiki page citations are navigation context" in provider.prompts[0]
    finally:
        repo.close()


@pytest.mark.parametrize(
    "artifact",
    [
        "content truncated in source",
        "源摘录内容被截断",
        "原始资料不完整，请查阅原文",
    ],
)
def test_compiler_rejects_context_excerpt_artifacts_in_proposed_wiki_prose(tmp_path, artifact):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-context-artifact.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/concepts/approval.md",
                    "content": (
                        "---\ntitle: Approval\nkind: concept\n---\n\n"
                        f"Approval is required ({artifact}). [source:{source['id']}]"
                    ),
                    "source_ids": [source["id"]],
                }
            ],
        }
    )
    try:
        with pytest.raises(WikiCompilationError, match="context truncation artifact"):
            WikiCompiler(repo, provider).compile_maintenance(
                project_id="project-a",
                source_ids=[source["id"]],
                trigger="manual",
                rules_text=build_default_agents_rules("project-a"),
            )
    finally:
        repo.close()


@pytest.mark.parametrize(
    "response, message",
    [
        ("not-json", "object"),
        ({"operations": [{"operation": "create", "path": "raw/private.md", "content": "x", "source_ids": ["source-a"]}]}, "wiki/"),
        ({"operations": [{"operation": "create", "path": "wiki/a.md", "content": "x", "source_ids": ["unknown"]}]}, "unknown source"),
    ],
)
def test_compiler_records_failed_run_for_invalid_provider_output(tmp_path, response, message):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-failure.db"))
    source = _eligible_source(repo)
    try:
        with pytest.raises(WikiCompilationError, match=message):
            WikiCompiler(repo, FakeCompilerProvider(response)).compile_maintenance(
                project_id="project-a",
                source_ids=[source["id"]],
                trigger="manual",
                rules_text=build_default_agents_rules("project-a"),
            )

        run = repo.list_runs("project-a")[0]
        assert run["status"] == "failed"
        assert repo.list_sources("project-a", status="eligible")[0]["id"] == source["id"]
    finally:
        repo.close()


def test_compiler_persists_page_revisions_and_surfaces_explicit_contradictions(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-revisions.db"))
    first = _eligible_source(repo)
    second = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="counter.md",
            raw_content="A later counter-policy.",
            trust_level="trusted",
            metadata={"contradicts_source_ids": [first["id"]]},
        )
    ).source
    provider = FakeCompilerProvider({
        "operations": [{
            "operation": "create", "path": "wiki/decisions/policy.md",
            "content": f"---\ntitle: Policy\nkind: decision\n---\nCounter-policy. [source:{second['id']}]",
            "source_ids": [second["id"]],
        }]
    })
    pages = [{"id": "page-a", "project_id": "project-a", "path": "wiki/overview.md", "content": "# Existing\n"}]
    try:
        result = WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[first["id"], second["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
            page_snapshots=pages,
        )

        persisted_run = repo.get_run("project-a", result.run["id"])
        assert persisted_run["input_refs"]["page_hashes"]["page-a"]
        contradictions = result.proposal["eval_summary"]["contradictions"]
        assert contradictions == [{"source_id": second["id"], "contradicts_source_id": first["id"], "basis": "explicit_source_metadata"}]
        assert "Contradiction candidates" in provider.prompts[0]
    finally:
        repo.close()


def test_compiler_flags_newer_conflicting_structured_claims_for_shared_concepts(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-heuristic.db"))
    service = SourceCaptureService(repo)
    first = service.capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="policy-v1.md",
            raw_content="Approval is optional.",
            trust_level="trusted",
            metadata={"concepts": ["approval"], "claims": {"approval_required": False}},
        )
    ).source
    second = service.capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="policy-v2.md",
            raw_content="Approval is mandatory.",
            trust_level="trusted",
            metadata={"concepts": ["approval"], "claims": {"approval_required": True}},
        )
    ).source
    provider = FakeCompilerProvider({
        "operations": [{
            "operation": "create",
            "path": "wiki/decisions/approval.md",
            "content": f"Approval changed. [source:{second['id']}]",
            "source_ids": [second["id"]],
        }]
    })
    try:
        result = WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[first["id"], second["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
        )

        finding = result.proposal["eval_summary"]["contradictions"][0]
        assert finding["source_id"] == second["id"]
        assert finding["contradicts_source_id"] == first["id"]
        assert finding["basis"] == "conflicting_structured_claim_recency"
        assert finding["shared_concepts"] == "approval"
        assert finding["conflicting_claims"] == "approval_required"
    finally:
        repo.close()
