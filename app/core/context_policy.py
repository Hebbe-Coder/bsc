"""Explicit context inheritance policies for agent executions.

The policy is intentionally deterministic. It does not call an LLM to create a
summary, so a fork or resume request cannot silently change meaning because a
summarizer failed. Hosts may replace the compacted summary later while keeping
the same contract and budget metadata.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from typing import Iterable

from pydantic import BaseModel, Field

from app.core.prompt_context import estimate_prompt_tokens, truncate_prompt_text


class ContextPolicy(str, Enum):
    FRESH = "fresh"
    FORK = "fork"
    RESUME = "resume"


class ContextItem(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = ""
    source_session_id: str = ""
    priority: int = Field(default=0, ge=0, le=100)


class ContextUsage(BaseModel):
    policy: ContextPolicy
    max_tokens: int = Field(ge=64)
    estimated_tokens: int = Field(ge=0)
    inherited_items: int = Field(ge=0)
    included_items: int = Field(ge=0)
    summarized_items: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    context_truncated: bool = False
    persistent_items: int = Field(default=0, ge=0)
    persistent_included: int = Field(default=0, ge=0)
    omitted_items: int = Field(default=0, ge=0)
    compaction_mode: str = "summary"
    manifest_id: str = ""
    recoverable_source_sessions: list[str] = Field(default_factory=list)


class ContextPacket(BaseModel):
    policy: ContextPolicy
    rendered_input: str
    usage: ContextUsage
    manifest: "ContextManifest"


class ContextReference(BaseModel):
    """A redacted record of one context segment used by a model request."""

    role: str
    source_session_id: str = ""
    priority: int = Field(ge=0, le=100)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    estimated_tokens: int = Field(ge=0)
    disposition: str = "included"


class ContextManifest(BaseModel):
    """Inspectable context composition without retaining prompt/source bodies.

    A source session id is intentionally preserved when an inherited segment is
    compacted or omitted. The API can then rebuild a different bounded packet
    from the authoritative session projection instead of pretending the lossy
    summary is the original record.
    """

    revision: str = "bsc-context-v2"
    manifest_id: str = Field(pattern=r"^ctx_[a-f0-9]{16}$")
    policy: ContextPolicy
    compaction_mode: str = "summary"
    current_input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_session_ids: list[str] = Field(default_factory=list)
    inherited: list[ContextReference] = Field(default_factory=list)
    persistent: list[ContextReference] = Field(default_factory=list)


class ContextManager:
    """Build a bounded context packet for one runtime invocation."""

    def __init__(self, *, max_tokens: int = 12_000, max_verbatim_items: int = 6) -> None:
        if max_tokens < 64:
            raise ValueError("max_tokens must be at least 64")
        if max_verbatim_items < 1:
            raise ValueError("max_verbatim_items must be positive")
        self.max_tokens = max_tokens
        self.max_verbatim_items = max_verbatim_items

    def build(
        self,
        input_text: str,
        *,
        policy: ContextPolicy | str = ContextPolicy.FRESH,
        inherited_items: Iterable[ContextItem | dict] = (),
        persistent_items: Iterable[ContextItem | dict] = (),
    ) -> ContextPacket:
        selected_policy = ContextPolicy(policy)
        current = input_text
        source = [
            item if isinstance(item, ContextItem) else ContextItem.model_validate(item)
            for item in inherited_items
            if (item.content if isinstance(item, ContextItem) else item.get("content", "")).strip()
        ]
        persistent = [
            item if isinstance(item, ContextItem) else ContextItem.model_validate(item)
            for item in persistent_items
            if (item.content if isinstance(item, ContextItem) else item.get("content", "")).strip()
        ]
        if selected_policy is ContextPolicy.RESUME and not source:
            raise ValueError("resume context requires a source session")

        if selected_policy is ContextPolicy.FRESH:
            if not persistent:
                bounded_input = truncate_prompt_text(current, self.max_tokens)
                return self._packet(
                    policy=selected_policy,
                    rendered_input=bounded_input,
                    current_input=current,
                    effective_input=bounded_input,
                    inherited=[],
                    persistent=persistent,
                    included=[],
                    summarized=[],
                    omitted=[],
                    persistent_included=0,
                    context_truncated=bounded_input != current,
                )
            persistent_rendered, persistent_included, persistent_truncated = self._render_persistent(
                persistent
            )
            input_budget = max(
                1,
                self.max_tokens - estimate_prompt_tokens(persistent_rendered) - 16,
            )
            bounded_input = truncate_prompt_text(current, input_budget)
            sections = []
            if persistent_rendered:
                sections.append("[persistent project context]\n" + persistent_rendered)
            sections.append("[current request]\n" + bounded_input)
            rendered = "\n\n".join(sections)
            if estimate_prompt_tokens(rendered) > self.max_tokens:
                rendered = truncate_prompt_text(rendered, self.max_tokens)
            return self._packet(
                policy=selected_policy,
                rendered_input=rendered,
                current_input=current,
                effective_input=bounded_input,
                inherited=[],
                persistent=persistent,
                included=[],
                summarized=[],
                omitted=[],
                persistent_included=persistent_included,
                context_truncated=(
                    bounded_input != current
                    or persistent_truncated
                    or estimate_prompt_tokens(rendered) > self.max_tokens
                ),
            )
        else:
            # Priority first, then source order. The newest caller input is
            # always appended last so it cannot be displaced by inherited data.
            history = sorted(enumerate(source), key=lambda pair: (pair[1].priority, pair[0]))
            history = [item for _, item in history]

        # Project knowledge is not chat history.  It must be supplied to all
        # policies, including a fork or resume, while the latest request keeps
        # its protected budget at the end of the packet.
        persistent_rendered, persistent_included, persistent_truncated = self._render_persistent(
            persistent
        )
        input_budget = max(1, self.max_tokens // 3)
        bounded_input = truncate_prompt_text(current, input_budget)
        input_truncated = bounded_input != current
        history_budget = max(
            1,
            self.max_tokens
            - estimate_prompt_tokens(persistent_rendered)
            - estimate_prompt_tokens(bounded_input)
            - 48,
        )
        included: list[ContextItem] = []
        summary_candidates: list[ContextItem] = []
        used = 0

        for item in reversed(history):
            if len(included) >= self.max_verbatim_items:
                summary_candidates.append(item)
                continue
            item_text = f"[{item.role}] {item.content.strip()}"
            item_tokens = estimate_prompt_tokens(item_text)
            if used + item_tokens > history_budget:
                summary_candidates.append(item)
                continue
            included.append(item)
            used += item_tokens
        included.reverse()

        # Keep the compacted representation inside the remaining history
        # budget. Earlier versions rendered every summary candidate and then
        # truncated the whole packet, which made it impossible to tell which
        # inherited facts actually reached the provider.
        summary_budget = max(0, history_budget - used)
        summarized: list[ContextItem] = []
        omitted: list[ContextItem] = []
        summary_lines: list[str] = []
        for item in reversed(summary_candidates):
            prefix = f"[{item.role}] "
            available = summary_budget - estimate_prompt_tokens(prefix)
            if available <= 0:
                omitted.append(item)
                continue
            excerpt = truncate_prompt_text(item.content.strip(), min(available, 180))
            if not excerpt:
                omitted.append(item)
                continue
            line = prefix + excerpt
            summary_lines.append(line)
            summarized.append(item)
            summary_budget -= estimate_prompt_tokens(line)

        sections: list[str] = []
        if persistent_rendered:
            sections.append("[persistent project context]\n" + persistent_rendered)
        if summarized:
            sections.append("[inherited context summary]\n" + "\n".join(summary_lines))
        if included:
            sections.append(
                "[inherited context]\n"
                + "\n".join(f"[{item.role}] {item.content.strip()}" for item in included)
            )
        sections.append("[current request]\n" + bounded_input)
        rendered = "\n\n".join(sections)
        if estimate_prompt_tokens(rendered) > self.max_tokens:
            rendered = truncate_prompt_text(rendered, self.max_tokens)
            input_truncated = True

        return self._packet(
            policy=selected_policy,
            rendered_input=rendered,
            current_input=current,
            effective_input=bounded_input,
            inherited=source,
            persistent=persistent,
            included=included,
            summarized=summarized,
            omitted=omitted,
            persistent_included=persistent_included,
            context_truncated=(
                input_truncated
                or persistent_truncated
                or bool(summarized)
                or bool(omitted)
            ),
        )

    def _render_persistent(self, items: list[ContextItem]) -> tuple[str, int, bool]:
        """Render stable project context without treating it as chat history."""
        if not items:
            return "", 0, False
        budget = max(1, self.max_tokens // 2)
        included: list[str] = []
        used = 0
        truncated = False
        for item in sorted(items, key=lambda candidate: candidate.priority, reverse=True):
            label = "project knowledge" if item.role == "project_knowledge" else item.role
            prefix = f"[{label}] "
            available = budget - used - estimate_prompt_tokens(prefix)
            if available <= 0:
                truncated = True
                continue
            content = truncate_prompt_text(item.content.strip(), available)
            if not content:
                truncated = True
                continue
            included.append(prefix + content)
            used += estimate_prompt_tokens(prefix + content)
            truncated = truncated or content != item.content.strip()
        return "\n\n".join(included), len(included), truncated

    def _packet(
        self,
        *,
        policy: ContextPolicy,
        rendered_input: str,
        current_input: str,
        effective_input: str,
        inherited: list[ContextItem],
        persistent: list[ContextItem],
        included: list[ContextItem],
        summarized: list[ContextItem],
        omitted: list[ContextItem],
        persistent_included: int,
        context_truncated: bool,
    ) -> ContextPacket:
        manifest = self._manifest(
            policy=policy,
            current_input=current_input,
            inherited=inherited,
            persistent=persistent,
            included=included,
            summarized=summarized,
            omitted=omitted,
            persistent_included=persistent_included,
        )
        return ContextPacket(
            policy=policy,
            rendered_input=rendered_input,
            usage=ContextUsage(
                policy=policy,
                max_tokens=self.max_tokens,
                estimated_tokens=estimate_prompt_tokens(rendered_input),
                inherited_items=len(inherited),
                included_items=len(included),
                summarized_items=len(summarized),
                omitted_items=len(omitted),
                input_tokens=estimate_prompt_tokens(effective_input),
                context_truncated=context_truncated,
                persistent_items=len(persistent),
                persistent_included=persistent_included,
                compaction_mode=manifest.compaction_mode,
                manifest_id=manifest.manifest_id,
                recoverable_source_sessions=manifest.source_session_ids,
            ),
            manifest=manifest,
        )

    def _manifest(
        self,
        *,
        policy: ContextPolicy,
        current_input: str,
        inherited: list[ContextItem],
        persistent: list[ContextItem],
        included: list[ContextItem],
        summarized: list[ContextItem],
        omitted: list[ContextItem],
        persistent_included: int,
    ) -> ContextManifest:
        included_ids = {id(item) for item in included}
        summarized_ids = {id(item) for item in summarized}
        omitted_ids = {id(item) for item in omitted}
        inherited_refs = [
            self._reference(
                item,
                disposition=(
                    "included" if id(item) in included_ids
                    else "summarized" if id(item) in summarized_ids
                    else "omitted" if id(item) in omitted_ids
                    else "excluded"
                ),
            )
            for item in inherited
        ]
        ordered_persistent = sorted(
            persistent,
            key=lambda candidate: candidate.priority,
            reverse=True,
        )
        persistent_refs = [
            self._reference(
                item,
                disposition=("persistent" if index < persistent_included else "omitted"),
            )
            for index, item in enumerate(ordered_persistent)
        ]
        source_session_ids = list(dict.fromkeys(
            reference.source_session_id
            for reference in inherited_refs
            if reference.source_session_id
        ))
        fingerprint_payload = {
            "revision": "bsc-context-v2",
            "policy": policy.value,
            "current_input_fingerprint": self._fingerprint(current_input),
            "source_session_ids": source_session_ids,
            "inherited": [reference.model_dump(mode="json") for reference in inherited_refs],
            "persistent": [reference.model_dump(mode="json") for reference in persistent_refs],
        }
        encoded = json.dumps(
            fingerprint_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return ContextManifest(
            manifest_id=f"ctx_{sha256(encoded).hexdigest()[:16]}",
            policy=policy,
            current_input_fingerprint=fingerprint_payload["current_input_fingerprint"],
            source_session_ids=source_session_ids,
            inherited=inherited_refs,
            persistent=persistent_refs,
        )

    @staticmethod
    def _fingerprint(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def _reference(self, item: ContextItem, *, disposition: str) -> ContextReference:
        content = item.content.strip()
        return ContextReference(
            role=item.role,
            source_session_id=item.source_session_id,
            priority=item.priority,
            fingerprint=self._fingerprint(content),
            estimated_tokens=estimate_prompt_tokens(content),
            disposition=disposition,
        )
