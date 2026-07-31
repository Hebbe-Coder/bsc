import pytest

from app.mcp import wiki_tools
from app.mcp import server
from app.api import mcp_http
from app.core.config import settings
from app.knowledge.ecosystem_release_gate import ReleaseEvidence
from app.knowledge.wiki_repository import WikiRepository


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


def test_mcp_release_evidence_is_read_only_project_scoped_and_redacted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "release-evidence-mcp.db")
    repo = WikiRepository(db_path=db_path)
    repo.append_release_evidence(
        "project-a",
        ReleaseEvidence(
            evidence_id="o1_secure_boundary_restart",
            state="pending",
            proof_class="none",
            detail_code="awaiting_observation",
        ),
        recorded_by="project_admin",
    )
    repo.close()
    monkeypatch.setattr(wiki_tools, "WikiRepository", lambda: WikiRepository(db_path=db_path))
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_reader", "project-a"))
    try:
        payload = wiki_tools.wiki_release_evidence("project-a")

        assert payload["project_id"] == "project-a"
        assert payload["decision"]["status"] == "implemented_with_operational_proof_pending"
        assert payload["evidence"] == [{
            "evidence_id": "o1_secure_boundary_restart",
            "state": "pending",
            "proof_class": "none",
            "observed_at": "",
            "durable_ids": [],
            "detail_code": "awaiting_observation",
            "revision": 1,
            "recorded_by": "project_admin",
        }]
        assert "raw_content" not in str(payload)
        assert server.wiki_release_evidence("project-a") == payload
        assert "wiki_release_evidence" in {item["name"] for item in mcp_http._tool_list()}
        with pytest.raises(PermissionError, match="访问权限"):
            server.wiki_release_evidence("project-b")
    finally:
        repo.close()
