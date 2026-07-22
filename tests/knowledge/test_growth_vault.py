from app.knowledge.vault import FilesystemWikiVault


def test_vault_commit_preserves_binary_and_unrelated_text(tmp_path):
    root = tmp_path / "vault"
    project = root / "projects" / "project-a"
    project.mkdir(parents=True)
    binary = project / "outputs" / "deck.pptx"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"PK\x03\x04\x00\xffbinary")
    (project / "notes.md").write_text("user note", encoding="utf-8")
    (project / "wiki").mkdir()
    (project / "wiki" / "overview.md").write_text("old", encoding="utf-8")

    vault = FilesystemWikiVault(root, "project-a")
    snapshot = vault.contents
    snapshot["wiki/overview.md"] = "new"
    vault.commit(snapshot)

    assert binary.read_bytes() == b"PK\x03\x04\x00\xffbinary"
    assert (project / "notes.md").read_text(encoding="utf-8") == "user note"
    assert (project / "wiki" / "overview.md").read_text(encoding="utf-8") == "new"


def test_vault_commit_can_archive_managed_text_without_touching_binary(tmp_path):
    root = tmp_path / "vault"
    project = root / "projects" / "project-a"
    project.mkdir(parents=True)
    (project / "remove.md").write_text("remove", encoding="utf-8")
    binary = project / "keep.bin"
    binary.write_bytes(b"\xff\xfe\x00\x01")

    vault = FilesystemWikiVault(root, "project-a")
    vault.commit({})

    assert not (project / "remove.md").exists()
    assert binary.read_bytes() == b"\xff\xfe\x00\x01"
