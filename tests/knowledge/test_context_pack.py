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
