import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_agent_analyze_routes_through_business_runtime(monkeypatch):
    calls = {}

    async def fake_run_business_runtime(**kwargs):
        calls.update(kwargs)
        return {
            "status": "completed",
            "project_id": kwargs["project_id"],
            "execution_id": "run-test",
            "mission": {"title": "Runtime Mission", "steps": 2, "mode": kwargs["mode"]},
            "artifacts": 3,
            "gaps": 0,
            "gap_details": [],
            "board": None,
            "board_verdict": "",
            "board_consensus": "",
            "board_votes": {},
            "runtime": {
                "status": "completed",
                "execution_id": "run-test",
                "artifact_scope": "tmp/run-test",
                "iterations": 1,
                "elapsed_ms": 12.0,
                "errors": [],
            },
            "report": {"_artifact_graph": {"total_artifacts": 3}},
        }

    monkeypatch.setattr(
        "app.capabilities.runner.run_business_runtime",
        fake_run_business_runtime,
    )

    response = TestClient(app).post(
        "/agent/analyze",
        json={
            "input": "Build a support automation business",
            "mode": "template",
            "domain": "customer_service",
            "project_id": "tenant-a-project-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["project_id"] == "tenant-a-project-1"
    assert body["execution_id"] == "run-test"
    assert body["runtime"]["iterations"] == 1
    assert calls["input_text"] == "Build a support automation business"
    assert calls["domain"] == "customer_service"
    assert calls["mode"] == "template"
    assert calls["project_id"] == "tenant-a-project-1"


def test_agent_os_response_contract_is_shared_with_frontend():
    from pathlib import Path

    from app.schemas.agent_os import AgentAnalysisResponse
    from scripts.generate_agent_os_contracts import OUT, render_contracts

    schema = AgentAnalysisResponse.model_json_schema()

    assert schema["properties"]["runtime"]["$ref"].endswith("AgentRuntimeMetadata")
    assert schema["properties"]["board"]["anyOf"][0]["$ref"].endswith("AgentBoard")
    assert Path(OUT).read_text(encoding="utf-8") == render_contracts()


def test_agent_cli_delegates_to_shared_runtime(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import cli
    from app.core.config import settings

    calls = {}

    async def fake_run(**kwargs):
        calls.update(kwargs)
        return {
            "status": "completed",
            "mission": {"title": "CLI Runtime", "steps": 1, "mode": "template"},
            "artifacts": 2,
            "gaps": 0,
            "board": None,
            "board_verdict": "",
            "board_consensus": "",
            "runtime": {"artifact_scope": "tmp/default/cli/run", "errors": []},
            "report": {"business_domain": "test"},
        }

    monkeypatch.setattr("app.capabilities.runner.run_business_runtime", fake_run)
    output = tmp_path / "cli-report.json"
    cli.cmd_agent(SimpleNamespace(
        input="CLI runtime input",
        output=str(output),
        mode="template",
        domain="retail",
        board=False,
    ))

    assert calls == {
        "input_text": "CLI runtime input",
        "domain": "retail",
        "mode": "template",
        "board": False,
        "tenant_id": settings.DEFAULT_TENANT_ID,
    }
    assert output.exists()


def test_runtime_runner_uses_request_scoped_project(tmp_path, monkeypatch):
    from app.capabilities import runner
    from app.capabilities.runtime import RuntimeResult, RuntimePhase

    captured = {}

    class FakeRuntime:
        def __init__(self, *, store, registry, planner, max_iterations, executor_backend):
            self.store = store
            captured["executor_backend"] = executor_backend
            captured["max_iterations"] = max_iterations

        async def run(self, *, prd_text, domain_hint, project_id):
            captured["prd_text"] = prd_text
            captured["domain_hint"] = domain_hint
            captured["project_id"] = project_id
            artifact = self.store.create_business_model(
                label="Scoped Model",
                project_id=project_id,
                domain=domain_hint,
                objectives=["Improve support quality"],
            )
            return RuntimeResult(
                status=RuntimePhase.COMPLETED,
                artifact_graph=self.store,
                export=self.store.export(project_id=project_id),
                mission={"title": "Scoped Mission", "steps": 1, "mode": "template"},
                iterations=1,
                elapsed_ms=1.5,
                errors=[],
                gaps=[],
            )

    monkeypatch.setattr(runner, "BusinessRuntime", FakeRuntime)

    async def scenario():
        return await runner.run_business_runtime(
            input_text="Support automation PRD",
            domain="customer_service",
            mode="template",
            project_id="project-42",
            data_dir=str(tmp_path),
            executor_backend="local",
            max_iterations=2,
        )

    result = asyncio.run(scenario())

    assert result["status"] == "completed"
    assert result["project_id"] == "project-42"
    assert result["execution_id"]
    assert result["mission"] == {"title": "Scoped Mission", "steps": 1, "mode": "template"}
    assert result["artifacts"] == 1
    assert result["runtime"]["iterations"] == 1
    assert result["runtime"]["artifact_scope"].endswith(
        f"project-42\\{result['execution_id']}"
    )
    assert captured["project_id"] == "project-42"
    assert captured["executor_backend"] == "local"
    assert captured["max_iterations"] == 2


def test_runtime_runner_isolates_same_project_between_runs(tmp_path, monkeypatch):
    from app.capabilities import runner
    from app.capabilities.runtime import RuntimeResult, RuntimePhase

    class FakeRuntime:
        def __init__(self, *, store, registry, planner, max_iterations, executor_backend):
            self.store = store

        async def run(self, *, prd_text, domain_hint, project_id):
            self.store.create_business_model(
                label=f"Model {prd_text}",
                project_id=project_id,
                domain=domain_hint,
                objectives=[prd_text],
            )
            return RuntimeResult(
                status=RuntimePhase.COMPLETED,
                artifact_graph=self.store,
                export=self.store.export(project_id=project_id),
                mission={"title": "Isolated Mission", "steps": 1, "mode": "template"},
                iterations=1,
                elapsed_ms=1.0,
                errors=[],
                gaps=[],
            )

    monkeypatch.setattr(runner, "BusinessRuntime", FakeRuntime)

    async def scenario():
        first = await runner.run_business_runtime(
            input_text="Run One",
            domain="retail",
            mode="template",
            project_id="shared-project",
            data_dir=str(tmp_path),
        )
        second = await runner.run_business_runtime(
            input_text="Run Two",
            domain="retail",
            mode="template",
            project_id="shared-project",
            data_dir=str(tmp_path),
        )
        return first, second

    first, second = asyncio.run(scenario())

    assert first["artifacts"] == 1
    assert second["artifacts"] == 1
    assert first["execution_id"] != second["execution_id"]
    assert first["runtime"]["artifact_scope"] != second["runtime"]["artifact_scope"]
    assert first["runtime"]["artifact_scope"].startswith(str(tmp_path))
    assert second["runtime"]["artifact_scope"].startswith(str(tmp_path))


def test_runtime_runner_places_artifacts_under_tenant_project_and_session(tmp_path, monkeypatch):
    from app.capabilities import runner
    from app.capabilities.runtime import RuntimeResult, RuntimePhase

    class FakeRuntime:
        def __init__(self, *, store, registry, planner, max_iterations, executor_backend):
            self.store = store

        async def run(self, *, prd_text, domain_hint, project_id):
            self.store.create_business_model(label="Scoped", project_id=project_id)
            return RuntimeResult(
                status=RuntimePhase.COMPLETED,
                artifact_graph=self.store,
                export=self.store.export(project_id=project_id),
                mission={},
            )

    monkeypatch.setattr(runner, "BusinessRuntime", FakeRuntime)

    result = asyncio.run(runner.run_business_runtime(
        input_text="Scoped artifact run",
        project_id="project-a",
        execution_id="session-a",
        tenant_id="tenant-a",
        data_dir=str(tmp_path),
    ))

    assert result["runtime"]["artifact_scope"].endswith(
        "tenant-a\\project-a\\session-a"
    )


def test_business_runtime_passes_prd_text_to_capability_executor(tmp_path):
    from app.artifacts import ArtifactGraphStore
    from app.capabilities.executor import ExecutionResult
    from app.capabilities.planner import MissionGraph, MissionStep
    from app.capabilities.registry import Capability, CapabilityRegistry
    from app.capabilities.runtime import BusinessRuntime

    captured = {}

    class FakePlanner:
        async def plan(self, prd_text, domain_hint="", goals=None):
            return MissionGraph(
                mission_id="m1",
                mission="runtime_regression",
                title="Runtime Regression",
                domain=domain_hint,
                planning_mode="template",
                steps=[
                    MissionStep(
                        step_id="s1",
                        capability_name="business_understanding",
                        parallel_group=0,
                    )
                ],
                required_capabilities=["business_understanding"],
            )

    class FakeExecutor:
        async def execute(self, capability, input_text="", project_id=""):
            captured["capability"] = capability.name
            captured["input_text"] = input_text
            captured["project_id"] = project_id
            return ExecutionResult(
                capability_name=capability.name,
                status="success",
                backend="fake",
            )

    registry = CapabilityRegistry()
    registry.register(Capability(name="business_understanding"))
    runtime = BusinessRuntime(
        store=ArtifactGraphStore(str(tmp_path)),
        registry=registry,
        planner=FakePlanner(),
        executor=FakeExecutor(),
    )

    result = asyncio.run(runtime.run(
        prd_text="Original PRD text",
        domain_hint="retail",
        project_id="project-99",
    ))

    assert result.status == "completed"
    assert captured == {
        "capability": "business_understanding",
        "input_text": "Original PRD text",
        "project_id": "project-99",
    }


def test_runtime_response_projects_capability_execution_metadata(tmp_path):
    from app.artifacts import ArtifactGraphStore
    from app.capabilities.runner import _runtime_result_to_agent_response
    from app.capabilities.runtime import RuntimePhase, RuntimeResult

    result = RuntimeResult(
        status=RuntimePhase.COMPLETED,
        artifact_graph=ArtifactGraphStore(str(tmp_path / "artifacts")),
        capability_executions=[{
            "capability_name": "risk_analysis",
            "status": "success",
            "artifacts_produced": ["risk-1"],
            "backend": "nanobot",
            "mode": "real",
            "retries": 1,
            "attempts": [
                {"attempt": 1, "outcome": "failed", "retryable": True},
                {"attempt": 2, "outcome": "success", "retryable": False},
            ],
        }],
    )

    response = _runtime_result_to_agent_response(
        result=result,
        project_id="projection-project",
        execution_id="projection-run",
        artifact_scope="tmp/projection-project/projection-run",
        board=None,
    )

    assert response["runtime"]["capability_executions"][0]["capability_name"] == "risk_analysis"
    assert response["runtime"]["capability_executions"][0]["retries"] == 1


def test_business_runtime_preserves_error_terminal_phase(tmp_path):
    from app.artifacts import ArtifactGraphStore
    from app.capabilities.registry import CapabilityRegistry
    from app.capabilities.runtime import BusinessRuntime, RuntimePhase

    class FailingPlanner:
        async def plan(self, prd_text, domain_hint="", goals=None):
            raise RuntimeError("planner exploded")

    runtime = BusinessRuntime(
        store=ArtifactGraphStore(str(tmp_path)),
        registry=CapabilityRegistry(),
        planner=FailingPlanner(),
    )

    result = asyncio.run(runtime.run(
        prd_text="Broken PRD",
        domain_hint="retail",
        project_id="project-error",
    ))

    assert result.status == RuntimePhase.ERROR
    assert result.errors == ["planner exploded"]


def test_default_registry_registers_legacy_compatibility_and_mock_coverage():
    from app.artifacts.types import ArtifactType
    from app.capabilities.executor import assert_mock_coverage
    from app.capabilities.registry import build_default_registry

    registry = build_default_registry()
    capability = registry.get("legacy_bsc_compatibility")

    assert capability is not None
    assert callable(capability.executor_fn)
    assert capability.tags == ["legacy", "compatibility", "bsc"]
    assert capability.output_artifact_types == [
        ArtifactType.BUSINESS_MODEL,
        ArtifactType.RISK,
        ArtifactType.DECISION,
    ]
    assert_mock_coverage(registry)


def test_legacy_bsc_compatibility_executes_inside_business_runtime(tmp_path, monkeypatch):
    from app.artifacts import ArtifactGraphStore
    from app.capabilities.planner import MissionGraph, MissionStep
    from app.capabilities.registry import build_default_registry
    from app.capabilities.runtime import BusinessRuntime

    async def fake_compile(prd_content, llm_service=None, template_id=None):
        return {
            "business_system": {
                "business_domain": "content_safety",
                "objectives": [
                    {"objective": "Improve moderation speed"},
                    {"objective": "Reduce false positives"},
                ],
                "workflow": [
                    {"step": 1, "name": "Collect case", "action": "ingest request"},
                ],
                "roles": [
                    {"role": "Reviewer"},
                ],
                "responsibilities": [{"role": "Reviewer", "task": "Escalate edge cases"}],
                "sla": [{"metric": "turnaround", "target": "< 15m"}],
                "metrics": [{"name": "accuracy", "target": "98%"}],
                "kpi": [{"name": "backlog", "target": "< 100"}],
                "risks": [
                    {
                        "risk": "Policy drift",
                        "severity": "high",
                        "probability": "medium",
                        "mitigation": "Weekly review",
                        "dimension": "compliance",
                    }
                ],
                "report": {
                    "executive_summary": "Pilot a reviewer-assisted moderation flow.",
                    "title": "Legacy BSC report",
                },
            },
            "summary": "Legacy BSC compatibility summary",
            "pipeline": {"stages": [], "total_ms": 12, "parallel": True},
            "workspace": {},
        }

    class LegacyOnlyPlanner:
        async def plan(self, prd_text, domain_hint="", goals=None):
            return MissionGraph(
                mission_id="legacy-1",
                mission="legacy_bridge",
                title="Legacy Bridge",
                domain=domain_hint,
                planning_mode="template",
                steps=[
                    MissionStep(
                        step_id="s1",
                        capability_name="legacy_bsc_compatibility",
                        parallel_group=0,
                    )
                ],
                required_capabilities=["legacy_bsc_compatibility"],
            )

    monkeypatch.setattr(
        "app.capabilities.legacy_bsc.compile_to_business_system_async",
        fake_compile,
    )

    runtime = BusinessRuntime(
        store=ArtifactGraphStore(str(tmp_path)),
        registry=build_default_registry(),
        planner=LegacyOnlyPlanner(),
        executor_backend="nanobot",
    )

    result = asyncio.run(runtime.run(
        prd_text="Legacy runtime PRD",
        domain_hint="content_safety",
        project_id="legacy-project",
    ))

    assert result.status == "completed"
    assert result.export["business_domain"] == "content_safety"
    assert result.export["workflow"][0]["name"] == "Collect case"
    assert result.export["roles"][0]["role"] == "Reviewer"
    assert result.export["risks"][0]["risk"] == "Policy drift"
    assert result.export["_artifact_graph"]["decisions"][0]["decision_statement"]


def test_nanobot_mock_backend_produces_structured_artifacts(tmp_path, monkeypatch):
    from app.artifacts import ArtifactGraphStore
    from app.capabilities.planner import MissionGraph, MissionStep
    from app.capabilities.registry import build_default_registry
    from app.capabilities.runtime import BusinessRuntime
    from app.services.llm_adapter import LLMAdapter

    class BusinessOnlyPlanner:
        async def plan(self, prd_text, domain_hint="", goals=None):
            return MissionGraph(
                mission_id="mock-1",
                mission="mock_business_understanding",
                title="Mock Business Understanding",
                domain=domain_hint,
                planning_mode="template",
                steps=[
                    MissionStep(
                        step_id="s1",
                        capability_name="business_understanding",
                        parallel_group=0,
                    )
                ],
                required_capabilities=["business_understanding"],
            )

    monkeypatch.setattr(
        "app.services.llm_adapter.get_llm_adapter",
        lambda force_mock=False: LLMAdapter(force_mock=True),
    )

    runtime = BusinessRuntime(
        store=ArtifactGraphStore(str(tmp_path)),
        registry=build_default_registry(),
        planner=BusinessOnlyPlanner(),
        executor_backend="nanobot",
    )

    result = asyncio.run(runtime.run(
        prd_text="Support automation PRD",
        domain_hint="customer_service",
        project_id="mock-project",
    ))

    assert result.status == "completed"
    assert result.export["business_domain"] == "customer_service"
    assert result.export["objectives"]
    assert result.export["_artifact_graph"]["biz_models"]
