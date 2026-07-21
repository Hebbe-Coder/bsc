import asyncio

from app.artifacts import ArtifactGraphStore
from app.artifacts.types import ArtifactType, BaseArtifact
from app.capabilities.executor import (
    CapabilityExecutionPolicy,
    CapabilityExecutor,
    ExecutionResult,
)
from app.capabilities.planner import MissionGraph, MissionStep
from app.capabilities.registry import Capability, CapabilityRegistry
from app.capabilities.runtime import BusinessRuntime


def test_capability_executor_retries_only_retryable_failures(tmp_path):
    calls = 0

    class FlakyBackend:
        async def execute(self, capability, input_text="", project_id=""):
            nonlocal calls
            calls += 1
            if calls < 3:
                return ExecutionResult(
                    capability_name=capability.name,
                    status="failed",
                    error="temporary provider unavailable",
                    backend="fake",
                )
            return ExecutionResult(
                capability_name=capability.name,
                status="success",
                artifacts_produced=["artifact-1"],
                backend="fake",
            )

    executor = CapabilityExecutor(
        ArtifactGraphStore(str(tmp_path)),
        policy=CapabilityExecutionPolicy(
            max_attempts=3,
            attempt_timeout_seconds=1,
            initial_backoff_seconds=0,
        ),
    )
    executor._backend = FlakyBackend()

    result = asyncio.run(executor.execute(Capability(name="flaky")))

    assert calls == 3
    assert result.status == "success"
    assert result.retries == 2
    assert [attempt.outcome for attempt in result.attempts] == [
        "failed",
        "failed",
        "success",
    ]
    assert result.attempts[0].retryable is True
    assert result.attempts[-1].retryable is False


def test_capability_executor_does_not_retry_non_retryable_failure(tmp_path):
    calls = 0

    class InvalidInputBackend:
        async def execute(self, capability, input_text="", project_id=""):
            nonlocal calls
            calls += 1
            return ExecutionResult(
                capability_name=capability.name,
                status="failed",
                error="invalid capability payload",
                backend="fake",
            )

    executor = CapabilityExecutor(
        ArtifactGraphStore(str(tmp_path)),
        policy=CapabilityExecutionPolicy(
            max_attempts=3,
            attempt_timeout_seconds=1,
            initial_backoff_seconds=0,
        ),
    )
    executor._backend = InvalidInputBackend()

    result = asyncio.run(executor.execute(Capability(name="invalid")))

    assert calls == 1
    assert result.status == "failed"
    assert result.retries == 0
    assert result.attempts[0].retryable is False
    assert result.error_code == "invalid_request"


def test_capability_executor_records_and_retries_timeouts(tmp_path):
    calls = 0

    class HangingBackend:
        async def execute(self, capability, input_text="", project_id=""):
            nonlocal calls
            calls += 1
            await asyncio.sleep(1)

    executor = CapabilityExecutor(
        ArtifactGraphStore(str(tmp_path)),
        policy=CapabilityExecutionPolicy(
            max_attempts=2,
            attempt_timeout_seconds=0.005,
            initial_backoff_seconds=0,
        ),
    )
    executor._backend = HangingBackend()

    result = asyncio.run(executor.execute(Capability(name="timeout")))

    assert calls == 2
    assert result.status == "failed"
    assert result.error_code == "timeout"
    assert result.retries == 1
    assert [attempt.outcome for attempt in result.attempts] == ["timeout", "timeout"]
    assert all(attempt.retryable for attempt in result.attempts)


def test_runtime_applies_policy_to_direct_capability_and_projects_attempts(tmp_path):
    calls = 0

    async def flaky_capability(input_text, project_id, **_):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("connection reset by provider")
        return BaseArtifact(
            artifact_type=ArtifactType.EVIDENCE,
            project_id=project_id,
            label="Recovered evidence",
            description=input_text,
        )

    class OneStepPlanner:
        async def plan(self, prd_text, domain_hint="", goals=None):
            return MissionGraph(
                mission_id="retry-runtime",
                mission="retry runtime",
                title="Retry Runtime",
                steps=[
                    MissionStep(
                        step_id="flaky-step",
                        capability_name="flaky_capability",
                    )
                ],
                required_capabilities=["flaky_capability"],
            )

    registry = CapabilityRegistry()
    registry.register(Capability(
        name="flaky_capability",
        output_artifact_types=[ArtifactType.EVIDENCE],
        executor_fn=flaky_capability,
    ))
    runtime = BusinessRuntime(
        store=ArtifactGraphStore(str(tmp_path)),
        registry=registry,
        planner=OneStepPlanner(),
        executor=CapabilityExecutor(
            ArtifactGraphStore(str(tmp_path / "executor")),
            policy=CapabilityExecutionPolicy(
                max_attempts=2,
                attempt_timeout_seconds=1,
                initial_backoff_seconds=0,
            ),
        ),
    )

    result = asyncio.run(runtime.run(prd_text="Retail PRD", project_id="retail"))

    assert result.status == "completed"
    assert calls == 2
    assert result.capability_executions[0]["capability_name"] == "flaky_capability"
    assert result.capability_executions[0]["retries"] == 1
    assert [attempt["outcome"] for attempt in result.capability_executions[0]["attempts"]] == [
        "failed",
        "success",
    ]


def test_gap_detection_normalizes_realistic_model_category_aliases(tmp_path):
    class LogicalFlawLLM:
        last_mode = "real"
        last_usage = None

        async def generate(self, prompt):
            return (
                '{"gaps":[{"gap":"Demand forecast conflicts with the stated cash budget",'
                '"category":"logical_flaw","severity":"high",'
                '"recommendation":"Reconcile the forecast with cash constraints"}]}'
            )

    from app.capabilities.executor import NanobotAgentBackend

    store = ArtifactGraphStore(str(tmp_path))
    backend = NanobotAgentBackend(store, llm_service=LogicalFlawLLM())
    capability = Capability(
        name="gap_detection",
        output_artifact_types=[ArtifactType.GAP],
    )

    result = asyncio.run(backend.execute(capability, "Ecommerce inventory PRD", "ecommerce"))

    assert result.status == "success"
    gap = store.get(result.artifacts_produced[0])
    assert gap is not None
    assert gap.category.value == "analysis_insufficient"
