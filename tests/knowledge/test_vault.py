import os
from pathlib import Path

import pytest

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGateError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import WikiOperation, WikiOperationType, WikiProposal


def test_filesystem_vault_publishes_only_inside_project_managed_directory(tmp_path):
    root = tmp_path / "Obsidian Vault"
    root.mkdir()
    user_note = root / "2026-07-21.md"
    user_note.write_text("personal note", encoding="utf-8")
    (root / ".obsidian").mkdir()
    (root / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    proposal = WikiProposal(
        project_id="project-a",
        source_ids=["source-a"],
        operations=[
            WikiOperation(
                operation=WikiOperationType.CREATE, path="wiki/concepts/approval.md",
                content="# Approval", source_ids=["source-a"],
            )
        ],
    )

    vault = FilesystemWikiVault(root, "project-a")
    vault.commit(vault.stage(proposal))

    assert (root / "projects" / "project-a" / "wiki" / "concepts" / "approval.md").read_text(encoding="utf-8") == "# Approval"
    assert user_note.read_text(encoding="utf-8") == "personal note"
    assert (root / ".obsidian" / "app.json").read_text(encoding="utf-8") == "{}"


def test_filesystem_vault_reloads_published_snapshot(tmp_path):
    root = Path(tmp_path)
    vault = FilesystemWikiVault(root, "project-a")
    proposal = WikiProposal(
        project_id="project-a", source_ids=["source-a"],
        operations=[WikiOperation(operation=WikiOperationType.APPEND, path="wiki/log.md", content="first\n", source_ids=["source-a"])],
    )
    vault.commit(vault.stage(proposal))

    assert FilesystemWikiVault(root, "project-a").contents == {"wiki/log.md": "first\n"}


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_filesystem_vault_does_not_read_symlinked_files(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret", encoding="utf-8")
    try:
        (root / "projects" / "project-a").mkdir(parents=True)
        (root / "projects" / "project-a" / "escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("current Windows principal cannot create symlinks")

    assert FilesystemWikiVault(root, "project-a").contents == {}


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_filesystem_vault_refuses_to_replace_a_project_containing_a_symlink(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret", encoding="utf-8")
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    try:
        (project_root / "escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("current Windows principal cannot create symlinks")

    with pytest.raises(ProposalGateError, match="symlink"):
        FilesystemWikiVault(root, "project-a").commit({"wiki/index.md": "# Index\n"})


def test_filesystem_vault_honors_a_safe_configured_project_mapping(tmp_path):
    root = Path(tmp_path)
    vault = FilesystemWikiVault(root, "project-a", "clients/acme/wiki-project")
    vault.commit({"wiki/overview.md": "# Acme\n"})

    assert vault.project_root == root / "clients" / "acme" / "wiki-project"
    assert (root / "clients" / "acme" / "wiki-project" / "wiki" / "overview.md").is_file()
    assert not (root / "projects" / "project-a").exists()


def test_filesystem_vault_rejects_a_mapping_that_escapes_the_configured_root(tmp_path):
    with pytest.raises(ProposalGateError, match="mapping"):
        FilesystemWikiVault(Path(tmp_path), "project-a", "../another-vault")
