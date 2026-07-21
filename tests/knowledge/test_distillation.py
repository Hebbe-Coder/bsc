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
