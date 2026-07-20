import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_product_entrypoints_delegate_to_runtime_compatibility():
    entrypoints = {
        "app/cli.py": "run_legacy_bsc_runtime_sync",
        "app/tasks/bsc_tasks.py": "run_legacy_bsc_runtime_sync",
        "app/api/stream_api.py": "run_legacy_bsc_runtime",
        "app/api/chat_api.py": "run_legacy_bsc_runtime",
        "app/mcp/_engine_runner.py": "run_legacy_bsc_runtime",
        "app/agents/studio_orchestrator.py": "run_legacy_bsc_runtime_sync",
        "app/orchestrator/agents/business_architect.py": "run_legacy_bsc_runtime",
        "app/core/dialog_engine.py": "run_legacy_bsc_runtime_sync",
        "app/core/compaction_pipeline.py": "run_legacy_bsc_runtime_sync",
        "app/core/interactive_pipeline.py": "run_legacy_bsc_runtime_sync",
        "app/core/pipeline_enhanced.py": "run_legacy_bsc_runtime_sync",
    }
    direct_compiler_imports = (
        "from app.core.bsc_pipeline import compile_to_business_system",
        "from app.core.async_pipeline import compile_to_business_system_async",
        "from app.core.async_pipeline import run_async_bsc_pipeline",
        "from app.core.bsc_pipeline import run_bsc_pipeline",
    )

    for relative_path, runtime_call in entrypoints.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert runtime_call in source
        assert not any(import_line in source for import_line in direct_compiler_imports)


def test_sync_compatibility_bridge_keeps_runtime_ownership_inside_event_loop(monkeypatch):
    from app.capabilities import runner

    calls = {}

    async def fake_runtime(**kwargs):
        calls.update(kwargs)
        return {"business_system": {}, "pipeline": {}, "workspace": {}, "summary": "ok"}

    monkeypatch.setattr(runner, "run_legacy_bsc_runtime", fake_runtime)

    async def invoke_from_running_loop():
        return runner.run_legacy_bsc_runtime_sync(
            input_text="runtime compatibility input",
            template_id="template-a",
            async_mode=False,
        )

    result = asyncio.run(invoke_from_running_loop())

    assert result["summary"] == "ok"
    assert calls == {
        "input_text": "runtime compatibility input",
        "template_id": "template-a",
        "async_mode": False,
    }


def test_mcp_compile_uses_the_runtime_compatibility_capability(monkeypatch):
    from app.mcp import _engine_runner

    calls = {}

    async def fake_runtime(**kwargs):
        calls.update(kwargs)
        return {"business_system": {}, "pipeline": {}, "workspace": {}, "summary": "ok"}

    monkeypatch.setattr(
        "app.capabilities.runner.run_legacy_bsc_runtime",
        fake_runtime,
    )

    result = asyncio.run(_engine_runner._run_compile({
        "description": "MCP runtime input",
        "template_id": "template-mcp",
        "project_id": "project-mcp",
    }))

    assert result["summary"] == "ok"
    assert calls == {
        "input_text": "MCP runtime input",
        "template_id": "template-mcp",
        "project_id": "project-mcp",
        "async_mode": True,
    }


def test_chat_compile_uses_runtime_and_preserves_follow_up_projection(monkeypatch):
    from app.api import chat_api

    calls = {}

    async def fake_runtime(**kwargs):
        calls.update(kwargs)
        return {
            "business_system": {
                "workflow": [{"step": 1, "name": "Review"}],
                "roles": [{"role": "Reviewer"}],
                "sla": [{"metric": "time", "target": "15m"}],
                "kpi": [{"name": "accuracy", "target": "98%"}],
                "risk": {"process_risks": [{"risk": "Delay"}]},
                "strategy": {"growth_opportunities": []},
                "optimization": {"recommendations": []},
            },
            "pipeline": {"total_ms": 12},
            "workspace": {},
            "summary": "runtime summary",
        }

    monkeypatch.setattr("app.capabilities.runner.run_legacy_bsc_runtime", fake_runtime)

    response = asyncio.run(chat_api._handle_compile("chat runtime input"))

    assert calls == {"input_text": "chat runtime input", "async_mode": False}
    assert response["data"]["sop"]["workflow"][0]["name"] == "Review"
    assert response["data"]["risk"]["process_risks"][0]["risk"] == "Delay"
    assert response["data"]["total_ms"] == 12
