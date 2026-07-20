import asyncio

from app.artifacts import ArtifactGraphStore
from app.artifacts.types import ArtifactType, EvidenceArtifact, Severity
from app.capabilities.executor import NanobotAgentBackend
from app.capabilities.registry import Capability
from app.core.llm_usage import ModelUsage
from app.core.prompt_context import CapabilityPromptBudget, estimate_prompt_tokens


def _backend(tmp_path, *, max_tokens=360, input_max_tokens=120, artifact_max_tokens=100):
    store = ArtifactGraphStore(str(tmp_path / "artifacts"))
    return store, NanobotAgentBackend(
        store,
        prompt_budget=CapabilityPromptBudget(
            max_tokens=max_tokens,
            input_max_tokens=input_max_tokens,
            artifact_max_tokens=artifact_max_tokens,
        ),
    )


def test_prompt_budget_bounds_final_prompt_and_prioritizes_critical_inputs(tmp_path):
    store, backend = _backend(tmp_path)
    store.create_risk(
        "critical control failure " + "priority " * 160,
        severity=Severity.CRITICAL,
        artifact_id="risk-critical",
    )
    for index in range(12):
        store.create_risk(
            f"low priority risk {index} " + "bulk " * 160,
            severity=Severity.LOW,
            artifact_id=f"risk-low-{index:02d}",
        )

    capability = Capability(
        name="decision_support",
        input_artifact_types=[ArtifactType.RISK],
    )
    prompt, usage = backend._build_prompt_with_usage(capability, "")

    assert estimate_prompt_tokens(prompt) <= usage.max_tokens
    assert "critical control failure" in prompt
    assert usage.artifacts_included >= 1
    assert usage.artifacts_omitted > 0
    assert usage.artifacts_truncated >= 1


def test_prompt_budget_preserves_input_head_and_tail_when_truncated(tmp_path):
    _, backend = _backend(tmp_path, max_tokens=300, input_max_tokens=100)
    capability = Capability(name="custom_capability")
    input_text = "START-REQUIREMENT " + ("middle " * 300) + "FINAL-ACCEPTANCE"

    prompt, usage = backend._build_prompt_with_usage(capability, input_text)

    assert estimate_prompt_tokens(prompt) <= usage.max_tokens
    assert "START-REQUIREMENT" in prompt
    assert "FINAL-ACCEPTANCE" in prompt
    assert "[truncated by context budget]" in prompt
    assert usage.input_truncated is True


def test_evidence_validation_receives_actual_artifact_evidence(tmp_path):
    store, backend = _backend(tmp_path, max_tokens=600)
    store.create_assumption(
        "Customers accept the proposed workflow",
        artifact_id="assumption-1",
    )
    evidence = EvidenceArtifact(
        artifact_type=ArtifactType.EVIDENCE,
        label="Acceptance evidence",
        finding="verified-third-party-source confirms acceptance",
        artifact_id="evidence-1",
    )
    store.add(evidence)

    capability = Capability(
        name="evidence_validation",
        input_artifact_types=[ArtifactType.ASSUMPTION],
    )
    prompt, usage = backend._build_prompt_with_usage(capability, "")

    assert evidence.artifact_id in prompt
    assert "verified-third-party-source" in prompt
    assert "(see artifacts above)" not in prompt
    assert usage.artifacts_included == 2


def test_real_execution_projects_prompt_context_usage(tmp_path):
    class RealLLM:
        provider = "deepseek"
        last_mode = "real"
        last_usage = ModelUsage(
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=15,
            completion_tokens=8,
            total_tokens=23,
            reported=True,
            complete=True,
        )

        async def generate(self, prompt):
            return (
                '{"domain":"support","value_proposition":"faster service",'
                '"customer_segments":[],"objectives":[],"revenue_model":"",'
                '"key_activities":[],"key_resources":[]}'
            )

    store, backend = _backend(tmp_path)
    backend._llm = RealLLM()
    capability = Capability(
        name="business_understanding",
        output_artifact_types=[ArtifactType.BUSINESS_MODEL],
    )

    result = asyncio.run(backend.execute(capability, "short PRD", "project-1"))

    assert result.status == "success"
    assert result.prompt_context is not None
    assert result.prompt_context.estimated_tokens <= result.prompt_context.max_tokens
    assert result.model_usage is not None
    assert result.model_usage.total_tokens == 23
