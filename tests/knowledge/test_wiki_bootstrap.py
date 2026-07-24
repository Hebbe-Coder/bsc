from app.knowledge.wiki_bootstrap import WikiBootstrapService
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_bootstrap import WikiBootstrapError


def test_bootstrap_creates_only_missing_managed_files_and_indexes_pages(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    user_agents = "---\nproject_id: project-a\npage_kinds: [brief]\nwrite_root: wiki/\n---\n# User rules\n"
    (project_root / "AGENTS.md").write_text(user_agents, encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "bootstrap.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        first = WikiBootstrapService(repo).initialize(project_id="project-a")
        second = WikiBootstrapService(repo).initialize(project_id="project-a")

        assert set(first["created"]) == {"README.md", "00-Workspace.md", "wiki/overview.md", "wiki/index.md", "wiki/log.md"}
        assert set(first["created_directories"]) == set(WikiBootstrapService.managed_directories())
        assert second["status"] == "already_initialized"
        assert second["created_directories"] == []
        assert (project_root / "AGENTS.md").read_text(encoding="utf-8") == user_agents
        assert "A-layer evidence" in (project_root / "README.md").read_text(encoding="utf-8")
        assert "03_Projects/active/" in (project_root / "00-Workspace.md").read_text(encoding="utf-8")
        assert all((project_root / directory).is_dir() for directory in WikiBootstrapService.managed_directories())
        rules_page = next(page for page in repo.list_pages("project-a") if page["path"] == "AGENTS.md")
        assert rules_page["page_kind"] == "rules"
        assert repo.get_page_content("project-a", rules_page["id"])["content"] == user_agents
        assert {page["path"] for page in repo.list_pages("project-a")} == {"AGENTS.md", "wiki/overview.md", "wiki/index.md", "wiki/log.md"}
    finally:
        repo.close()


def test_bootstrap_preserves_existing_notes_while_expanding_the_operational_layout(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    user_note = project_root / "project-notes.md"
    user_note.write_text("Keep this user-authored note.", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "bootstrap-preserve.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        result = WikiBootstrapService(repo).initialize(project_id="project-a")

        assert result["status"] == "initialized"
        assert user_note.read_text(encoding="utf-8") == "Keep this user-authored note."
        assert (project_root / "00_Inbox" / "web-clipper").is_dir()
        assert (project_root / "01_Sources" / "feishu").is_dir()
        assert (project_root / "04_Outputs" / "articles").is_dir()
        assert (project_root / "02_Assets" / "curated").is_dir()
        assert (project_root / "03_Projects" / "active").is_dir()
        assert (project_root / "05_Archive" / "reviewed").is_dir()
        assert (project_root / "06_Skills" / "candidates").is_dir()
        assert (project_root / "distillations" / "每周蒸馏").is_dir()
    finally:
        repo.close()


def test_bootstrap_returns_a_governed_error_when_the_vault_cannot_be_written(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "bootstrap-error.db"))
    repo.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.FilesystemWikiVault.commit", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk denied")))
    try:
        try:
            WikiBootstrapService(repo).initialize(project_id="project-a")
        except WikiBootstrapError as exc:
            assert str(exc) == "unable to write the configured project Vault"
        else:
            raise AssertionError("bootstrap must report a governed Vault write failure")
    finally:
        repo.close()
