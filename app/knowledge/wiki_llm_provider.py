"""Adapter from the existing SOP LLM client to the proposal-only Wiki compiler."""

from __future__ import annotations

from app.core.config import settings
from app.knowledge.wiki_compiler import WikiCompilationError
from app.services.sop_llm_client import SOPLLMClient, SOPLLMError


class SOPWikiCompilerProvider:
    """Request a structured draft only; publication remains outside the model call."""

    def __init__(self, provider: str = "") -> None:
        selected = (provider or settings.KNOWLEDGE_WIKI_LLM_PROVIDER or settings.SOP_LLM_PROVIDER or "mock").lower()
        if selected == "mock":
            raise WikiCompilationError("a real KNOWLEDGE_WIKI_LLM_PROVIDER is required for maintenance compilation")
        self.client = SOPLLMClient(provider=selected)

    def compile_wiki(self, prompt: str) -> dict:
        try:
            response = self.client.chat_structured(
                system_prompt=(
                    "You are a governed project Wiki compiler. Return JSON only with rationale and operations. "
                    "Every operation must carry source_ids, use evidence only, and never claim publication."
                ),
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=4000,
            )
        except SOPLLMError as exc:
            raise WikiCompilationError("Wiki LLM request failed") from exc
        if not isinstance(response, dict):
            raise WikiCompilationError("Wiki LLM did not return a JSON object")
        return response
