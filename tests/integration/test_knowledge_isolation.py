"""Adversarial project and filesystem isolation for the knowledge-growth domain."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGateError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import WikiOperation, WikiOperationType
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_two_projects_cannot_cross_read_sources_pages_graph_runs_or_schedules(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "isolation.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.configure_vault("project-b", "projects/project-b")
    source_a = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Project A secret", trust_level="trusted")
    ).source
    source_b = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-b", source_type="manual_upload", raw_content="Project B secret", trust_level="trusted")
    ).source
    repo.record_publication(
        project_id="project-a",
        contents={"wiki/index.md": f"# A\n[source:{source_a['id']}]"},
        source_ids=[],
    )
    repo.record_publication(
        project_id="project-b",
        contents={"wiki/index.md": f"# B\n[source:{source_b['id']}]"},
        source_ids=[],
    )
    try:
        assert repo.get_source("project-a", source_b["id"]) is None
        assert repo.get_source("project-b", source_a["id"]) is None
        page_a = repo.list_pages("project-a")[0]
        page_b = repo.list_pages("project-b")[0]
        assert repo.get_page("project-a", page_b["id"]) is None
        assert repo.get_page("project-b", page_a["id"]) is None
        assert {edge["to_id"] for edge in repo.list_graph_edges("project-a")} == {source_a["id"]}
        assert {edge["to_id"] for edge in repo.list_graph_edges("project-b")} == {source_b["id"]}
        assert repo.list_runs("project-a") == []
        assert repo.list_schedules("project-b") == []
    finally:
        repo.close()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_vault_rejects_traversal_absolute_raw_write_and_symlink_escape(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("current Windows principal cannot create symlinks")

    with pytest.raises(ProposalGateError, match="escaped"):
        FilesystemWikiVault(root, "project-a", "escape/project")
    with pytest.raises(ProposalGateError, match="mapping"):
        FilesystemWikiVault(root, "project-a", "../outside")
    with pytest.raises(ProposalGateError, match="mapping"):
        FilesystemWikiVault(root, "project-a", str(outside))
    with pytest.raises(ValidationError):
        WikiOperation(operation=WikiOperationType.CREATE, path="raw/../private.md", content="forbidden")
    operation = WikiOperation(operation=WikiOperationType.CREATE, path="raw/private.md", content="forbidden")
    from app.knowledge.wiki_contracts import WikiProposal
    with pytest.raises(ProposalGateError, match="wiki/"):
        InMemoryWikiVault().stage(WikiProposal(project_id="project-a", manual=True, operations=[operation]))
