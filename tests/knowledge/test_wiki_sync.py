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

        assert report == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 1}
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

        assert report == {"scanned": 2, "created": 2, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0}
        assert sources["notes.txt"]["source_type"] == "obsidian_file"
        assert sources["map.canvas"]["metadata"]["extension"] == ".canvas"
    finally:
        repo.close()


def test_obsidian_sync_excludes_all_configured_managed_project_roots(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "research.md").write_text("External research", encoding="utf-8")
    (root / "clients" / "acme" / "wiki").mkdir(parents=True)
    (root / "clients" / "acme" / "wiki" / "overview.md").write_text("Managed Acme Wiki", encoding="utf-8")
    (root / "clients" / "acme" / "raw").mkdir(parents=True)
    (root / "clients" / "acme" / "raw" / "brief.md").write_text("Project A raw evidence", encoding="utf-8")
    (root / "clients" / "acme" / "inbox").mkdir(parents=True)
    (root / "clients" / "acme" / "inbox" / "signal.json").write_text('{"title":"Signal"}', encoding="utf-8")
    (root / "clients" / "beta").mkdir(parents=True)
    (root / "clients" / "beta" / "AGENTS.md").write_text("Managed Beta rules", encoding="utf-8")
    (root / "projects" / "legacy" / "wiki").mkdir(parents=True)
    (root / "projects" / "legacy" / "wiki" / "overview.md").write_text("Legacy managed Wiki", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-mappings.db"))
    repo.configure_vault("project-a", "clients/acme")
    repo.configure_vault("project-b", "clients/beta")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report == {"scanned": 3, "created": 3, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0}
        assert {source["origin"] for source in repo.list_sources("project-a")} == {
            "research.md", "clients/acme/raw/brief.md", "clients/acme/inbox/signal.json"
        }
    finally:
        repo.close()


def test_obsidian_sync_records_deletion_and_reappearance_without_destroying_evidence(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    note = root / "note.md"
    note.write_text("Immutable evidence", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-delete.db"))
    service = ObsidianSyncService(repo, root)
    try:
        first = service.sync(project_id="project-a")
        source_id = repo.list_sources("project-a")[0]["id"]
        note.unlink()
        deleted = service.sync(project_id="project-a")
        retained = repo.get_source("project-a", source_id)
        note.write_text("Immutable evidence", encoding="utf-8")
        restored = service.sync(project_id="project-a")

        assert first["created"] == 1
        assert deleted["deleted"] == 1
        assert retained["raw_content"] == "Immutable evidence"
        assert retained["metadata"]["source_present"] is False
        assert restored["duplicates"] == 1
        assert repo.get_source("project-a", source_id)["metadata"]["source_present"] is True
    finally:
        repo.close()


def test_obsidian_sync_retains_unsupported_file_fingerprint_as_rejected_evidence(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    binary = root / "research.pdf"
    binary.write_bytes(b"%PDF-test-evidence")
    repo = WikiRepository(db_path=str(tmp_path / "sync-unsupported.db"))
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report["rejected"] == 1
        source = repo.list_sources("project-a")[0]
        assert source["origin"] == "research.pdf"
        assert source["status"] == "rejected"
        assert source["metadata"]["extraction_status"] == "unsupported"
        assert source["metadata"]["byte_size"] == len(b"%PDF-test-evidence")
    finally:
        repo.close()
