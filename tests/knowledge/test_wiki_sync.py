from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_sync import ObsidianSyncService


def test_obsidian_sync_imports_user_markdown_without_reading_managed_or_hidden_files(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "welcome.md").write_text("# Welcome\nUseful knowledge", encoding="utf-8")
    (root / "empty.md").write_text("\n", encoding="utf-8")
    (root / ".obsidian").mkdir()
    (root / ".obsidian" / "internal.md").write_text("ignore", encoding="utf-8")
    (root / "projects" / "project-a" / "wiki").mkdir(parents=True)
    (root / "projects" / "project-a" / "wiki" / "generated.md").write_text("ignore", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync.db"))
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report == {"scanned": 1, "created": 1, "duplicates": 0, "skipped": 1}
        source = repo.list_sources("project-a")[0]
        assert source["vault_path"] == "welcome.md"
        assert source["status"] == "validated"
    finally:
        repo.close()


def test_obsidian_sync_imports_text_and_canvas_as_immutable_structured_evidence(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "notes.txt").write_text("A text source", encoding="utf-8")
    (root / "map.canvas").write_text('{"nodes": []}', encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-structured.db"))
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        sources = {source["origin"]: source for source in repo.list_sources("project-a")}

        assert report == {"scanned": 2, "created": 2, "duplicates": 0, "skipped": 0}
        assert sources["notes.txt"]["source_type"] == "obsidian_file"
        assert sources["map.canvas"]["metadata"]["extension"] == ".canvas"
    finally:
        repo.close()
