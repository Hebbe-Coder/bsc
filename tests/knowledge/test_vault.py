from pathlib import Path

from app.knowledge.proposal_gate import InMemoryWikiVault
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
