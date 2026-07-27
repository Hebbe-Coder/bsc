from app.core.config import settings
from app.knowledge.wiki_bootstrap import WikiBootstrapService
from scripts.seed_knowledge_browser_fixture import seed


def test_browser_fixture_uses_only_the_explicit_temporary_vault(tmp_path, monkeypatch):
    fixture_vault = tmp_path / "fixture-vault"
    external_vault = tmp_path / "external-vault"
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(external_vault))
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", True)

    result = seed(
        db_path=tmp_path / "fixture.db",
        vault_root=fixture_vault,
        project_id="browser-demo",
    )

    assert result["project_id"] == "browser-demo"
    assert settings.OBSIDIAN_VAULT_ROOT == str(external_vault)
    project_root = fixture_vault / "projects" / "browser-demo"
    assert (project_root / "README.md").is_file()
    assert all((project_root / directory).is_dir() for directory in WikiBootstrapService.managed_directories())
    assert (project_root / "distillations" / "2026-W30" / "knowledge-action.md").is_file()
    assert not external_vault.exists()
