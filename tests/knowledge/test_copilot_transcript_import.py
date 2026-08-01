from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge.copilot_transcript_import import (
    CopilotTranscriptImportError,
    CopilotTranscriptImportService,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.output_registry import OutputRegistry


def _transcript(*, response: str, assistant_label: str = "ai") -> str:
    return (
        "---\n"
        'epoch: 1785558682253\n'
        'modelKey: "deepseek-v4-flash|deepseek"\n'
        'topic: "PBOS v1 Execution Plan"\n'
        "---\n\n"
        "**user**: Create a bounded PBOS plan.\n"
        "[Context: Notes: projects/project-a/03_Projects/active/brief.md]\n"
        "[Timestamp: 2026/08/01 13:09:48]\n\n"
        f"**{assistant_label}**: {response}\n"
        "[Timestamp: 2026/08/01 13:10:12]\n"
    )


def _configured_project(tmp_path: Path) -> tuple[GrowthRepository, Path, Path]:
    vault = tmp_path / "vault"
    project_root = vault / "projects" / "project-a"
    archive = project_root / "copilot" / "copilot-conversations"
    archive.mkdir(parents=True)
    (project_root / "04_Outputs" / "copilot").mkdir(parents=True)
    settings_path = vault / ".obsidian" / "plugins" / "copilot" / "data.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        '{"defaultSaveFolder":"projects/project-a/copilot/copilot-conversations"}',
        encoding="utf-8",
    )
    (project_root / "bsc-plugins.json").write_text(
        '{"plugins":[{"id":"copilot","name":"Copilot","adapter":"filesystem_output","input_paths":["04_Outputs/copilot"]}]}',
        encoding="utf-8",
    )
    manifest = ObsidianPluginManifest.load(project_root)
    manifest.set_trust(
        project_root,
        plugin_ids=["copilot"],
        trusted=True,
        actor_id="test-owner",
        reason="fixture",
    )
    repo = GrowthRepository(db_path=str(tmp_path / "growth.db"))
    repo.configure_vault("project-a", "projects/project-a", "test-owner")
    return repo, vault, archive


def test_import_latest_completed_copilot_transcript_creates_an_auditable_review_draft(tmp_path: Path):
    repo, vault, archive = _configured_project(tmp_path)
    original = archive / "PBOS_v1_Execution_Plan.md"
    original.write_text(
        _transcript(
            response=(
                "**Facts**: The active brief defines a Mission and evidence boundary.\n\n"
                "**Plan**: Freeze the acceptance boundary before implementation.\n\n"
                "**Gap**: No owner outcome has been observed."
            )
        ),
        encoding="utf-8",
    )
    original_bytes = original.read_bytes()
    service = CopilotTranscriptImportService(repo, vault)
    try:
        first = service.import_latest(project_id="project-a", actor_id="test-owner")
        second = service.import_latest(project_id="project-a", actor_id="test-owner")

        output = first["output"]
        assert first["idempotent"] is False
        assert second["idempotent"] is True
        assert second["output"]["id"] == output["id"]
        assert output["status"] == "registered"
        assert output["kind"] == "personal_execution_plan"
        assert output["metadata"]["origin"] == "copilot_transcript_import"
        assert output["metadata"]["obsidian_plugin"] == "copilot"
        assert output["metadata"]["obsidian_adapter"] == "transcript_import"
        assert output["metadata"]["original_path"] == "copilot/copilot-conversations/PBOS_v1_Execution_Plan.md"
        assert len(output["metadata"]["transcript_sha256"]) == 64
        assert len(output["metadata"]["response_sha256"]) == 64
        assert original.read_bytes() == original_bytes

        materialized = OutputRegistry(repo, vault).read_content("project-a", output["id"])
        assert "Imported Copilot review draft" in materialized["content"]
        assert "Freeze the acceptance boundary before implementation." in materialized["content"]
        assert "No owner outcome has been observed." in materialized["content"]
        assert "Create a bounded PBOS plan." not in materialized["content"]
        assert len(repo.list_outputs("project-a")) == 1
    finally:
        repo.close()


def test_import_current_copilot_assistant_autosave_from_the_separate_archive(tmp_path: Path):
    repo, vault, archive = _configured_project(tmp_path)
    original = archive / "PBOS_One-Click_Governed_Delivery.md"
    original.write_text(
        _transcript(
            assistant_label="assistant",
            response=(
                "**Facts**: The active brief defines the Mission boundary.\n\n"
                "**Plan**: Keep the output pending review until an owner outcome exists."
            ),
        ),
        encoding="utf-8",
    )
    original_bytes = original.read_bytes()
    service = CopilotTranscriptImportService(repo, vault)
    try:
        result = service.import_latest(project_id="project-a", actor_id="test-owner")

        output = result["output"]
        assert result["idempotent"] is False
        assert output["status"] == "registered"
        assert output["metadata"]["origin"] == "copilot_transcript_import"
        assert output["metadata"]["original_path"] == "copilot/copilot-conversations/PBOS_One-Click_Governed_Delivery.md"
        assert original.read_bytes() == original_bytes

        materialized = OutputRegistry(repo, vault).read_content("project-a", output["id"])
        assert "Keep the output pending review until an owner outcome exists." in materialized["content"]
    finally:
        repo.close()


def test_import_rejects_truncated_or_untrusted_copilot_archives(tmp_path: Path):
    repo, vault, archive = _configured_project(tmp_path)
    (archive / "truncated.md").write_text(
        _transcript(response="_[The response was truncated before any content could be generated.]_"),
        encoding="utf-8",
    )
    service = CopilotTranscriptImportService(repo, vault)
    try:
        with pytest.raises(CopilotTranscriptImportError, match="no_completed_copilot_response"):
            service.import_latest(project_id="project-a", actor_id="test-owner")

        project_root = vault / "projects" / "project-a"
        manifest = ObsidianPluginManifest.load(project_root)
        manifest.set_trust(
            project_root,
            plugin_ids=["copilot"],
            trusted=False,
            actor_id="test-owner",
            reason="revoke fixture trust",
        )
        (archive / "completed.md").write_text(
            _transcript(response="A complete, reviewable result with evidence gaps."),
            encoding="utf-8",
        )
        with pytest.raises(CopilotTranscriptImportError, match="copilot_bridge_not_trusted"):
            service.import_latest(project_id="project-a", actor_id="test-owner")
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()
