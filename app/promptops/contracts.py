"""Stable PromptOps request, revision, and audit-facing contracts."""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.llm_usage import ModelUsage


class PromptTask(str, Enum):
    """Task profiles with intentionally different quality/cost expectations."""

    SOP_COMPOSITION = "sop_composition"
    WIKI_COMPILATION = "wiki_compilation"
    RAG_ANSWER = "rag_answer"
    KNOWLEDGE_DISTILLATION = "knowledge_distillation"
    QUALITY_JUDGE = "quality_judge"
    LIGHTWEIGHT_EXTRACTION = "lightweight_extraction"
    RETRIEVAL_SUFFICIENCY = "retrieval_sufficiency"


class PromptAgentAudience(str, Enum):
    """The authority boundary for a model invocation."""

    PRIMARY = "primary"
    SUBAGENT = "subagent"


class PromptToolPolicy(str, Enum):
    """PromptOps is a structured-model boundary, not a tool executor."""

    STRUCTURED_MODEL_ONLY = "structured_model_only"


class PromptDelegationPolicy(str, Enum):
    """A provider request cannot spawn further agents or work on its own."""

    NO_DELEGATION = "no_delegation"


class PromptAgentDefinition(BaseModel):
    """Inspectable, least-privilege definition for one BSC model role.

    This is deliberately narrower than a general coding-agent profile. A
    PromptOps worker can produce a structured model response only; it cannot
    access tools, publish data, invoke MCP, or delegate work. Those actions
    remain behind their own BSC capability and approval contracts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_-]*$")
    revision: str = Field(min_length=1, max_length=128)
    audience: PromptAgentAudience
    supported_tasks: tuple[PromptTask, ...] = Field(min_length=1)
    tool_policy: PromptToolPolicy = PromptToolPolicy.STRUCTURED_MODEL_ONLY
    delegation_policy: PromptDelegationPolicy = PromptDelegationPolicy.NO_DELEGATION
    memory_policy: str = Field(default="governed_project_context_only", min_length=1, max_length=96)
    external_side_effects_allowed: bool = False

    @model_validator(mode="after")
    def prohibit_side_effects(self) -> "PromptAgentDefinition":
        if self.external_side_effects_allowed:
            raise ValueError("PromptOps agent definitions cannot allow external side effects")
        return self

    @classmethod
    def for_task(cls, task: PromptTask) -> "PromptAgentDefinition":
        """Return the versioned built-in profile for an exact task family."""
        profiles: dict[PromptTask, tuple[str, str, PromptAgentAudience]] = {
            PromptTask.SOP_COMPOSITION: ("sop_composer", "sop-composer-v1", PromptAgentAudience.PRIMARY),
            PromptTask.WIKI_COMPILATION: ("wiki_compiler", "wiki-compiler-v1", PromptAgentAudience.PRIMARY),
            PromptTask.RAG_ANSWER: ("knowledge_answerer", "knowledge-answerer-v1", PromptAgentAudience.PRIMARY),
            PromptTask.KNOWLEDGE_DISTILLATION: (
                "knowledge_distiller",
                "knowledge-distiller-v1",
                PromptAgentAudience.PRIMARY,
            ),
            PromptTask.QUALITY_JUDGE: ("quality_reviewer", "quality-reviewer-v1", PromptAgentAudience.SUBAGENT),
            PromptTask.LIGHTWEIGHT_EXTRACTION: (
                "evidence_extractor",
                "evidence-extractor-v1",
                PromptAgentAudience.SUBAGENT,
            ),
            PromptTask.RETRIEVAL_SUFFICIENCY: (
                "citation_planner",
                "citation-planner-v1",
                PromptAgentAudience.SUBAGENT,
            ),
        }
        agent_id, revision, audience = profiles[task]
        return cls(
            agent_id=agent_id,
            revision=revision,
            audience=audience,
            supported_tasks=(task,),
        )


class DataClassification(str, Enum):
    """Outbound-data classification; raw private data is fail-closed."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"


class PromptRequest(BaseModel):
    """One project-scoped model request before it crosses a provider boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    task: PromptTask
    revision: str = Field(min_length=1, max_length=128)
    system_prompt: str = Field(min_length=1, max_length=80_000)
    user_prompt: str = Field(min_length=1, max_length=1_000_000)
    data_classification: DataClassification = DataClassification.INTERNAL
    provider: str = Field(default="deepseek", min_length=1, max_length=64)
    # Runtime-only provider keys preserve existing key rotation for callers
    # such as RAG. The field is excluded from serialization and every audit
    # record, so credentials never enter the PromptOps ledger.
    provider_keys: tuple[str, ...] = Field(default_factory=tuple, exclude=True, repr=False)
    # A project operator may explicitly pin a compatible model revision. When
    # absent, the task router selects the quality/cost default.
    model_override: str = Field(default="", max_length=128)
    # Private/confidential content is permitted only after a caller has
    # produced a reviewable derived form. The original body never enters this
    # request in that mode.
    sanitized_derivative: bool = False
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4_000, ge=128, le=32_000)
    # Long governed transformations can require a different provider read
    # budget without silently changing the default for every PromptOps task.
    timeout_seconds: float | None = Field(default=None, ge=5.0, le=180.0)
    # Outer retries occur only after the structured client has exhausted its
    # key-rotation and JSON-repair behavior. Keep the default deliberately
    # small: a business/knowledge run should never become an unbounded spend.
    max_attempts: int = Field(default=2, ge=1, le=3)
    # Some governed transformations have a strict per-render spend and
    # latency budget. This bounds JSON parsing/repair calls inside one outer
    # PromptOps attempt without weakening the default compatibility behavior.
    max_structured_attempts: int = Field(default=2, ge=1, le=3)
    retry_initial_backoff_seconds: float = Field(default=0.5, ge=0.0, le=10.0)
    retry_max_backoff_seconds: float = Field(default=5.0, ge=0.0, le=30.0)
    max_rate_limit_retries: int = Field(default=1, ge=0, le=2)
    # References identify admitted project context without copying its body to
    # the audit log. They are identifiers, never prompt excerpts or secrets.
    context_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    # Callers may supply a stricter, exact-task profile. Otherwise the stable
    # built-in profile selected from ``task`` is used.
    agent_definition: PromptAgentDefinition | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("revision")
    @classmethod
    def normalize_revision(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("revision is required")
        return normalized

    @field_validator("provider_keys")
    @classmethod
    def normalize_provider_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("context_refs")
    @classmethod
    def normalize_context_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw_value in values:
            value = str(raw_value).strip()
            if not value:
                continue
            if len(value) > 256 or any(character in value for character in "\r\n\t"):
                raise ValueError("context_refs must be short, single-line identifiers")
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_agent_scope(self) -> "PromptRequest":
        if self.agent_definition is not None and self.task not in self.agent_definition.supported_tasks:
            raise ValueError("agent_definition does not permit this PromptTask")
        if self.retry_max_backoff_seconds < self.retry_initial_backoff_seconds:
            raise ValueError("retry_max_backoff_seconds cannot be less than retry_initial_backoff_seconds")
        return self

    @property
    def resolved_agent_definition(self) -> PromptAgentDefinition:
        return self.agent_definition or PromptAgentDefinition.for_task(self.task)

    @property
    def prompt_fingerprint(self) -> str:
        material = "\n".join((self.task.value, self.revision, self.system_prompt))
        return sha256(material.encode("utf-8")).hexdigest()

    @property
    def input_fingerprint(self) -> str:
        material = "\n".join((self.project_id, self.user_prompt))
        return sha256(material.encode("utf-8")).hexdigest()


class PromptAgentManifest(BaseModel):
    """Redacted, durable description of the exact model-role invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: str = "bsc-prompt-agent-manifest-v1"
    manifest_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    project_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_revision: str = Field(min_length=1)
    audience: PromptAgentAudience
    task: PromptTask
    model: str = Field(min_length=1)
    model_override_applied: bool
    tool_policy: PromptToolPolicy
    delegation_policy: PromptDelegationPolicy
    memory_policy: str = Field(min_length=1)
    external_side_effects_allowed: bool = False
    context_refs: tuple[str, ...] = Field(default_factory=tuple)
    context_ref_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def from_request(cls, request: PromptRequest, *, model: str) -> "PromptAgentManifest":
        definition = request.resolved_agent_definition
        context_ref_fingerprint = sha256(
            json.dumps(
                {"project_id": request.project_id, "context_refs": request.context_refs},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        payload = {
            "schema_revision": "bsc-prompt-agent-manifest-v1",
            "project_id": request.project_id,
            "agent_id": definition.agent_id,
            "agent_revision": definition.revision,
            "audience": definition.audience,
            "task": request.task,
            "model": model,
            "model_override_applied": bool(request.model_override.strip()),
            "tool_policy": definition.tool_policy,
            "delegation_policy": definition.delegation_policy,
            "memory_policy": definition.memory_policy,
            "external_side_effects_allowed": definition.external_side_effects_allowed,
            "context_refs": request.context_refs,
            "context_ref_fingerprint": context_ref_fingerprint,
            "prompt_fingerprint": request.prompt_fingerprint,
            "input_fingerprint": request.input_fingerprint,
        }
        manifest_fingerprint = sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return cls(manifest_fingerprint=manifest_fingerprint, **payload)


class PromptUsage(BaseModel):
    """Observed provider usage for a governed model request.

    A structured client may make a JSON-repair request internally. This folds
    every observed provider response while preserving whether the totals are
    complete. Missing provider usage is never estimated from prompt text.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_calls: int = Field(default=0, ge=0)
    reported_calls: int = Field(default=0, ge=0)
    complete: bool = False
    latency_ms: int = Field(default=0, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)

    @classmethod
    def from_model_usages(
        cls,
        usages: list[ModelUsage],
        *,
        latency_ms: int,
    ) -> "PromptUsage":
        if not usages:
            # The caller invokes this only after crossing the provider
            # boundary. The provider did not report token values, but one
            # attempt is still observable.
            return cls(provider_calls=1, latency_ms=latency_ms)

        reported = [usage for usage in usages if usage.reported]
        complete = len(reported) == len(usages) and all(usage.complete for usage in usages)

        def aggregate(field: str) -> int | None:
            values = [getattr(usage, field) for usage in usages]
            if any(value is None for value in values):
                return None
            return sum(int(value) for value in values)

        return cls(
            provider_calls=len(usages),
            reported_calls=len(reported),
            complete=complete,
            latency_ms=latency_ms,
            prompt_tokens=aggregate("prompt_tokens"),
            completion_tokens=aggregate("completion_tokens"),
            total_tokens=aggregate("total_tokens"),
            cached_tokens=aggregate("cached_tokens"),
            reasoning_tokens=aggregate("reasoning_tokens"),
        )

    @classmethod
    def fold(cls, attempts: list["PromptUsage"]) -> "PromptUsage":
        """Fold all outer attempts without estimating missing provider usage."""
        if not attempts:
            return cls()

        def aggregate(field: str) -> int | None:
            values = [getattr(attempt, field) for attempt in attempts]
            if any(value is None for value in values):
                return None
            return sum(int(value) for value in values)

        total_calls = sum(attempt.provider_calls for attempt in attempts)
        return cls(
            provider_calls=total_calls,
            reported_calls=sum(attempt.reported_calls for attempt in attempts),
            complete=bool(total_calls) and all(attempt.complete for attempt in attempts),
            latency_ms=sum(attempt.latency_ms for attempt in attempts),
            prompt_tokens=aggregate("prompt_tokens"),
            completion_tokens=aggregate("completion_tokens"),
            total_tokens=aggregate("total_tokens"),
            cached_tokens=aggregate("cached_tokens"),
            reasoning_tokens=aggregate("reasoning_tokens"),
        )


class PromptRun(BaseModel):
    """Result projection that is safe to pass to the caller and Studio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task: PromptTask
    revision: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    agent_manifest: PromptAgentManifest
    usage: PromptUsage
    attempt_count: int = Field(default=1, ge=1)
    retry_count: int = Field(default=0, ge=0)
    retry_categories: tuple[str, ...] = Field(default_factory=tuple)
    output: dict[str, Any]
