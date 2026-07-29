import json

from app.knowledge.obsidian_metadata import (
    CANONICAL_METADATA_FIELDS,
    KNOWLEDGE_INDEX_ROOT,
    ObsidianMetadataService,
    is_managed_index_path,
    merge_metadata_menu_settings,
)
from app.knowledge.wiki_repository import WikiRepository


def _metadata_menu_file(root):
    path = root / ".obsidian" / "plugins" / "metadata-menu" / "data.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "presetFields": [
                    {"id": "custom-01", "name": "user_field", "path": "", "type": "Input", "options": {}}
                ],
                "enableProperties": True,
                "userPreference": "preserved",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_canonical_metadata_menu_fields_merge_without_replacing_user_fields():
    merged = merge_metadata_menu_settings(
        {
            "presetFields": [{"id": "custom-01", "name": "user_field", "path": "", "type": "Input", "options": {}}],
            "userPreference": "preserved",
        }
    )

    fields = {field["name"]: field for field in merged["presetFields"]}

    assert set(CANONICAL_METADATA_FIELDS) <= fields.keys()
    assert fields["user_field"]["id"] == "custom-01"
    assert fields["asset_kind"]["type"] == "Select"
    assert fields["captured_at"]["type"] == "Date"
    assert fields["related_sources"]["type"] == "MultiFile"
    assert fields["managed_by_bsc"]["type"] == "Boolean"
    assert merged["userPreference"] == "preserved"


def test_metadata_menu_configuration_creates_private_backup_and_is_idempotent(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    source = _metadata_menu_file(root)
    backup_root = tmp_path / "private-backups"

    first = ObsidianMetadataService(root).configure_metadata_menu(backup_root=backup_root)
    second = ObsidianMetadataService(root).configure_metadata_menu(backup_root=backup_root)

    configured = json.loads(source.read_text(encoding="utf-8"))
    fields = {field["name"] for field in configured["presetFields"]}
    backups = list(backup_root.glob("metadata-menu-*.json"))

    assert first["status"] == "configured"
    assert first["backup_created"] is True
    assert second == {"status": "unchanged", "backup_created": False, "field_count": len(CANONICAL_METADATA_FIELDS)}
    assert len(backups) == 1
    assert "user_field" in fields
    assert set(CANONICAL_METADATA_FIELDS) <= fields


def test_managed_indexes_are_scoped_idempotent_and_preserve_user_conflicts(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "metadata.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        service = ObsidianMetadataService(root, repository=repo)

        first = service.write_managed_indexes(project_id="project-a")
        index = project_root / KNOWLEDGE_INDEX_ROOT / "00-Home.md"

        assert first["created"] == 11
        assert first["updated"] == 0
        assert first["conflicts"] == 0
        assert "managed_by_bsc: true" in index.read_text(encoding="utf-8")
        assert "```dataview" in (project_root / KNOWLEDGE_INDEX_ROOT / "01-Inbox.md").read_text(encoding="utf-8")
        atlas = (project_root / KNOWLEDGE_INDEX_ROOT / "09-Evidence-Atlas.md").read_text(encoding="utf-8")
        network = (project_root / KNOWLEDGE_INDEX_ROOT / "10-Reference-Network.md").read_text(encoding="utf-8")
        assert "extraction_status" in atlas
        assert "related_sources" in network
        assert is_managed_index_path((KNOWLEDGE_INDEX_ROOT, "00-Home.md")) is True
        assert is_managed_index_path(("wiki", "index.md")) is False

        assert service.write_managed_indexes(project_id="project-a") == {"created": 0, "updated": 0, "unchanged": 11, "conflicts": 0}

        index.write_text("User changed this file", encoding="utf-8")
        conflict = service.write_managed_indexes(project_id="project-a")

        assert conflict == {"created": 0, "updated": 0, "unchanged": 10, "conflicts": 1}
        assert index.read_text(encoding="utf-8") == "User changed this file"
    finally:
        repo.close()
