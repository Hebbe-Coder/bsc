import asyncio

import pytest

from app.api import skill_routes
from app.core.config import settings
from app.skills.registry import SkillRegistry, is_safe_manifest_path


def _write_manifest(root, skill_id, *, entrypoint="chain:prd-analysis", body="Use evidence."):
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True)
    manifest = skill_dir / "SKILL.md"
    manifest.write_text(
        "---\n"
        f"id: {skill_id}\n"
        f"name: {skill_id}\n"
        "version: 2.1.0\n"
        f"entrypoint: {entrypoint}\n"
        "inputs:\n"
        "  - name: idea\n"
        "outputs:\n"
        "  - name: result\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return manifest


def test_registry_discovers_project_manifest_with_provenance(tmp_path):
    _write_manifest(tmp_path, "project-discovery")
    registry = SkillRegistry(
        root=tmp_path,
        executable_chain_ids={"prd-analysis"},
    )

    manifest = registry.get("project-discovery")

    assert manifest is not None
    assert manifest.source == "project"
    assert manifest.source_path == "project-discovery/SKILL.md"
    assert manifest.version == "2.1.0"
    assert manifest.executable is True
    assert manifest.inputs[0].name == "idea"
    assert registry.resolve_chain("project-discovery") == "prd-analysis"


def test_registry_keeps_unapproved_entrypoint_non_executable(tmp_path):
    _write_manifest(tmp_path, "unsafe-runner", entrypoint="python:module.callable")
    registry = SkillRegistry(
        root=tmp_path,
        executable_chain_ids={"prd-analysis"},
    )

    manifest = registry.get("unsafe-runner")

    assert manifest is not None
    assert manifest.executable is False
    with pytest.raises(PermissionError):
        registry.resolve_chain("unsafe-runner")


def test_manifest_path_must_stay_inside_configured_root(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    outside = _write_manifest(tmp_path / "outside", "escaped")

    assert is_safe_manifest_path(outside, root=root) is False


def test_project_skill_executes_through_approved_chain(tmp_path, monkeypatch):
    _write_manifest(
        tmp_path,
        "project-discovery",
        body="Inspect users and measurable outcomes.",
    )
    monkeypatch.setattr(settings, "SKILL_ROOT", str(tmp_path))

    captured = {}

    class FakeChain:
        @classmethod
        def create(cls, provider, model_name):
            captured["provider"] = provider
            captured["model_name"] = model_name
            return cls()

        async def ainvoke(self, input_data):
            captured["input_data"] = input_data
            return "executed"

    monkeypatch.setitem(skill_routes.CHAIN_REGISTRY, "prd-analysis", FakeChain)
    execution_id = "exec-project-skill"
    skill_routes.executions[execution_id] = {
        "status": "running",
        "result": None,
        "from_cache": False,
    }

    asyncio.run(
        skill_routes.execute_skill_async(
            execution_id,
            "project-discovery",
            {"idea": "Reduce onboarding delay"},
            "mock",
            "",
            use_cache=False,
        )
    )

    assert skill_routes.executions[execution_id]["status"] == "completed"
    assert skill_routes.executions[execution_id]["result"] == "executed"
    prompt = captured["input_data"]["prd_content"]
    assert "Inspect users and measurable outcomes." in prompt
    assert prompt.endswith("Reduce onboarding delay")


def test_skill_api_lists_project_and_builtin_provenance(tmp_path, monkeypatch):
    _write_manifest(tmp_path, "api-discovery")
    monkeypatch.setattr(settings, "SKILL_ROOT", str(tmp_path))

    payload = asyncio.run(skill_routes.list_skills())
    by_id = {item["id"]: item for item in payload}

    assert by_id["prd-analysis"]["source"] == "builtin"
    assert by_id["api-discovery"]["source"] == "project"
    assert by_id["api-discovery"]["version"] == "2.1.0"
    assert by_id["api-discovery"]["executable"] is True
