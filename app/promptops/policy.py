"""Task-model routing and fail-closed outbound data policy for PromptOps."""

from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.generation_provenance import sanitize_untrusted_text

from .contracts import DataClassification, PromptRequest, PromptTask


class PromptPolicyError(ValueError):
    """Raised before a provider is invoked when request policy is violated."""


class PromptModelRouter:
    """Route quality-critical work to Pro and bounded utility work to Flash."""

    PRO_TASKS = frozenset({
        PromptTask.SOP_COMPOSITION,
        PromptTask.WIKI_COMPILATION,
        PromptTask.RAG_ANSWER,
        PromptTask.KNOWLEDGE_DISTILLATION,
        PromptTask.QUALITY_JUDGE,
    })
    FLASH_TASKS = frozenset({
        PromptTask.LIGHTWEIGHT_EXTRACTION,
        PromptTask.RETRIEVAL_SUFFICIENCY,
    })

    def model_for(self, task: PromptTask, *, override: str = "") -> str:
        if override.strip():
            return override.strip()
        if task in self.PRO_TASKS:
            return "deepseek-v4-pro"
        if task in self.FLASH_TASKS:
            return "deepseek-v4-flash"
        raise PromptPolicyError(f"no model route configured for task: {task}")


@dataclass(frozen=True)
class PreparedPrompt:
    system_prompt: str
    user_prompt: str


class OutboundDataPolicy:
    """Fence untrusted text and prohibit raw private/confidential egress."""

    def prepare(self, request: PromptRequest) -> PreparedPrompt:
        if (
            request.data_classification in {DataClassification.PRIVATE, DataClassification.CONFIDENTIAL}
            and not request.sanitized_derivative
        ):
            raise PromptPolicyError(
                "raw private or confidential data cannot be sent to an external model"
            )
        return PreparedPrompt(
            system_prompt=request.system_prompt,
            user_prompt=sanitize_untrusted_text(
                request.user_prompt,
                data_kind=f"{request.data_classification.value}_project_context",
                ref_id=request.input_fingerprint[:16],
            ),
        )
