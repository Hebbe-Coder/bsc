import pytest

from app.mcp import wiki_tools


def test_wiki_tools_validate_required_project_and_page_scope():
    with pytest.raises(ValueError, match="project_id"):
        wiki_tools.wiki_guide("")
    with pytest.raises(ValueError, match="page_id"):
        wiki_tools.wiki_read("project-a", "")


def test_wiki_guide_describes_proposal_only_safety():
    guide = wiki_tools.wiki_guide("project-a")

    assert guide["project_id"] == "project-a"
    assert "cannot access arbitrary Vault paths" in guide["safety"]
    assert guide["workflow"][-1] == "publish through a proposal gate"
