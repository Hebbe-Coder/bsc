from app.knowledge.wiki_bootstrap import WikiBootstrapService
from app.knowledge.wiki_repository import WikiRepository


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

        assert set(first["created"]) == {"wiki/overview.md", "wiki/index.md", "wiki/log.md"}
        assert second["status"] == "already_initialized"
        assert (project_root / "AGENTS.md").read_text(encoding="utf-8") == user_agents
        assert {page["path"] for page in repo.list_pages("project-a")} == {"wiki/overview.md", "wiki/index.md", "wiki/log.md"}
    finally:
        repo.close()
