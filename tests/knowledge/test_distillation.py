import pytest

from app.knowledge.distillation import DistillationError, WeeklyDistillationService
from app.knowledge.proposal_gate import InMemoryWikiVault


def test_distillation_publishes_three_source_backed_outputs_atomically():
    vault = InMemoryWikiVault({"wiki/index.md": "# Index\n"})
    bundle = WeeklyDistillationService(vault).distill(
        project_id="project-a",
        week="2026-W30",
        sources=[{"id": "source-a", "project_id": "project-a", "raw_content": "# Agent systems\nHuman review remains necessary."}],
        pages=[{"id": "page-a", "project_id": "project-a", "path": "wiki/decisions/review.md", "content": "# Review\nKeep approval manual."}],
        rule_revision="rules-1",
    )

    assert set(bundle.paths) == {
        "distillations/2026-W30/knowledge-action.md",
        "distillations/2026-W30/content-creation.md",
        "distillations/2026-W30/context-pack.md",
    }
    assert "[source:source-a]" in vault.contents["distillations/2026-W30/knowledge-action.md"]
    assert "page-a" in vault.contents["distillations/2026-W30/context-pack.md"]
    assert vault.contents["wiki/index.md"] == "# Index\n"


def test_distillation_refuses_empty_or_cross_project_evidence():
    service = WeeklyDistillationService(InMemoryWikiVault())
    with pytest.raises(DistillationError, match="eligible source"):
        service.distill(project_id="project-a", week="2026-W30", sources=[], pages=[], rule_revision="rules-1")
    with pytest.raises(DistillationError, match="project scoped"):
        service.distill(
            project_id="project-a", week="2026-W30",
            sources=[{"id": "source-b", "project_id": "project-b", "raw_content": "leak"}],
            pages=[], rule_revision="rules-1",
        )


def test_distillation_records_changes_contradictions_quality_and_context_omissions():
    from app.knowledge.context_pack import ContextPackBuilder
    from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules

    vault = InMemoryWikiVault()
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=512).build(
        project_id="project-a",
        rules=rules,
        sources=[
            {"id": "source-new", "project_id": "project-a", "raw_content": "x" * 700},
        ],
    )
    source = {
        "id": "source-new",
        "project_id": "project-a",
        "raw_content": "# New control\nApproval now needs two reviewers.",
        "origin": "brief.md",
        "supersedes_id": "source-old",
        "metadata": {"audience": "operations leaders", "contradicts_source_ids": ["source-old"]},
    }
    WeeklyDistillationService(vault).distill(
        project_id="project-a",
        week="2026-W30",
        sources=[source],
        pages=[],
        rule_revision=rules.revision,
        evaluations=[{"status": "failed", "summary": {"findings": [{"code": "missing_constraint"}]}}],
        contradictions=[{"source_id": "source-new", "contradicts_source_id": "source-old"}],
        context_pack=pack,
    )

    action = vault.contents["distillations/2026-W30/knowledge-action.md"]
    content = vault.contents["distillations/2026-W30/content-creation.md"]
    context = vault.contents["distillations/2026-W30/context-pack.md"]
    assert "## Changed beliefs" in action and "source-old" in action
    assert "## Contradictions" in action and "source-new" in action
    assert "missing_constraint" in action
    assert "Audience: operations leaders" in content
    assert "Claim/citation pair" in content
    assert "Omitted references" in context and "source-new" in context
