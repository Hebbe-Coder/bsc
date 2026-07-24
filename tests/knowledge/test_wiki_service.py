from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_service import WikiService


class RecordingIndex:
    def __init__(self):
        self.snapshots = []

    def sync_wiki_snapshot(self, *, project_id, contents):
        self.snapshots.append((project_id, dict(contents)))
        return {"indexed": len(contents), "removed": 0, "failures": []}


def test_wiki_service_initializes_reads_and_indexes_the_authoritative_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "service.db"))
    repo.configure_vault("project-a", "projects/project-a")
    index = RecordingIndex()
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        service = WikiService(repo, search_index=index)
        initialized = service.initialize_project("project-a", actor="owner")

        assert initialized["status"] == "initialized"
        assert initialized["indexing"] == {"indexed": 6, "removed": 0, "failures": []}
        assert index.snapshots[0][0] == "project-a"
        assert set(index.snapshots[0][1]) == {
            "AGENTS.md", "README.md", "00-Workspace.md", "wiki/overview.md", "wiki/index.md", "wiki/log.md",
        }
        status = service.get_workspace_status("project-a")
        assert status["configured"] is True
        assert status["pages"] == 4
        page = next(item for item in service.list_pages("project-a") if item["path"] == "wiki/overview.md")
        assert service.read_page("project-a", page["id"])["page"]["path"] == "wiki/overview.md"
        assert service.list_runs("project-a")[0]["run_type"] == "wiki_initialize"
    finally:
        repo.close()
