"""LLM Adapter: unified async generate() interface for the Business Agent OS.

Bridges the gap between existing LLMService (chat-based) and the
Agent OS components that expect a simple generate(prompt) → str interface.

Usage:
    from app.services.llm_adapter import LLMAdapter

    llm = LLMAdapter()
    response = await llm.generate("Analyze this business model...")
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from app.core.llm_usage import ModelUsage

logger = logging.getLogger(__name__)


class LLMAdapter:
    """Unified async LLM interface for the Business Agent OS.

    Wraps the existing LLMService and provides:
      - generate(prompt) → str  (the interface all Agent OS components expect)
      - generate_json(prompt) → dict  (parsed JSON output)
      - Fallback to mock responses when LLM is unavailable.
    """

    def __init__(self, provider: str | None = None, force_mock: bool = False):
        self._provider = provider
        self._force_mock = force_mock
        self._sync_service = None
        self._ready: bool | None = None
        self._last_mode: str = ""
        self._last_usage: ModelUsage | None = None

    @property
    def is_ready(self) -> bool:
        if self._ready is None:
            try:
                svc = self._get_sync_service()
                self._ready = svc.is_ready() and not self._force_mock
            except Exception:
                self._ready = False
        return self._ready

    @property
    def provider(self) -> str:
        return getattr(self._get_sync_service(), "provider", "")

    @property
    def force_mock(self) -> bool:
        return self._force_mock

    @property
    def last_mode(self) -> str:
        return self._last_mode

    @property
    def last_usage(self) -> ModelUsage | None:
        return self._last_usage

    def _get_sync_service(self):
        if self._sync_service is None:
            from app.services.llm_service import LLMService
            self._sync_service = LLMService(
                provider=self._provider, force_mock=self._force_mock,
            )
        return self._sync_service

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a text response from the LLM.

        Args:
            prompt: The main prompt (becomes user_prompt).
            system_prompt: Optional system instruction.
            temperature: Creativity (None = default).
            max_tokens: Max output length.

        Returns:
            LLM response text.
        """
        if not system_prompt:
            # Auto-detect: if prompt is a single block, use generic system prompt
            system_prompt = (
                "You are a Business Agent OS reasoning engine. "
                "Respond with the requested output format (JSON when applicable). "
                "Be precise and structured."
            )

        try:
            svc = self._get_sync_service()
            # Run synchronous chat in thread pool
            result = await asyncio.to_thread(
                svc.chat,
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Extract text from result
            if isinstance(result, dict):
                # Check if this is a parsed JSON response (not a raw content dict)
                if "_meta" in result:
                    metadata = result["_meta"]
                    self._last_mode = str(metadata.get("mode", ""))
                    raw_usage = metadata.get("usage")
                    self._last_usage = (
                        ModelUsage.model_validate(raw_usage)
                        if isinstance(raw_usage, dict)
                        else None
                    )
                    # LLMService already parsed JSON; return as JSON string
                    import json as _json
                    clean = {k: v for k, v in result.items() if k != "_meta"}
                    return _json.dumps(clean, ensure_ascii=False) if clean else str(result)
                self._last_mode = "api"
                self._last_usage = None
                return result.get("content", result.get("text", str(result)))
            self._last_mode = "api"
            self._last_usage = None
            return str(result)

        except Exception as exc:
            self._last_usage = None
            logger.warning("LLM generate failed: %s", exc)
            raise

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> dict:
        """Generate and parse JSON response.

        Returns parsed dict, or {"_error": "..."} on failure.
        """
        import json as _json
        import re

        try:
            text = await self.generate(prompt, system_prompt, temperature)
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            return _json.loads(text)
        except _json.JSONDecodeError:
            # Try to extract JSON from response
            try:
                match = re.search(r"\{.*\}", text if 'text' in dir() else "", re.DOTALL)
                if match:
                    return _json.loads(match.group())
            except Exception:
                pass
            logger.warning("LLM generate_json: could not parse response")
            return {"_error": "JSON parse failed", "_raw": text if 'text' in dir() else ""}
        except Exception as exc:
            logger.warning("LLM generate_json failed: %s", exc)
            return {"_error": str(exc)}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_llm_adapter: Optional[LLMAdapter] = None


def get_llm_adapter(force_mock: bool = False) -> LLMAdapter:
    """Get or create the global LLM adapter instance."""
    global _llm_adapter
    if _llm_adapter is None or force_mock:
        _llm_adapter = LLMAdapter(force_mock=force_mock)
    return _llm_adapter


def reset_llm_adapter():
    """Reset the global adapter (for testing)."""
    global _llm_adapter
    _llm_adapter = None
