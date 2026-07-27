import pytest

from app.knowledge.context_pack import ContextPackBuilder
from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules


def test_context_pack_keeps_priority_and_records_omitted_complete_sections():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=1_800).build(
        project_id="project-a",
        rules=rules,
        task_constraints=["The SOP must respect the customer's review cadence."],
        decisions=[{"id": "decision-1", "project_id": "project-a", "content": "Use a human approval gate."}],
        pages=[{"id": "page-1", "project_id": "project-a", "content": "# Existing decision\nApproval stays manual."}],
        sources=[
            {"id": "source-1", "project_id": "project-a", "raw_content": "Evidence claim with citation context."},
            {"id": "source-2", "project_id": "project-a", "raw_content": "x" * 1_000},
        ],
        weekly_distillation={"id": "week-30", "project_id": "project-a", "content": "Weekly signal."},
    )

    assert "[rules:project-a]" in pack.rendered
    assert "[constraint:constraint-1]" in pack.rendered
    assert "source-1" in pack.source_ids
    assert "source-2" in pack.omitted_refs
    assert pack.character_count <= pack.character_budget
    assert pack.revision


def test_context_pack_rejects_cross_project_records():
    rules = parse_project_rules(build_default_agents_rules("project-a"))

    with pytest.raises(ValueError, match="project scoped"):
        ContextPackBuilder().build(
            project_id="project-a",
            rules=rules,
            sources=[{"id": "source-b", "project_id": "project-b", "raw_content": "leak"}],
        )


def test_context_pack_keeps_a_bounded_source_excerpt_when_pages_consume_the_budget():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=2_000).build(
        project_id="project-a",
        rules=rules,
        pages=[{
            "id": "bootstrap-page",
            "project_id": "project-a",
            "content": "Published guidance. " * 120,
        }],
        sources=[{
            "id": "large-prd",
            "project_id": "project-a",
            "raw_content": "Opening requirement. " + ("Detailed requirement. " * 500) + "Closing acceptance criterion.",
        }],
    )

    assert pack.character_count <= pack.character_budget
    assert pack.source_ids == ("large-prd",)
    assert "[source:large-prd] Evidence" in pack.rendered
    assert "[CONTEXT_EXCERPT: content truncated; consult the immutable source]" in pack.rendered
    assert "Opening requirement." in pack.rendered
    assert "Closing acceptance criterion." in pack.rendered
    assert pack.rendered.split("[CONTEXT_EXCERPT", 1)[0].rstrip().endswith(".")
    assert "large-prd:excerpted_for_budget" in pack.omitted_refs


def test_context_pack_can_prioritize_full_source_evidence_over_derived_pages():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=1_800).build(
        project_id="project-a",
        rules=rules,
        pages=[{
            "id": "page-a",
            "project_id": "project-a",
            "content": "Derived context. " * 120,
        }],
        sources=[{
            "id": "source-a",
            "project_id": "project-a",
            "raw_content": "Primary evidence must remain visible before older derived pages are considered. " * 8,
        }],
        sources_first=True,
    )

    assert pack.source_ids == ("source-a",)
    assert "Primary evidence must remain visible" in pack.rendered
    assert "page-a" in pack.omitted_refs


class CandidateRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, *, project_id, top_k, rerank):
        self.calls.append((query, project_id, top_k, rerank))
        return [
            {"source": "evidence://project-a/source-relevant", "doc_format": "evidence/manual_upload"},
            {"source": "wiki://project-a/wiki/decisions/relevant.md", "doc_format": "wiki_markdown"},
        ]


def test_context_provider_uses_hybrid_retrieval_to_bound_candidate_records(tmp_path):
    from app.knowledge.context_pack import WikiContextProvider
    from app.knowledge.vault import FilesystemWikiVault
    from app.knowledge.wiki_repository import WikiRepository
    from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService

    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "context-retrieval.db"))
    repo.configure_vault("project-a", "projects/project-a")
    vault = FilesystemWikiVault(root, "project-a")
    vault.commit({"AGENTS.md": build_default_agents_rules("project-a")})
    source_index = type("Index", (), {"project_source": lambda self, source: {"status": "ingested"}})()
    relevant = SourceCaptureService(repo, search_index=source_index).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Relevant evidence", trust_level="trusted")
    ).source
    irrelevant = SourceCaptureService(repo, search_index=source_index).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Irrelevant evidence", trust_level="trusted")
    ).source
    repo._execute("UPDATE knowledge_sources SET id=? WHERE project_id=? AND id=?", ("source-relevant", "project-a", relevant["id"]))
    repo._execute("UPDATE knowledge_sources SET id=? WHERE project_id=? AND id=?", ("source-irrelevant", "project-a", irrelevant["id"]))
    repo._commit()
    repo.record_publication(
        project_id="project-a",
        contents={
            "wiki/decisions/relevant.md": "---\ntitle: Relevant\nkind: decision\n---\nRelevant decision.",
            "wiki/decisions/irrelevant.md": "---\ntitle: Irrelevant\nkind: decision\n---\nIrrelevant decision.",
        },
        source_ids=[],
    )
    retriever = CandidateRetriever()
    try:
        pack = WikiContextProvider(repo, vault_root=root, retrieval_service=retriever).build_context(
            project_id="project-a", task_constraints=["approval policy"]
        )

        assert retriever.calls == [("approval policy", "project-a", 24, True)]
        assert pack is not None
        assert "Relevant evidence" in pack.rendered
        assert "Irrelevant evidence" not in pack.rendered
        assert "Relevant decision" in pack.rendered
        assert "Irrelevant decision" not in pack.rendered
        assert set(pack.retrieval_refs) == {"source-relevant", "wiki/decisions/relevant.md"}
        assert pack.token_budget == pack.character_budget // 4
    finally:
        repo.close()
