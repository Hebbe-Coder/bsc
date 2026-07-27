from hashlib import sha256

from app.knowledge.obsidian_source_projection import MANAGED_EVIDENCE_PREFIX, ObsidianSourceProjection
from app.knowledge.wiki_contracts import SourceRecord
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_sync import ObsidianSyncService


def _source(project_id: str, source_id: str, content: str, **metadata) -> SourceRecord:
    return SourceRecord(
        id=source_id,
        project_id=project_id,
        source_type="horizon_signal",
        origin=f"https://example.com/{source_id}",
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
        raw_content=content,
        trust_level="reviewed",
        metadata=metadata,
    )


def test_projects_bsc_owned_sources_as_immutable_obsidian_pages_without_sync_loop(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "projection.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = repo.create_source(_source("project-a", "horizon-1", "Original evidence body", title="Horizon signal"))
    try:
        first = ObsidianSourceProjection(repo, root).sync(project_id="project-a")
        target = project_root / MANAGED_EVIDENCE_PREFIX / "horizon-1.md"

        assert first == {"eligible": 1, "created": 1, "updated": 0, "unchanged": 0, "skipped": 0, "conflicts": 0}
        assert target.is_file()
        content = target.read_text(encoding="utf-8")
        assert 'source_id: "horizon-1"' in content
        assert "Original evidence body" in content
        assert repo.get_source("project-a", source["id"])["metadata"]["obsidian_source_mirror"]["path"] == (
            "01_Sources/bsc-evidence/horizon-1.md"
        )

        second = ObsidianSourceProjection(repo, root).sync(project_id="project-a")
        assert second == {"eligible": 1, "created": 0, "updated": 0, "unchanged": 1, "skipped": 0, "conflicts": 0}

        sync_report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        assert sync_report["scanned"] == 0
        assert sync_report["created"] == 0
        assert len(repo.list_sources("project-a")) == 1
    finally:
        repo.close()


def test_never_overwrites_a_user_edited_bsc_evidence_projection(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "projection-conflict.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.create_source(_source("project-a", "manual-1", "Immutable source"))
    try:
        projection = ObsidianSourceProjection(repo, root)
        assert projection.sync(project_id="project-a")["created"] == 1
        target = project_root / MANAGED_EVIDENCE_PREFIX / "manual-1.md"
        target.write_text("User-authored replacement", encoding="utf-8")

        report = projection.sync(project_id="project-a")
        assert report["conflicts"] == 1
        assert target.read_text(encoding="utf-8") == "User-authored replacement"
    finally:
        repo.close()


def test_never_projects_user_authored_obsidian_imports(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "projection-user-source.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.create_source(_source("project-a", "obsidian-1", "User source", sync="obsidian"))
    try:
        report = ObsidianSourceProjection(repo, root).sync(project_id="project-a")
        assert report == {"eligible": 0, "created": 0, "updated": 0, "unchanged": 0, "skipped": 1, "conflicts": 0}
        assert not (project_root / MANAGED_EVIDENCE_PREFIX).exists()
    finally:
        repo.close()
