"""One governed entry point for structured DeepSeek task execution."""

from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from time import sleep
from typing import Any, Callable
from uuid import uuid4

from app.core.llm_usage import ModelUsage

from .audit import PromptAuditStore
from .contracts import PromptAgentManifest, PromptRequest, PromptRun, PromptUsage
from .policy import OutboundDataPolicy, PromptModelRouter, PromptPolicyError
from .retry import decide_retry


class PromptOpsError(RuntimeError):
    """A provider failure with a stable, non-secret error category."""

    def __init__(self, category: str, message: str = "PromptOps request failed") -> None:
        self.category = category
        super().__init__(message)


class PromptOps:
    """Routes a versioned task through policy, model selection, and audit."""

    def __init__(
        self,
        *,
        router: PromptModelRouter | None = None,
        data_policy: OutboundDataPolicy | None = None,
        audit_store: PromptAuditStore | None = None,
        client_factory: Callable[..., Any] | None = None,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        self.router = router or PromptModelRouter()
        self.data_policy = data_policy or OutboundDataPolicy()
        root = Path(os.environ.get("PROMPTOPS_AUDIT_ROOT", "data/promptops"))
        self.audit_store = audit_store or PromptAuditStore(root)
        self.client_factory = client_factory
        self.sleep_func = sleep_func or sleep

    def run_structured(self, request: PromptRequest) -> PromptRun:
        run_id = f"prompt_{uuid4().hex}"
        model = self.router.model_for(request.task, override=request.model_override)
        manifest = PromptAgentManifest.from_request(request, model=model)
        try:
            prepared = self.data_policy.prepare(request)
        except PromptPolicyError as exc:
            self._audit(
                request,
                run_id,
                model,
                "policy_blocked",
                agent_manifest=manifest,
                error_category="outbound_data_policy",
            )
            raise
        attempt_usages: list[PromptUsage] = []
        retry_categories: list[str] = []
        rate_limit_retries = 0
        output: Any = None
        client: Any | None = None
        started_at: float | None = None
        for attempt_index in range(1, request.max_attempts + 1):
            client = None
            started_at = None
            try:
                client = self._client(
                    provider=request.provider,
                    model=model,
                    provider_keys=request.provider_keys,
                    timeout_seconds=request.timeout_seconds,
                )
                reset_usage = getattr(client, "reset_usage_tracking", None)
                if callable(reset_usage):
                    reset_usage()
                started_at = perf_counter()
                output = client.chat_structured(
                    system_prompt=prepared.system_prompt,
                    user_prompt=prepared.user_prompt,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
                break
            except Exception as exc:
                # Inspect exception shape rather than importing a concrete
                # provider exception. This remains one patchable boundary for
                # provider rotations and deterministic tests.
                category = str(getattr(exc, "category", "provider_request_failed") or "provider_request_failed")
                elapsed_ms = int((perf_counter() - started_at) * 1000) if started_at is not None else 0
                attempt_usages.append(
                    self._usage_for(client, latency_ms=elapsed_ms, provider_called=started_at is not None)
                )
                decision = decide_retry(
                    category,
                    retry_count=len(retry_categories),
                    max_attempts=request.max_attempts,
                    max_rate_limit_retries=request.max_rate_limit_retries,
                    rate_limit_retries=rate_limit_retries,
                    initial_backoff_seconds=request.retry_initial_backoff_seconds,
                    max_backoff_seconds=request.retry_max_backoff_seconds,
                )
                if not decision.retry:
                    self._audit(
                        request,
                        run_id,
                        model,
                        "failed",
                        agent_manifest=manifest,
                        error_category=category,
                        usage=PromptUsage.fold(attempt_usages),
                        attempt_count=attempt_index,
                        retry_count=len(retry_categories),
                        retry_categories=tuple(retry_categories),
                    )
                    raise PromptOpsError(category) from exc
                retry_categories.append(category)
                if category == "rate_limited":
                    rate_limit_retries += 1
                self._audit(
                    request,
                    run_id,
                    model,
                    "retrying",
                    agent_manifest=manifest,
                    error_category=category,
                    usage=PromptUsage.fold(attempt_usages),
                    attempt_count=attempt_index,
                    retry_count=len(retry_categories),
                    retry_categories=tuple(retry_categories),
                    retry_delay_ms=int(decision.delay_seconds * 1000),
                )
                if decision.delay_seconds:
                    self.sleep_func(decision.delay_seconds)

        usage = self._usage_for(
            client,
            latency_ms=int((perf_counter() - started_at) * 1000) if started_at is not None else 0,
            provider_called=started_at is not None,
        )
        attempt_usages.append(usage)
        usage = PromptUsage.fold(attempt_usages)
        attempt_count = len(attempt_usages)
        if not isinstance(output, dict):
            self._audit(
                request,
                run_id,
                model,
                "invalid_response",
                agent_manifest=manifest,
                error_category="structured_response_invalid",
                usage=usage,
                attempt_count=attempt_count,
                retry_count=len(retry_categories),
                retry_categories=tuple(retry_categories),
            )
            raise PromptOpsError("structured_response_invalid")
        provider = str(getattr(client, "provider", "deepseek") or "deepseek")
        actual_model = str(getattr(client, "model", model) or model)
        # A client may expose a compatible concrete model name after routing.
        # Recompute instead of mutating the model field so the manifest hash
        # always authenticates the exact model recorded in the audit ledger.
        actual_manifest = PromptAgentManifest.from_request(request, model=actual_model)
        self._audit(
            request,
            run_id,
            actual_model,
            "completed",
            agent_manifest=actual_manifest,
            provider=provider,
            usage=usage,
            attempt_count=attempt_count,
            retry_count=len(retry_categories),
            retry_categories=tuple(retry_categories),
        )
        return PromptRun(
            run_id=run_id,
            project_id=request.project_id,
            task=request.task,
            revision=request.revision,
            provider=provider,
            model=actual_model,
            prompt_fingerprint=request.prompt_fingerprint,
            input_fingerprint=request.input_fingerprint,
            agent_manifest=actual_manifest,
            usage=usage,
            attempt_count=attempt_count,
            retry_count=len(retry_categories),
            retry_categories=tuple(retry_categories),
            output=output,
        )

    def _audit(
        self,
        request: PromptRequest,
        run_id: str,
        model: str,
        status: str,
        *,
        agent_manifest: PromptAgentManifest,
        provider: str = "deepseek",
        error_category: str = "",
        usage: PromptUsage | None = None,
        attempt_count: int = 1,
        retry_count: int = 0,
        retry_categories: tuple[str, ...] = (),
        retry_delay_ms: int = 0,
    ) -> None:
        observed_usage = usage or PromptUsage()
        self.audit_store.append({
            "run_id": run_id,
            "project_id": request.project_id,
            "task": request.task.value,
            "revision": request.revision,
            "provider": provider,
            "model": model,
            "status": status,
            "error_category": error_category,
            "prompt_fingerprint": request.prompt_fingerprint,
            "input_fingerprint": request.input_fingerprint,
            "data_classification": request.data_classification.value,
            "sanitized_derivative": request.sanitized_derivative,
            "agent_manifest_fingerprint": agent_manifest.manifest_fingerprint,
            "agent_id": agent_manifest.agent_id,
            "agent_revision": agent_manifest.agent_revision,
            "agent_audience": agent_manifest.audience.value,
            "tool_policy": agent_manifest.tool_policy.value,
            "delegation_policy": agent_manifest.delegation_policy.value,
            "memory_policy": agent_manifest.memory_policy,
            "external_side_effects_allowed": agent_manifest.external_side_effects_allowed,
            "context_ref_count": len(agent_manifest.context_refs),
            "context_ref_fingerprint": agent_manifest.context_ref_fingerprint,
            "provider_calls": observed_usage.provider_calls,
            "provider_usage_reported_calls": observed_usage.reported_calls,
            "provider_usage_complete": observed_usage.complete,
            "provider_latency_ms": observed_usage.latency_ms,
            "provider_prompt_tokens": observed_usage.prompt_tokens,
            "provider_completion_tokens": observed_usage.completion_tokens,
            "provider_total_tokens": observed_usage.total_tokens,
            "provider_cached_tokens": observed_usage.cached_tokens,
            "provider_reasoning_tokens": observed_usage.reasoning_tokens,
            "attempt_count": attempt_count,
            "retry_count": retry_count,
            "retry_categories": list(retry_categories),
            "retry_delay_ms": retry_delay_ms,
        })

    @staticmethod
    def _usage_for(
        client: Any | None,
        *,
        latency_ms: int,
        provider_called: bool,
    ) -> PromptUsage:
        if not provider_called:
            return PromptUsage(latency_ms=latency_ms)
        raw_usages = getattr(client, "last_call_usages", ()) if client is not None else ()
        usages: list[ModelUsage] = []
        if isinstance(raw_usages, (list, tuple)):
            for raw_usage in raw_usages:
                try:
                    usages.append(
                        raw_usage
                        if isinstance(raw_usage, ModelUsage)
                        else ModelUsage.model_validate(raw_usage)
                    )
                except (TypeError, ValueError):
                    # An unrelated third-party field cannot be treated as a
                    # provider-reported usage record.
                    continue
        if not usages:
            raw_usage = getattr(client, "last_usage", None) if client is not None else None
            try:
                if raw_usage is not None:
                    usages.append(
                        raw_usage
                        if isinstance(raw_usage, ModelUsage)
                        else ModelUsage.model_validate(raw_usage)
                    )
            except (TypeError, ValueError):
                pass
        return PromptUsage.from_model_usages(usages, latency_ms=latency_ms)

    def _client(
        self,
        *,
        provider: str,
        model: str,
        provider_keys: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"provider": provider, "model": model}
        if provider_keys:
            kwargs["keys"] = list(provider_keys)
        if timeout_seconds is not None:
            kwargs["timeout"] = timeout_seconds
        if self.client_factory is not None:
            return self.client_factory(**kwargs)
        from app.services.sop_llm_client import SOPLLMClient

        return SOPLLMClient(**kwargs)
