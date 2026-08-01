import os
from pathlib import Path

import pytest

from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_sync import ObsidianSyncService
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


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

        assert report == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 1, "blocked": 0}
        source = repo.list_sources("project-a")[0]
        assert source["vault_path"] == "welcome.md"
        assert source["status"] == "validated"
    finally:
        repo.close()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_obsidian_sync_skips_symlinked_files_outside_the_vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret", encoding="utf-8")
    (root / "inside.md").write_text("inside evidence", encoding="utf-8")
    try:
        (root / "escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("current Windows principal cannot create symlinks")
    repo = WikiRepository(db_path=str(tmp_path / "sync-symlink.db"))
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report["scanned"] == 1
        assert report["skipped"] == 1
        assert [source["origin"] for source in repo.list_sources("project-a")] == ["inside.md"]
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

        assert report == {"scanned": 2, "created": 2, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0, "blocked": 0}
        assert sources["notes.txt"]["source_type"] == "obsidian_file"
        assert sources["map.canvas"]["metadata"]["extension"] == ".canvas"
    finally:
        repo.close()


def test_obsidian_sync_scopes_a_mapped_project_to_its_own_vault_directory(tmp_path):
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

        assert report == {"scanned": 2, "created": 2, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0, "blocked": 0}
        assert {source["origin"] for source in repo.list_sources("project-a")} == {
            "clients/acme/raw/brief.md", "clients/acme/inbox/signal.json"
        }
    finally:
        repo.close()


def test_obsidian_sync_quarantines_legacy_unscoped_records_without_reading_their_files(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    (project_root / "01_Sources").mkdir(parents=True)
    (project_root / "01_Sources" / "brief.md").write_text("Project-scoped evidence", encoding="utf-8")
    transient = root / "copilot" / "copilot-conversations" / "chat.md"
    transient.parent.mkdir(parents=True)
    transient.write_text("Transient conversation that must not be read", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-scope-repair.db"))
    repo.configure_vault("project-a", "projects/project-a")
    legacy = repo.create_source(
        SourceRecord(
            project_id="project-a",
            source_type="obsidian_markdown",
            origin="copilot/copilot-conversations/chat.md",
            vault_path="copilot/copilot-conversations/chat.md",
            content_hash="a" * 64,
            raw_content="Legacy out-of-scope source retained only for audit",
            status=SourceStatus.VALIDATED,
            metadata={"sync": "obsidian"},
        )
    )
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        current = repo.get_source("project-a", legacy["id"])

        assert report == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 1, "deleted": 0, "skipped": 0, "blocked": 0}
        assert {source["origin"] for source in repo.list_sources("project-a")} == {
            "projects/project-a/01_Sources/brief.md", "copilot/copilot-conversations/chat.md"
        }
        assert current["status"] == SourceStatus.REJECTED.value
        assert current["metadata"]["source_present"] is False
        assert current["metadata"]["scope_exclusion"]["reason"] == "outside_mapped_project_root"
        assert current["metadata"]["scope_exclusion"]["project_root"] == "projects/project-a"
    finally:
        repo.close()


def test_obsidian_sync_attributes_declared_plugin_exports_without_reading_plugin_configuration(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    (project_root / "raw" / "readwise").mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"readwise","name":"Readwise Export","adapter":"filesystem_drop","input_paths":["raw/readwise"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["readwise"], trusted=True, actor_id="test", reason="fixture"
    )
    (project_root / "raw" / "readwise" / "weekly.md").write_text("Imported highlight", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-plugin.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        ObsidianSyncService(repo, root).sync(project_id="project-a")
        source = repo.list_sources("project-a")[0]

        assert source["source_type"] == "obsidian_plugin:readwise"
        assert source["metadata"]["obsidian_plugin"] == "readwise"
        assert source["metadata"]["plugin_name"] == "Readwise Export"
        assert source["origin"].endswith("raw/readwise/weekly.md")
        status = ObsidianPluginManifest.load(project_root).public_status([source], project_root=project_root)
        assert status["plugins"][0]["status"] == "captured"
        assert status["plugins"][0]["captured_sources"] == 1
        assert status["plugins"][0]["path_status"] == "ready"
    finally:
        repo.close()


def test_plugin_status_verifies_declared_destination_from_readonly_settings(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export_root = project_root / "00_Inbox" / "web-clipper"
    export_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
        encoding="utf-8",
    )
    settings_path = root / ".obsidian" / "plugins" / "obsidian-clipper" / "data.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"advancedStorageFolder":"projects/project-a/00_Inbox/web-clipper"}', encoding="utf-8")
    manifest = ObsidianPluginManifest.load(project_root)

    configured = manifest.public_status(project_root=project_root, vault_root=root)["plugins"][0]

    assert configured["runtime_configuration"] == {
        "state": "configured",
        "detail_code": "destination_matches_bridge",
    }
    settings_path.write_text('{"advancedStorageFolder":"unmanaged/inbox"}', encoding="utf-8")
    mismatch = manifest.public_status(project_root=project_root, vault_root=root)["plugins"][0]
    assert mismatch["runtime_configuration"]["state"] == "mismatch"


def test_plugin_status_rejects_symlinked_runtime_settings_without_reading_or_writing_source(tmp_path, monkeypatch):
    """Route readiness is metadata-only, even when a settings path is malicious."""
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export_root = project_root / "00_Inbox" / "web-clipper"
    export_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
        encoding="utf-8",
    )
    source = project_root / "01_Sources" / "private.md"
    source.parent.mkdir(parents=True)
    source.write_text("PRIVATE SOURCE BODY", encoding="utf-8")
    settings_path = root / ".obsidian" / "plugins" / "obsidian-clipper" / "data.json"
    settings_path.parent.mkdir(parents=True)

    manifest = ObsidianPluginManifest.load(project_root)
    original_read_bytes = Path.read_bytes
    original_write_text = Path.write_text
    original_resolve = Path.resolve
    original_is_symlink = Path.is_symlink
    resolved_source = original_resolve(source)

    def redirected_resolve(path, *args, **kwargs):
        if path == settings_path:
            return resolved_source
        return original_resolve(path, *args, **kwargs)

    def simulated_symlink(path):
        return path == settings_path or original_is_symlink(path)

    def guarded_read_bytes(path, *args, **kwargs):
        if original_resolve(path) == resolved_source:
            raise AssertionError("plugin status must not read a source body")
        return original_read_bytes(path, *args, **kwargs)

    def guarded_write_text(path, *args, **kwargs):
        if original_resolve(path) == resolved_source:
            raise AssertionError("plugin status must not write a source file")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "resolve", redirected_resolve)
    monkeypatch.setattr(Path, "is_symlink", simulated_symlink)

    route = manifest.public_status(project_root=project_root, vault_root=root)["plugins"][0]

    assert route["runtime_configuration"] == {
        "state": "unavailable",
        "detail_code": "plugin_settings_unsafe_path",
    }


def test_plugin_status_verifies_copilot_conversation_archive_is_separate_from_reviewed_outputs(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "copilot"
    output_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"copilot","name":"Obsidian Copilot reviewed outputs","adapter":"filesystem_output","input_paths":["04_Outputs/copilot"]}]}',
        encoding="utf-8",
    )
    settings_path = root / ".obsidian" / "plugins" / "copilot" / "data.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        '{"defaultSaveFolder":"projects/project-a/copilot/copilot-conversations"}',
        encoding="utf-8",
    )
    manifest = ObsidianPluginManifest.load(project_root)
    manifest.set_trust(
        project_root,
        plugin_ids=["copilot"],
        trusted=True,
        actor_id="test",
        reason="fixture",
    )

    configured = ObsidianPluginManifest.load(project_root).public_status(
        project_root=project_root,
        vault_root=root,
    )["plugins"][0]

    assert configured["runtime_configuration"] == {
        "state": "configured",
        "detail_code": "conversation_archive_separated_from_reviewed_output",
    }
    assert configured["status"] == "awaiting_output"

    rejected = ObsidianPluginManifest.load(project_root).public_status(
        outputs=[
            {
                "status": "rejected",
                "metadata": {"obsidian_plugin": "copilot", "obsidian_adapter": "filesystem_output"},
            }
        ],
        project_root=project_root,
        vault_root=root,
    )["plugins"][0]
    assert rejected["registered_outputs"] == 0
    assert rejected["status"] == "awaiting_output"
    assert rejected["capture_state"] == "ready_for_first_output"

    settings_path.write_text('{"defaultSaveFolder":"projects/project-a/04_Outputs/copilot"}', encoding="utf-8")
    mismatch = manifest.public_status(project_root=project_root, vault_root=root)["plugins"][0]

    assert mismatch["runtime_configuration"] == {
        "state": "mismatch",
        "detail_code": "conversation_archive_overlaps_reviewed_output",
    }


def test_zotero_bridge_captures_citation_provenance_from_an_exported_note(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export = project_root / "01_Sources" / "zotero" / "smith2025.md"
    export.parent.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-zotero-desktop-connector","name":"Zotero Integration","adapter":"filesystem_drop","input_paths":["01_Sources/zotero"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root,
        plugin_ids=["obsidian-zotero-desktop-connector"],
        trusted=True,
        actor_id="test",
        reason="fixture",
    )
    settings_path = root / ".obsidian" / "plugins" / "obsidian-zotero-desktop-connector" / "data.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"noteImportFolder":"projects/project-a/01_Sources/zotero"}', encoding="utf-8")
    export.write_text(
        "---\ncitekey: smith2025\nDOI: 10.1234/example\nurl: https://doi.org/10.1234/example\ndate: 2025-01-15\nitemKey: ABCD1234\n---\n# Paper note\n",
        encoding="utf-8",
    )
    repo = WikiRepository(db_path=str(tmp_path / "zotero-sync.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        source = repo.list_sources("project-a")[0]
        status = ObsidianPluginManifest.load(project_root).public_status([source], project_root=project_root, vault_root=root)["plugins"][0]

        assert report["created"] == 1
        metadata = source["metadata"]
        assert metadata["sync"] == "obsidian"
        assert metadata["obsidian_plugin"] == "obsidian-zotero-desktop-connector"
        assert metadata["plugin_name"] == "Zotero Integration"
        assert metadata["obsidian_adapter"] == "filesystem_drop"
        assert metadata["zotero_citation_key"] == "smith2025"
        assert metadata["zotero_doi"] == "10.1234/example"
        assert metadata["zotero_url"] == "https://doi.org/10.1234/example"
        assert metadata["zotero_source_date"] == "2025-01-15"
        assert metadata["zotero_item_key"] == "ABCD1234"
        assert metadata["extension"] == ".md"
        assert metadata["extraction_status"] == "complete"
        references = repo.list_reference_links("project-a", source_id=source["id"])
        assert {
            (item["target_type"], item["anchor"], item["relation"])
            for item in references
        } == {
            ("url", "https://doi.org/10.1234/example", "declares_url"),
            ("doi", "10.1234/example", "declares_doi"),
            ("citekey", "smith2025", "declares_citekey"),
        }
        repeat = ObsidianSyncService(repo, root).sync(project_id="project-a")
        assert repeat["duplicates"] == 1
        assert len(repo.list_reference_links("project-a", source_id=source["id"])) == 3
        assert status["runtime_configuration"] == {"state": "configured", "detail_code": "destination_matches_bridge"}
        assert status["status"] == "captured"
    finally:
        repo.close()


def test_project_context_plugin_is_captured_without_becoming_an_a_layer_route(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    drawing = project_root / "03_Projects" / "active" / "maps" / "architecture.excalidraw.md"
    drawing.parent.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-excalidraw-plugin","name":"Excalidraw","adapter":"filesystem_context","input_paths":["03_Projects/active/maps"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root,
        plugin_ids=["obsidian-excalidraw-plugin"],
        trusted=True,
        actor_id="test",
        reason="fixture",
    )
    drawing.write_text("# Project map\n\nContextual architecture map.", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "excalidraw-context.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        source = repo.list_sources("project-a")[0]
        status = ObsidianPluginManifest.load(project_root).public_status([source], project_root=project_root, vault_root=root)["plugins"][0]

        assert report["created"] == 1
        assert source["source_type"] == "obsidian_plugin:obsidian-excalidraw-plugin"
        assert source["metadata"]["obsidian_adapter"] == "filesystem_context"
        assert source["metadata"]["obsidian_workspace_role"] == "project_context"
        assert status["status"] == "captured"
    finally:
        repo.close()


@pytest.mark.parametrize("input_path", ["03_Projects", "01_Sources/project-notes", "wiki/maps"])
def test_project_context_plugin_rejects_non_dedicated_project_paths(input_path):
    with pytest.raises(ValueError):
        ObsidianPluginManifest.from_payload(
            {
                "plugins": [
                    {
                        "id": "obsidian-excalidraw-plugin",
                        "name": "Excalidraw",
                        "adapter": "filesystem_context",
                        "input_paths": [input_path],
                    }
                ]
            }
        )


def test_adding_a_trusted_route_preserves_unchanged_disk_trust_entries(tmp_path):
    project_root = tmp_path / "vault" / "projects" / "project-a"
    initial = ObsidianPluginManifest.from_payload(
        {
            "plugins": [
                {"id": "clipper", "adapter": "filesystem_drop", "input_paths": ["00_Inbox/web-clipper"]},
                {"id": "docxer", "adapter": "filesystem_drop", "input_paths": ["01_Sources/docxer"]},
            ]
        }
    )
    initial.write_to(project_root)
    initial.set_trust(project_root, plugin_ids=["clipper", "docxer"], trusted=True, actor_id="test", reason="fixture")

    replacement = ObsidianPluginManifest.from_payload(
        {
            "plugins": [
                *initial.to_payload()["plugins"],
                {"id": "zotero", "adapter": "filesystem_drop", "input_paths": ["01_Sources/zotero"]},
            ]
        }
    )
    replacement.write_to(project_root)
    replacement.set_trust(project_root, plugin_ids=["zotero"], trusted=True, actor_id="test", reason="fixture")

    loaded = ObsidianPluginManifest.load(project_root)
    assert {plugin.plugin_id for plugin in loaded.trusted_plugins()} == {"clipper", "docxer", "zotero"}


def test_plugin_status_marks_interactive_importers_without_claiming_a_saved_destination(tmp_path):
    project_root = tmp_path / "vault" / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"docxer","name":"Docxer","adapter":"filesystem_drop","input_paths":["01_Sources/docxer"]}]}',
        encoding="utf-8",
    )

    status = ObsidianPluginManifest.load(project_root).public_status(project_root=project_root, vault_root=tmp_path / "vault")

    assert status["plugins"][0]["runtime_configuration"] == {
        "state": "interactive_destination",
        "detail_code": "plugin_selects_destination_per_import",
    }


def test_claudian_agent_workspace_does_not_treat_media_folder_as_an_automatic_chat_export(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    (project_root / "04_Outputs" / "claudian").mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"realclaudian","name":"Claudian output","adapter":"filesystem_output","input_paths":["04_Outputs/claudian"]}]}',
        encoding="utf-8",
    )
    settings_path = root / ".claudian" / "claudian-settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        '{"mediaFolder":"projects/project-a/04_Outputs/claudian"}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root,
        plugin_ids=["realclaudian"],
        trusted=True,
        actor_id="test",
        reason="fixture",
    )

    route = ObsidianPluginManifest.load(project_root).public_status(
        project_root=project_root,
        vault_root=root,
    )["plugins"][0]

    assert route["runtime_configuration"] == {
        "state": "agent_workspace",
        "detail_code": "agent_writes_declared_output_path",
    }
    assert route["status"] == "awaiting_output"
    assert route["capture_state"] == "ready_for_first_output"


def test_plugin_status_distinguishes_an_empty_route_from_an_unprocessed_export(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export_root = project_root / "00_Inbox" / "web-clipper"
    export_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
        encoding="utf-8",
    )
    manifest = ObsidianPluginManifest.load(project_root)
    manifest.set_trust(project_root, plugin_ids=["obsidian-clipper"], trusted=True, actor_id="test", reason="fixture")

    empty = ObsidianPluginManifest.load(project_root).public_status(project_root=project_root, vault_root=root)["plugins"][0]

    assert empty["status"] == "awaiting_export"
    assert empty["capture_state"] == "ready_for_first_export"
    assert empty["export_observation"] == {"state": "empty", "file_count": 0, "latest_modified_at": ""}

    (export_root / ".sync.lock").write_text("ignored", encoding="utf-8")
    (export_root / "article.md").write_text("An external export awaiting source sync", encoding="utf-8")
    detected = ObsidianPluginManifest.load(project_root).public_status(project_root=project_root, vault_root=root)["plugins"][0]

    assert detected["status"] == "awaiting_export"
    assert detected["capture_state"] == "files_detected_pending_capture"
    assert detected["export_observation"]["state"] == "files_detected"
    assert detected["export_observation"]["file_count"] == 1
    assert detected["export_observation"]["latest_modified_at"]


def test_bsc_local_clipper_probe_never_counts_as_an_export_or_source(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export_root = project_root / "00_Inbox" / "web-clipper"
    export_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"obsidian-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
        encoding="utf-8",
    )
    manifest = ObsidianPluginManifest.load(project_root)
    manifest.set_trust(project_root, plugin_ids=["obsidian-clipper"], trusted=True, actor_id="test", reason="fixture")
    (export_root / "bsc.local.md").write_text(
        "# BSC Obsidian bridge health check\nThis operational test evidence must not be used for research.",
        encoding="utf-8",
    )
    repo = WikiRepository(db_path=str(tmp_path / "bridge-healthcheck.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        legacy = repo.create_source(
            SourceRecord(
                project_id="project-a",
                source_type="obsidian_plugin:obsidian-clipper",
                origin="projects/project-a/00_Inbox/web-clipper/bsc.local.md",
                vault_path="projects/project-a/00_Inbox/web-clipper/bsc.local.md",
                content_hash="0" * 64,
                raw_content="Legacy bridge health-check audit record",
                status=SourceStatus.REJECTED,
                metadata={
                    "sync": "obsidian",
                    "obsidian_plugin": "obsidian-clipper",
                    "obsidian_adapter": "filesystem_drop",
                },
            )
        )
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        status = ObsidianPluginManifest.load(project_root).public_status(
            repo.list_sources("project-a"), project_root=project_root, vault_root=root
        )["plugins"][0]

        assert report["scanned"] == 0
        assert report["deleted"] == 1
        assert repo.get_source("project-a", legacy["id"])["metadata"]["source_present"] is False
        assert status["status"] == "awaiting_export"
        assert status["capture_state"] == "ready_for_first_export"
        assert status["captured_sources"] == 0
        assert status["export_observation"] == {"state": "empty", "file_count": 0, "latest_modified_at": ""}
    finally:
        repo.close()


def test_obsidian_sync_accepts_the_documented_obsidian_inbox_and_source_layout(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    (project_root / "00_Inbox" / "web-clipper").mkdir(parents=True)
    (project_root / "01_Sources" / "docxer").mkdir(parents=True)
    (project_root / "04_Outputs").mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":['
        '{"id":"web-clipper","name":"Obsidian Web Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]},'
        '{"id":"docxer","name":"Docxer","adapter":"filesystem_drop","input_paths":["01_Sources/docxer"]}'
        "]}",
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["web-clipper", "docxer"], trusted=True, actor_id="test", reason="fixture"
    )
    (project_root / "00_Inbox" / "web-clipper" / "article.md").write_text("Captured article", encoding="utf-8")
    (project_root / "01_Sources" / "docxer" / "brief.md").write_text("Converted brief", encoding="utf-8")
    (project_root / "04_Outputs" / "report.md").write_text("Do not re-ingest output", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-standard-layout.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        sources = {source["origin"]: source for source in repo.list_sources("project-a")}

        assert report["created"] == 2
        assert set(sources) == {
            "projects/project-a/00_Inbox/web-clipper/article.md",
            "projects/project-a/01_Sources/docxer/brief.md",
        }
        assert sources["projects/project-a/00_Inbox/web-clipper/article.md"]["metadata"]["obsidian_plugin"] == "web-clipper"
        assert sources["projects/project-a/01_Sources/docxer/brief.md"]["metadata"]["obsidian_plugin"] == "docxer"
        assert sources["projects/project-a/00_Inbox/web-clipper/article.md"]["metadata"]["obsidian_adapter"] == "filesystem_drop"
    finally:
        repo.close()


def test_obsidian_sync_lists_untrusted_plugin_exports_but_never_reads_them(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export = project_root / "00_Inbox" / "web-clipper" / "article.md"
    export.parent.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"web-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
        encoding="utf-8",
    )
    export.write_text("An exported source that must wait for approval", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "untrusted-plugin.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        blocked = ObsidianSyncService(repo, root).sync(project_id="project-a")
        manifest = ObsidianPluginManifest.load(project_root)
        assert blocked["blocked"] == 1
        assert repo.list_sources("project-a") == []
        assert manifest.public_status(project_root=project_root)["plugins"][0]["trust_state"] == "untrusted"

        manifest.set_trust(project_root, plugin_ids=["web-clipper"], trusted=True, actor_id="test", reason="fixture")
        approved = ObsidianSyncService(repo, root).sync(project_id="project-a")
        source = repo.list_sources("project-a")[0]
        assert approved["created"] == 1
        assert source["source_type"] == "obsidian_plugin:web-clipper"
    finally:
        repo.close()


def test_obsidian_sync_reconciles_a_trusted_bridge_for_an_existing_immutable_duplicate(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    export = project_root / "00_Inbox" / "web-clipper" / "article.md"
    export.parent.mkdir(parents=True)
    export.write_text("Existing immutable capture", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "plugin-provenance.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        first = ObsidianSyncService(repo, root).sync(project_id="project-a")
        source = repo.list_sources("project-a")[0]
        assert first["created"] == 1
        assert "obsidian_plugin" not in source["metadata"]

        (project_root / "bsc-plugins.json").write_text(
            '{"plugins":[{"id":"web-clipper","name":"Obsidian Clipper","adapter":"filesystem_drop","input_paths":["00_Inbox/web-clipper"]}]}',
            encoding="utf-8",
        )
        ObsidianPluginManifest.load(project_root).set_trust(
            project_root, plugin_ids=["web-clipper"], trusted=True, actor_id="test", reason="fixture"
        )
        second = ObsidianSyncService(repo, root).sync(project_id="project-a")
        reconciled = repo.list_sources("project-a")[0]
        assert second["created"] == 0
        assert second["duplicates"] == 1
        assert reconciled["content_hash"] == source["content_hash"]
        assert reconciled["metadata"]["obsidian_plugin"] == "web-clipper"
        assert reconciled["metadata"]["obsidian_adapter"] == "filesystem_drop"
    finally:
        repo.close()


def test_obsidian_sync_imports_semantic_work_lanes_but_keeps_archive_outside_the_loop(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    project_root = root / "projects" / "project-a"
    (project_root / "02_Assets" / "curated").mkdir(parents=True)
    (project_root / "03_Projects" / "active").mkdir(parents=True)
    (project_root / "06_Skills" / "candidates").mkdir(parents=True)
    (project_root / "05_Archive" / "reviewed").mkdir(parents=True)
    (project_root / "02_Assets" / "curated" / "principle.md").write_text("Curated principle", encoding="utf-8")
    (project_root / "03_Projects" / "active" / "brief.md").write_text("Current delivery constraints", encoding="utf-8")
    (project_root / "06_Skills" / "candidates" / "review.md").write_text("Candidate review method", encoding="utf-8")
    (project_root / "05_Archive" / "reviewed" / "old.md").write_text("Do not re-ingest", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-semantic-layout.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")
        sources = {source["origin"]: source for source in repo.list_sources("project-a")}

        assert report["created"] == 3
        assert "projects/project-a/05_Archive/reviewed/old.md" not in sources
        asset = sources["projects/project-a/02_Assets/curated/principle.md"]
        context = sources["projects/project-a/03_Projects/active/brief.md"]
        skill = sources["projects/project-a/06_Skills/candidates/review.md"]
        assert (asset["source_type"], asset["metadata"]["obsidian_workspace_role"]) == ("obsidian_asset", "asset")
        assert (context["source_type"], context["metadata"]["obsidian_workspace_role"]) == ("obsidian_project_context", "project_context")
        assert (skill["source_type"], skill["metadata"]["obsidian_workspace_role"]) == ("obsidian_skill_candidate", "skill_candidate")
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
        asset = repo.list_media_assets("project-a", source_id=source["id"])[0]
        assert asset["storage_ref"] == "research.pdf"
        assert asset["byte_hash"] == source["content_hash"]
        assert asset["mime_type"] == "application/pdf"
    finally:
        repo.close()


def test_obsidian_sync_ignores_growth_managed_roots_outside_project_mappings(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "research.md").write_text("User research", encoding="utf-8")
    for managed_root in ("distillations", "methods", "outputs", "reviews"):
        folder = root / managed_root
        folder.mkdir()
        (folder / "generated.md").write_text("Managed output", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "sync-growth-roots.db"))
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report["created"] == 1
        assert {source["origin"] for source in repo.list_sources("project-a")} == {"research.md"}
    finally:
        repo.close()


def test_obsidian_sync_explicitly_excludes_managed_knowledge_index(tmp_path):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    index = project_root / "Knowledge Index" / "00-Home.md"
    base = project_root / "Knowledge Index" / "Knowledge Operations.base"
    source = project_root / "01_Sources" / "manual.md"
    index.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    index.write_text("---\nmanaged_by_bsc: true\n---\nManaged navigation", encoding="utf-8")
    base.write_text(
        'filters:\n  and:\n    - \'file.inFolder("projects/project-a")\'\nviews:\n  - type: table\n    name: Sources\n',
        encoding="utf-8",
    )
    source.write_text("Real source", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "managed-index.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianSyncService(repo, root).sync(project_id="project-a")

        assert report == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0, "blocked": 0}
        assert [item["origin"] for item in repo.list_sources("project-a")] == ["projects/project-a/01_Sources/manual.md"]
    finally:
        repo.close()
