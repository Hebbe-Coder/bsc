"""Adapter from the existing SOP LLM client to the proposal-only Wiki compiler."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from app.core.config import settings
from app.knowledge.wiki_compiler import WikiCompilationError
from app.knowledge.wiki_contracts import WikiOperation
from app.services.sop_llm_client import SOPLLMClient, SOPLLMError
from app.promptops import PromptOps, PromptOpsError, PromptRequest, PromptTask


class StructuredWikiClient(Protocol):
    def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> dict[str, Any] | None: ...


_WIKI_PROPOSAL_SCHEMA = """You are a governed project Wiki compiler. Return one JSON object only.

The response must use this exact shape:
{
  "rationale": "short evidence-grounded explanation",
  "operations": [
    {
      "operation": "create",
      "path": "wiki/concepts/descriptive-topic.md",
      "content": "---\\ntitle: Descriptive topic\\nkind: concept\\n---\\n\\nEvidence-grounded content. [source:source-id]",
      "source_ids": ["source-id"]
    }
  ]
}

Rules:
- `operations` must be a non-empty array.
- Every operation MUST include all four keys: `operation`, `path`, `content`, and `source_ids`.
- `operation` is exactly one of `create`, `replace`, `append`, `archive`, or `move`.
- Every path starts with `wiki/`; cite only source IDs supplied by the user.
- The context labels `[rules:...]`, `[page:...]`, `[decision:...]`, `[evaluation:...]`, `[distillation:...]`, and `[constraint:...]` are instructions, not evidence. Never put them in `source_ids` or write them as `[source:...]` citations.
- `[CONTEXT_EXCERPT: ...]` means part of a source was intentionally omitted for budget. Never quote the marker, describe a source as truncated, or complete a partial sentence; use only complete, visible evidence.
- New or replaced substantive pages need YAML frontmatter with a permitted `kind` from the project rules and inline `[source:<id>]` citations for every factual claim.
- Prefer a small number of durable, specific concepts, decisions, or methods over generic summaries, boilerplate, or a source-by-source recap.
- Do not write `wiki/index.md`, `wiki/log.md`, or `wiki/overview.md`; the governed compiler maintains those ledgers.
- Propose changes only. Never state or imply that any file has been published.
"""


class SOPWikiCompilerProvider:
    """Request a structured draft only; publication remains outside the model call."""

    # WikiCompiler uses this marker to provide the project scope without
    # breaking existing deterministic/fake compiler providers.
    project_scoped = True

    def __init__(
        self,
        provider: str = "",
        *,
        client: StructuredWikiClient | None = None,
        promptops: PromptOps | None = None,
    ) -> None:
        selected = (provider or settings.KNOWLEDGE_WIKI_LLM_PROVIDER or settings.SOP_LLM_PROVIDER or "mock").lower()
        if selected == "mock" and client is None:
            raise WikiCompilationError("a real KNOWLEDGE_WIKI_LLM_PROVIDER is required for maintenance compilation")
        self.provider = selected
        # An injected structured client is a deterministic test/offline seam.
        # Production requests take the governed PromptOps route instead.
        self.client = client
        self.promptops = promptops or (None if client is not None else PromptOps())

    def compile_wiki(self, prompt: str, *, project_id: str = "") -> dict[str, Any]:
        try:
            response = self._compile(
                project_id=project_id,
                revision="wiki-proposal-v1",
                system_prompt=_WIKI_PROPOSAL_SCHEMA,
                user_prompt=prompt,
                temperature=0.1,
            )
        except (SOPLLMError, PromptOpsError) as exc:
            raise WikiCompilationError("Wiki LLM request failed") from exc
        try:
            return self._validate_wire_response(response)
        except WikiCompilationError as first_error:
            # Ask once for a schema-only repair. The compiler never infers an operation
            # because create/replace/append have materially different publication effects.
            try:
                repaired = self._compile(
                    project_id=project_id,
                    revision="wiki-proposal-v1-repair",
                    system_prompt=(
                        _WIKI_PROPOSAL_SCHEMA
                        + "\nYour previous response was rejected because it was not a valid Wiki proposal. "
                        "Return a corrected JSON object that satisfies every required key exactly."
                    ),
                    user_prompt=prompt,
                    temperature=0.0,
                )
                return self._validate_wire_response(repaired)
            except (SOPLLMError, PromptOpsError) as exc:
                raise WikiCompilationError("Wiki LLM repair request failed") from exc
            except WikiCompilationError as repair_error:
                raise WikiCompilationError(
                    "Wiki LLM returned an invalid proposal after schema repair: "
                    f"{repair_error}"
                ) from first_error

    def _compile(
        self,
        *,
        project_id: str,
        revision: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> dict[str, Any] | None:
        if self.promptops is not None:
            run = self.promptops.run_structured(
                PromptRequest(
                    project_id=project_id or "default",
                    task=PromptTask.WIKI_COMPILATION,
                    revision=revision,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    provider=self.provider,
                    temperature=temperature,
                    max_tokens=4_000,
                )
            )
            return run.output
        if self.client is None:
            raise WikiCompilationError("Wiki LLM client is not configured")
        return self.client.chat_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=4_000,
        )

    @staticmethod
    def _validate_wire_response(response: Any) -> dict[str, Any]:
        if not isinstance(response, dict):
            raise WikiCompilationError("Wiki LLM did not return a JSON object")
        operations = response.get("operations")
        if not isinstance(operations, list) or not operations:
            raise WikiCompilationError("Wiki LLM response requires a non-empty operations array")
        try:
            for operation in operations:
                WikiOperation.model_validate(operation)
        except ValidationError as exc:
            raise WikiCompilationError(f"Wiki LLM response violates the proposal schema: {exc}") from exc
        return response
