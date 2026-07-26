from pathlib import Path

from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.obsidian_output_sync import ObsidianOutputSyncService
from app.knowledge.wiki_contracts import KnowledgeRun


def test_declared_plugin_output_is_copied_to_pending_d_layer_without_mutating_the_original(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "hyperframes"
    output_root.mkdir(parents=True)
    original = output_root / "brief.md"
    original.write_text("# Video brief\nOriginal plugin output", encoding="utf-8")
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"hyperframes","name":"HyperFrames","adapter":"filesystem_output","input_paths":["04_Outputs/hyperframes"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["hyperframes"], trusted=True, actor_id="test", reason="fixture"
    )
    repo = GrowthRepository(db_path=str(tmp_path / "output-sync.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = KnowledgeRun(id="sync-1", project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    try:
        service = ObsidianOutputSyncService(repo, vault)
        first = service.sync(project_id="project-a", run_id=run.id)
        second = service.sync(project_id="project-a", run_id=run.id)
        outputs = repo.list_outputs("project-a")

        assert first == {"scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0}
        assert second == {"scanned": 1, "registered": 0, "duplicates": 1, "rejected": 0, "skipped": 0, "blocked": 0}
        assert original.read_text(encoding="utf-8") == "# Video brief\nOriginal plugin output"
        assert len(outputs) == 1
        output = outputs[0]
        assert output["status"] == "registered"
        assert output["metadata"]["obsidian_plugin"] == "hyperframes"
        assert output["metadata"]["obsidian_adapter"] == "filesystem_output"
        materialized = project_root / Path(output["vault_path"])
        assert materialized.read_text(encoding="utf-8") == original.read_text(encoding="utf-8")
        assert any(
            edge["edge_type"] == "output_produced_by_run" and edge["from_id"] == run.id and edge["to_id"] == output["id"]
            for edge in repo.list_lineage("project-a")
        )
    finally:
        repo.close()


def test_output_sync_ignores_undeclared_and_temporary_files(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    declared = project_root / "04_Outputs" / "articles"
    declared.mkdir(parents=True)
    (declared / "article.md").write_text("Approved draft", encoding="utf-8")
    (declared / "article.md.swp").write_text("temporary", encoding="utf-8")
    unlisted = project_root / "04_Outputs" / "other"
    unlisted.mkdir(parents=True)
    (unlisted / "secret.md").write_text("must not be adopted", encoding="utf-8")
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"formatter","name":"Formatter","adapter":"filesystem_output","input_paths":["04_Outputs/articles"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["formatter"], trusted=True, actor_id="test", reason="fixture"
    )
    repo = GrowthRepository(db_path=str(tmp_path / "output-sync-unlisted.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianOutputSyncService(repo, vault).sync(project_id="project-a")

        assert report == {"scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 1, "blocked": 0}
        assert len(repo.list_outputs("project-a")) == 1
        assert repo.list_outputs("project-a")[0]["metadata"]["original_path"] == "04_Outputs/articles/article.md"
    finally:
        repo.close()
