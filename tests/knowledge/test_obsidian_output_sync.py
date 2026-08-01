from pathlib import Path

from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.obsidian_output_sync import ObsidianOutputSyncService
from app.knowledge.wiki_contracts import KnowledgeRun
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


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
        retry_run = KnowledgeRun(id="sync-2", project_id="project-a", run_type="source_sync", trigger="manual")
        repo.create_run(retry_run)
        second = service.sync(project_id="project-a", run_id=retry_run.id)
        outputs = repo.list_outputs("project-a")

        assert first == {"scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0}
        assert second == {"scanned": 1, "registered": 0, "duplicates": 1, "rejected": 0, "skipped": 0, "blocked": 0}
        assert original.read_text(encoding="utf-8") == "# Video brief\nOriginal plugin output"
        assert len(outputs) == 1
        output = outputs[0]
        assert output["status"] == "registered"
        assert output["run_id"] == run.id
        assert output["metadata"]["obsidian_plugin"] == "hyperframes"
        assert output["metadata"]["obsidian_adapter"] == "filesystem_output"
        materialized = project_root / Path(output["vault_path"])
        assert materialized.read_text(encoding="utf-8") == original.read_text(encoding="utf-8")
        assert any(
            edge["edge_type"] == "output_produced_by_run" and edge["from_id"] == run.id and edge["to_id"] == output["id"]
            for edge in repo.list_lineage("project-a")
        )
        assert not any(
            edge["edge_type"] == "output_produced_by_run" and edge["from_id"] == retry_run.id and edge["to_id"] == output["id"]
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


def test_claudian_output_contract_preserves_declared_provenance_and_source_lineage(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "claudian"
    output_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"realclaudian","name":"Claudian","adapter":"filesystem_output","input_paths":["04_Outputs/claudian"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["realclaudian"], trusted=True, actor_id="test", reason="fixture"
    )
    repo = GrowthRepository(db_path=str(tmp_path / "claudian-output.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="research.md",
            raw_content="Primary research evidence",
        )
    ).source
    original = output_root / "2026-07-30-decision-brief.md"
    original.write_text(
        "---\n"
        "bsc_output_contract: v1\n"
        "project_id: project-a\n"
        "title: Decision brief\n"
        "output_kind: decision_brief\n"
        "goal: Decide the next research step\n"
        "audience: Project owner\n"
        "channel: internal\n"
        f"source_refs: {source['id']}\n"
        "page_refs: \n"
        "---\n\n"
        "# Decision brief\n\nUse the cited evidence for the next research step.\n",
        encoding="utf-8",
    )
    try:
        assert ObsidianOutputSyncService._output_contract(original.read_bytes(), "project-a")["title"] == "Decision brief"
        report = ObsidianOutputSyncService(repo, vault).sync(project_id="project-a")
        output = repo.list_outputs("project-a")[0]

        assert report == {"scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0}
        assert output["title"] == "Decision brief"
        assert output["kind"] == "decision_brief"
        assert output["source_refs"] == [source["id"]]
        assert output["metadata"]["goal"] == "Decide the next research step"
        assert output["metadata"]["audience"] == "Project owner"
        assert output["metadata"]["channel"] == "internal"
        assert output["metadata"]["bsc_output_contract"] == "v1"
        assert any(
            edge["edge_type"] == "output_used_source" and edge["from_id"] == source["id"] and edge["to_id"] == output["id"]
            for edge in repo.list_lineage("project-a")
        )
    finally:
        repo.close()


def test_claudian_output_contract_rejects_a_declared_cross_project_output(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "claudian"
    output_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"realclaudian","name":"Claudian","adapter":"filesystem_output","input_paths":["04_Outputs/claudian"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["realclaudian"], trusted=True, actor_id="test", reason="fixture"
    )
    (output_root / "cross-project.md").write_text(
        "---\nbsc_output_contract: v1\nproject_id: project-b\n---\n# Must not cross projects\n",
        encoding="utf-8",
    )
    repo = GrowthRepository(db_path=str(tmp_path / "claudian-cross-project.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianOutputSyncService(repo, vault).sync(project_id="project-a")

        assert report == {"scanned": 1, "registered": 0, "duplicates": 0, "rejected": 1, "skipped": 0, "blocked": 0}
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_copilot_transcript_without_bsc_contract_is_rejected(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "copilot"
    output_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"copilot","name":"Copilot","adapter":"filesystem_output","input_paths":["04_Outputs/copilot"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["copilot"], trusted=True, actor_id="test", reason="fixture"
    )
    (output_root / "plan.md").write_text(
        "---\n"
        "epoch: 1785558682253\n"
        'modelKey: "deepseek-v4-flash|deepseek"\n'
        'topic: "PBOS v1 Execution Plan"\n'
        "---\n\n"
        "**user**: Compile an evidence-aware plan.\n"
        "[Context: Notes: projects/project-a/03_Projects/active/brief.md, "
        "projects/project-a/wiki/overview.md, ../outside.md]\n\n"
        "**ai**: Keep all unverified claims pending review.\n",
        encoding="utf-8",
    )
    repo = GrowthRepository(db_path=str(tmp_path / "copilot-output.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        report = ObsidianOutputSyncService(repo, vault).sync(project_id="project-a")

        assert report == {"scanned": 1, "registered": 0, "duplicates": 0, "rejected": 1, "skipped": 0, "blocked": 0}
        assert repo.list_outputs("project-a") == []
        assert (output_root / "plan.md").is_file()
    finally:
        repo.close()


def test_copilot_reviewed_output_with_contract_registers_once_and_is_idempotent(tmp_path):
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    output_root = project_root / "04_Outputs" / "copilot"
    output_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"copilot","name":"Copilot","adapter":"filesystem_output","input_paths":["04_Outputs/copilot"]}]}',
        encoding="utf-8",
    )
    ObsidianPluginManifest.load(project_root).set_trust(
        project_root, plugin_ids=["copilot"], trusted=True, actor_id="test", reason="fixture"
    )
    content = (
        "---\n"
        "bsc_output_contract: v1\n"
        "project_id: project-a\n"
        "title: PBOS v1 Execution Plan\n"
        "output_kind: execution_plan\n"
        "goal: Turn the approved brief into an executable plan\n"
        "audience: Project owner\n"
        "channel: internal\n"
        'modelKey: "deepseek-v4-flash|deepseek"\n'
        "---\n\n"
        "# PBOS v1 Execution Plan\n\nA reviewed Copilot delivery.\n"
    ).encode("utf-8")
    original = output_root / "plan.md"
    original.write_bytes(content)
    repo = GrowthRepository(db_path=str(tmp_path / "copilot-legacy.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        service = ObsidianOutputSyncService(repo, vault)
        first = service.sync(project_id="project-a")
        retry = service.sync(project_id="project-a")
        output = repo.list_outputs("project-a")[0]

        assert first == {"scanned": 1, "registered": 1, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0}
        assert retry == {"scanned": 1, "registered": 0, "duplicates": 1, "rejected": 0, "skipped": 0, "blocked": 0}
        assert output["title"] == "PBOS v1 Execution Plan"
        assert output["kind"] == "execution_plan"
        assert output["metadata"]["bsc_output_contract"] == "v1"
        assert output["metadata"]["provider"] == "deepseek"
        assert output["metadata"]["model"] == "deepseek-v4-flash"
        assert output["metadata"]["prompt_revision"] == "vault_output_contract_v1"
    finally:
        repo.close()
