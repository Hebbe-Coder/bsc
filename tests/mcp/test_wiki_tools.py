import pytest

from app.mcp import wiki_tools
from app.mcp import server
from app.core.config import settings


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


def test_mcp_wiki_feature_flags_gate_read_and_write_operations(monkeypatch):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _api_key="": ("admin", None))
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    with pytest.raises(PermissionError, match="disabled"):
        server._authorize_wiki_project("project-a", write=False)

    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", False)
    with pytest.raises(PermissionError, match="writes are disabled"):
        server._authorize_wiki_project("project-a", write=True)
