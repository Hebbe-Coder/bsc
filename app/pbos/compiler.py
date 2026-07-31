"""Contextual Personal Execution Plan compiler with an auditable fallback."""

from __future__ import annotations

import copy
import json
import hashlib
from typing import Any

from app.artifacts import (
    ArtifactStatus,
    CapabilityArtifact,
    DiagnosisArtifact,
    ExperienceArtifact,
    MissionArtifact,
    PersonalProfileArtifact,
    SOPVersionArtifact,
)
from app.core.config import settings
from app.core.prompt_context import estimate_prompt_tokens, truncate_prompt_text
from app.services.sop_llm_client import PROVIDER_KEY_MAP, PROVIDER_REGISTRY, SOPLLMClient


class PBOSPlanCompiler:
    """Compile a task-specific plan from personal and governed project context."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    @classmethod
    def from_settings(cls) -> "PBOSPlanCompiler":
        provider = str(settings.SOP_LLM_PROVIDER or settings.LLM_PROVIDER or "").strip().lower()
        key_spec = PROVIDER_KEY_MAP.get(provider)
        if not key_spec or not str(getattr(settings, key_spec[0], "") or "").strip():
            return cls()
        try:
            # A PBOS plan is an interactive, bounded planning delta. It should
            # not inherit a slower research model selected for distillation.
            model = str(settings.PBOS_LLM_MODEL or "").strip()
            if not model:
                model = str(PROVIDER_REGISTRY.get(provider, {}).get("model") or "")
            return cls(SOPLLMClient(
                provider=provider,
                model=model or None,
                timeout=float(settings.PBOS_LLM_TIMEOUT_SECONDS),
            ))
        except Exception:
            return cls()

    def compile(
        self,
        *,
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact | None,
        profile: PersonalProfileArtifact | None,
        capabilities: list[CapabilityArtifact],
        experiences: list[ExperienceArtifact],
        strategies: list[SOPVersionArtifact],
        feedback: list[dict[str, str]],
        knowledge_context: dict[str, Any],
    ) -> dict[str, Any]:
        documents = [item for item in knowledge_context.get("documents", []) if isinstance(item, dict)]
        baseline = self._baseline(
            mission=mission,
            diagnosis=diagnosis,
            profile=profile,
            capabilities=capabilities,
            experiences=experiences,
            feedback=feedback,
            knowledge_context=knowledge_context,
        )
        baseline["compiler_metadata"]["response_language"] = self._response_language(mission, profile)
        strategy_assets = self._matching_strategy_assets(
            strategies,
            comparison_key=str(baseline.get("comparison_key") or ""),
            comparison_context=str(baseline.get("comparison_context") or ""),
        )
        self._apply_strategy_assets(baseline, strategy_assets)
        deterministic_phases = copy.deepcopy(baseline["phases"])
        if self.client is None:
            return self._finalize_plan(
                baseline,
                documents,
                knowledge_context,
                deterministic_phases,
                mission,
            )
        prompt_payload = self._prompt_payload(
            mission, diagnosis, profile, capabilities, experiences, strategy_assets, feedback, knowledge_context
        )
        baseline["compiler_metadata"]["llm_prompt_context"] = self._prompt_usage(
            prompt_payload,
            documents_available=len(documents),
        )
        try:
            generated = self.client.chat_structured(
                system_prompt=self._system_prompt(),
                user_prompt=json.dumps(prompt_payload, ensure_ascii=False),
                temperature=0.2,
                max_tokens=max(256, int(settings.PBOS_LLM_MAX_OUTPUT_TOKENS)),
                max_structured_attempts=max(
                    1,
                    min(3, int(settings.PBOS_LLM_MAX_STRUCTURED_ATTEMPTS)),
                ),
            )
            self._record_llm_diagnostics(baseline)
            normalized = self._normalize(generated)
        except Exception as exc:
            baseline["compiler_metadata"]["llm_failure"] = str(getattr(exc, "category", "request_failed"))
            self._record_llm_diagnostics(baseline)
            return self._finalize_plan(
                baseline,
                documents,
                knowledge_context,
                deterministic_phases,
                mission,
            )
        if normalized is None:
            baseline["compiler_metadata"]["llm_failure"] = str(
                getattr(self.client, "last_structured_failure", "structured_response_invalid")
            )
            return self._finalize_plan(
                baseline,
                documents,
                knowledge_context,
                deterministic_phases,
                mission,
            )
        # The model may improve the execution wording, but cannot erase the
        # declared profile, evidence state, or governed-context traceability.
        for key in ("rationale", "risks", "success_criteria", "evidence_gap_plan"):
            baseline[key] = self._merge_text_items(baseline[key], normalized.get(key, []))
        baseline["title"] = normalized["title"]
        baseline["phases"] = self._merge_phases(baseline["phases"], normalized["phases"])
        baseline["compiler_metadata"] = {
            **baseline["compiler_metadata"],
            "mode": "llm_contextual",
            "provider": str(getattr(self.client, "provider", "configured")),
            "model": str(getattr(self.client, "model", "")),
        }
        return self._finalize_plan(
            baseline,
            documents,
            knowledge_context,
            deterministic_phases,
            mission,
        )

    def _record_llm_diagnostics(self, baseline: dict[str, Any]) -> None:
        """Persist only structural provider diagnostics, never a model response body."""
        shape = getattr(self.client, "last_response_shape", None)
        if isinstance(shape, dict):
            baseline["compiler_metadata"]["llm_response_shape"] = {
                str(key): value
                for key, value in shape.items()
                if isinstance(value, (str, int, float, bool, type(None), list))
            }
        attempts = getattr(self.client, "last_structured_attempts", None)
        if isinstance(attempts, list):
            baseline["compiler_metadata"]["llm_attempts"] = [
                {
                    "attempt": int(item.get("attempt", 0)),
                    "json_mode": bool(item.get("json_mode", False)),
                    "max_tokens": int(item.get("max_tokens", 0)),
                    "result": str(item.get("result", "unknown")),
                }
                for item in attempts
                if isinstance(item, dict)
            ][:3]

    @staticmethod
    def _merge_text_items(base: list[str], generated: list[str], limit: int = 12) -> list[str]:
        """Preserve evidence-led compiler facts while admitting model suggestions."""
        merged: list[str] = []
        for item in [*base, *generated]:
            value = str(item).strip()
            if value and value not in merged:
                merged.append(value)
            if len(merged) >= limit:
                break
        return merged

    @staticmethod
    def _merge_phases(base: list[dict[str, Any]], generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep deterministic execution contracts when model wording is partial."""
        merged: list[dict[str, Any]] = []
        for index, phase in enumerate(generated):
            baseline = base[index] if index < len(base) else {}
            value = dict(baseline)
            for key in ("title", "why_now", "inputs", "actions", "outputs", "checks", "decision_point"):
                candidate = phase.get(key)
                if candidate not in (None, "", [], {}):
                    value[key] = candidate
            merged.append(value)
        return merged or base

    def _finalize_plan(
        self,
        plan: dict[str, Any],
        documents: list[dict[str, Any]],
        knowledge_context: dict[str, Any],
        deterministic_phases: list[dict[str, Any]],
        mission: MissionArtifact,
    ) -> dict[str, Any]:
        """Apply non-negotiable plan constraints after all model merging."""
        finalized = self._apply_operational_completion_guard(
            self._remove_vault_echoes(plan, documents),
            knowledge_context,
            deterministic_phases,
        )
        finalized = self._ensure_strategy_guidance(finalized)
        phases = finalized.get("phases")
        if not isinstance(phases, list):
            return finalized
        compiler_metadata = finalized.get("compiler_metadata")
        response_language = (
            str(compiler_metadata.get("response_language") or "")
            if isinstance(compiler_metadata, dict)
            else ""
        )
        finalized["phases"], language_replacements = self._apply_mission_language_guard(
            phases,
            mission,
            force_chinese=response_language == "Chinese",
        )
        if language_replacements:
            finalized.setdefault("compiler_metadata", {})["language_guard"] = {
                "mission_language": "zh",
                "replacement_phases": language_replacements,
            }
        return finalized

    @classmethod
    def _apply_operational_completion_guard(
        cls,
        plan: dict[str, Any],
        knowledge_context: dict[str, Any],
        deterministic_phases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Do not turn a completed BSC-to-Obsidian mirror into the next task.

        The guard is deliberately narrow. It only replaces a phase when the
        model asks to sync, import, mirror, or project BSC evidence into
        Obsidian after the metadata-only operational state proves that the
        managed mirror already contains files. Normal Mission-specific
        evidence collection remains available.
        """
        operational_state = cls._safe_operational_state(knowledge_context)
        mirror = operational_state["managed_source_mirror"]
        metadata = plan.setdefault("compiler_metadata", {})
        metadata["operational_state"] = operational_state
        replaced: list[int] = []
        phases = plan.get("phases")
        if not isinstance(phases, list):
            return plan
        if mirror["state"] == "available":
            for index, phase in enumerate(phases):
                if not isinstance(phase, dict) or not cls._repeats_completed_source_projection(phase):
                    continue
                if index < len(deterministic_phases):
                    phases[index] = copy.deepcopy(deterministic_phases[index])
                    replaced.append(index + 1)
        if replaced:
            metadata["completed_operation_guard"] = {
                "operation": "bsc_obsidian_evidence_projection",
                "replacement_phase_indexes": replaced,
                "reason": "managed_source_mirror_available",
            }

        configured_routes = [
            item["id"]
            for item in operational_state["plugin_bridges"]["routes"]
            if item["route_state"] in {"configured_awaiting_export", "configured_awaiting_output"}
        ]
        plugin_replaced: list[int] = []
        plugin_ids: list[str] = []
        if configured_routes:
            for index, phase in enumerate(phases):
                if not isinstance(phase, dict):
                    continue
                matched = cls._repeats_configured_plugin_setup(phase, configured_routes)
                if not matched or index >= len(deterministic_phases):
                    continue
                phases[index] = copy.deepcopy(deterministic_phases[index])
                plugin_replaced.append(index + 1)
                plugin_ids.extend(matched)
        if plugin_replaced:
            metadata["plugin_bridge_guard"] = {
                "operation": "obsidian_plugin_setup",
                "route_ids": list(dict.fromkeys(plugin_ids)),
                "replacement_phase_indexes": plugin_replaced,
                "reason": "configured_route_awaiting_real_export",
            }

        if str(metadata.get("task_kind") or "") == "knowledge_delivery":
            generic_replaced: list[int] = []
            for index, phase in enumerate(phases):
                if (
                    not isinstance(phase, dict)
                    or index >= len(deterministic_phases)
                    or not cls._is_unrelated_growth_phase(phase)
                ):
                    continue
                phases[index] = copy.deepcopy(deterministic_phases[index])
                generic_replaced.append(index + 1)
            if generic_replaced:
                metadata["domain_specificity_guard"] = {
                    "task_kind": "knowledge_delivery",
                    "replacement_phase_indexes": generic_replaced,
                    "reason": "unrelated_growth_template",
                }
        return plan

    @staticmethod
    def _is_unrelated_growth_phase(phase: dict[str, Any]) -> bool:
        text = " ".join(
            str(value)
            for value in [phase.get("title"), *(phase.get("actions") or [])]
            if str(value).strip()
        ).casefold()
        return any(token in text for token in (
            "content experiment", "engagement metric", "audience behavior", "retention",
            "contrastive hook", "alternative opening", "record a result",
        ))

    @staticmethod
    def _safe_operational_state(knowledge_context: dict[str, Any]) -> dict[str, Any]:
        """Normalize planner-facing operational state to simple, non-secret facts."""
        raw = knowledge_context.get("operational_state")
        raw = raw if isinstance(raw, dict) else {}
        raw_mirror = raw.get("managed_source_mirror")
        raw_mirror = raw_mirror if isinstance(raw_mirror, dict) else {}
        raw_counts = raw.get("source_lifecycle_counts")
        source_counts = {
            str(key)[:64]: max(0, int(value))
            for key, value in (raw_counts.items() if isinstance(raw_counts, dict) else [])
            if isinstance(value, int) and not isinstance(value, bool)
        }
        raw_wiki = raw.get("published_wiki")
        raw_wiki = raw_wiki if isinstance(raw_wiki, dict) else {}
        raw_handoff = raw.get("weekly_handoff")
        raw_handoff = raw_handoff if isinstance(raw_handoff, dict) else {}
        raw_bridges = raw.get("plugin_bridges")
        raw_bridges = raw_bridges if isinstance(raw_bridges, dict) else {}
        valid_route_states = {
            "configured_awaiting_export",
            "captured",
            "configured_awaiting_output",
            "registered_output",
            "not_ready",
        }
        valid_capture_states = {
            "awaiting_trust",
            "trust_stale",
            "trust_unavailable",
            "captured",
            "registered_output",
            "files_detected_pending_registration",
            "files_detected_pending_capture",
            "ready_for_first_output",
            "ready_for_first_export",
            "route_unavailable",
        }
        plugin_routes: list[dict[str, str]] = []
        for value in raw_bridges.get("routes", []) if isinstance(raw_bridges.get("routes"), list) else []:
            if not isinstance(value, dict):
                continue
            plugin_id = str(value.get("id") or "").strip()[:80]
            adapter = str(value.get("adapter") or "").strip()[:48]
            if not plugin_id or not adapter:
                continue
            route_state = str(value.get("route_state") or "")
            capture_state = str(value.get("capture_state") or "")
            plugin_routes.append(
                {
                    "id": plugin_id,
                    "adapter": adapter,
                    "route_state": route_state if route_state in valid_route_states else "not_ready",
                    "capture_state": capture_state if capture_state in valid_capture_states else "route_unavailable",
                }
            )
            if len(plugin_routes) >= 12:
                break
        plugin_routes.sort(key=lambda item: item["id"])
        return {
            "source_lifecycle_counts": dict(sorted(source_counts.items())),
            "managed_source_mirror": {
                "state": "available" if str(raw_mirror.get("state") or "") == "available" else "awaiting_projection",
                "path": "01_Sources/bsc-evidence",
                "file_count": PBOSPlanCompiler._safe_nonnegative_int(raw_mirror.get("file_count")),
                "recorded_source_count": PBOSPlanCompiler._safe_nonnegative_int(raw_mirror.get("recorded_source_count")),
            },
            "published_wiki": {"page_count": PBOSPlanCompiler._safe_nonnegative_int(raw_wiki.get("page_count"))},
            "weekly_handoff": {
                "state": "available" if str(raw_handoff.get("state") or "") == "available" else "unavailable",
                "path": str(raw_handoff.get("path") or "")[:300],
            },
            "plugin_bridges": {
                "ready_route_count": sum(item["route_state"] != "not_ready" for item in plugin_routes),
                "routes": plugin_routes,
            },
        }

    @staticmethod
    def _safe_nonnegative_int(value: Any) -> int:
        if isinstance(value, bool):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _repeats_completed_source_projection(phase: dict[str, Any]) -> bool:
        values = [
            phase.get("title"),
            phase.get("why_now"),
            *(phase.get("actions") or []),
            *(phase.get("outputs") or []),
            *(phase.get("checks") or []),
        ]
        text = " ".join(str(value).casefold() for value in values if str(value).strip())
        english_target = ("obsidian" in text or "vault" in text) and (
            "bsc" in text or "source" in text or "evidence" in text
        )
        english_operation = any(term in text for term in ("sync", "import", "mirror", "projection")) or any(
            f"project {target}" in text for target in ("source", "sources", "evidence", "bsc")
        )
        chinese_target = ("obsidian" in text or "vault" in text) and ("bsc" in text or "来源" in text or "证据" in text)
        chinese_operation = any(term in text for term in ("同步", "导入", "镜像", "投影"))
        return (english_target and english_operation) or (chinese_target and chinese_operation)

    @staticmethod
    def _repeats_configured_plugin_setup(phase: dict[str, Any], configured_routes: list[str]) -> list[str]:
        """Return configured bridge ids when a phase repeats their setup work.

        Match only explicit Obsidian plugin configuration language and a
        declared route identifier. A generic connector action therefore stays
        available for a different integration that has not been configured.
        """
        values = [
            phase.get("title"),
            phase.get("why_now"),
            *(phase.get("actions") or []),
            *(phase.get("outputs") or []),
            *(phase.get("checks") or []),
        ]
        text = " ".join(str(value).casefold() for value in values if str(value).strip())
        compact_text = "".join(character for character in text if character.isalnum())
        setup_terms = (
            "configure",
            "configuration",
            "install",
            "setup",
            "set up",
            "reconfigure",
            "connect",
            "配置",
            "安装",
            "设置",
            "连接",
        )
        if "obsidian" not in text or not any(term in text for term in setup_terms):
            return []
        matched: list[str] = []
        for route_id in configured_routes:
            normalized = str(route_id).casefold().strip()
            compact_id = "".join(character for character in normalized if character.isalnum())
            short_id = compact_id.removeprefix("obsidian")
            if compact_id in compact_text or (short_id and short_id in compact_text):
                matched.append(route_id)
        return matched

    @classmethod
    def _apply_mission_language_guard(
        cls,
        phases: list[dict[str, Any]],
        mission: MissionArtifact,
        *,
        force_chinese: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, int]]]:
        """Keep an LLM's user-facing next actions in the Mission's language.

        Technical identifiers such as ``pytest`` remain valid, but a complete
        English instruction is a poor result for a Chinese Mission. This is a
        presentation guard, not translation: it replaces only fully English
        sentence-like actions with a bounded Mission-specific fallback.
        """
        if not force_chinese and not cls._uses_chinese(mission.title, mission.intent):
            return phases, []
        replacements: list[dict[str, Any]] = []
        fallback_actions = cls._chinese_fallback_actions(mission)
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            actions = [str(item).strip() for item in phase.get("actions") or [] if str(item).strip()]
            changed = False
            for action_index, action in enumerate(actions):
                if not cls._is_english_sentence(action):
                    continue
                actions[action_index] = fallback_actions[min(index, len(fallback_actions) - 1)]
                changed = True
            if changed:
                phase["actions"] = list(dict.fromkeys(actions))[:2]
                replacements.append({"phase_index": index + 1, "action_count": len(actions)})
        if replacements:
            return phases, replacements
        return phases, []

    @staticmethod
    def _uses_chinese(*values: str) -> bool:
        return any("\u4e00" <= character <= "\u9fff" for value in values for character in str(value))

    @classmethod
    def _response_language(
        cls,
        mission: MissionArtifact,
        profile: PersonalProfileArtifact | None,
    ) -> str:
        if cls._uses_chinese(mission.title, mission.intent):
            return "Chinese"
        preferences = profile.preferences if profile and isinstance(profile.preferences, dict) else {}
        language = str(preferences.get("language") or "").strip().lower()
        return "Chinese" if language.startswith("zh") else "Match the Mission's primary language"

    @staticmethod
    def _is_english_sentence(value: str) -> bool:
        if any("\u4e00" <= character <= "\u9fff" for character in value):
            return False
        latin_words = [word for word in value.replace("/", " ").split() if any(character.isalpha() for character in word)]
        return len(latin_words) >= 3

    @staticmethod
    def _chinese_fallback_actions(mission: MissionArtifact) -> list[str]:
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        objective = str(mission_context.get("goal") or mission.intent or mission.title).strip()[:120]
        kind = PBOSPlanCompiler._task_kind(f"{mission.title} {mission.intent}".lower())
        if kind == "knowledge_delivery":
            return [
                f"\u56f4\u7ed5\u201c{objective}\u201d\u6838\u67e5\u4e00\u9879\u53ef\u5f15\u7528\u4e8b\u5b9e\u3001\u4e00\u9879\u5f85\u9a8c\u8bc1\u7f3a\u53e3\u548c\u4e00\u4f4d\u51b3\u7b56\u8d1f\u8d23\u4eba\u3002",
                "\u4ece\u5df2\u53d1\u5e03 Wiki \u4e0e\u5468\u84b8\u998f\u6784\u9020\u4e00\u4e2a PRD \u4e13\u5c5e\u4e0a\u4e0b\u6587\u5305\uff0c\u5e76\u7f16\u8bd1\u53ef\u5ba1\u67e5 SOP\u3002",
                "\u8bb0\u5f55\u771f\u5b9e\u4ea4\u4ed8\u56de\u6267\u4e0e\u590d\u76d8\uff0c\u5c06\u5df2\u63a5\u53d7\u7ed3\u679c\u4e0e\u5019\u9009\u6a21\u578b\u5efa\u8bae\u5206\u5f00\u3002",
            ]
        if kind == "growth":
            return [
                f"围绕“{objective}”确定一个可量化的内容成效指标。",
                "设计只改变一个变量的内容对照实验，并记录基线。",
                "复盘实验结果，保留有效模式并明确下一次调整。",
            ]
        if kind == "engineering":
            return [
                f"将“{objective}”收敛为一个可验收的工程边界。",
                "实现一个可运行的最小闭环并保留测试或构建回执。",
                "记录结果、阻塞和下一次边界调整。",
            ]
        return [
            f"为“{objective}”区分事实、约束和待验证问题。",
            "执行一个受约束的最小动作并保留可审查结果。",
            "复盘结果和失败边界，再决定是否形成可复用方法。",
        ]

    @staticmethod
    def _prompt_usage(payload: dict[str, Any], *, documents_available: int) -> dict[str, int]:
        """Persist safe sizing evidence without retaining prompt or Vault text."""
        documents = payload.get("vault_context")
        included = len(documents) if isinstance(documents, list) else 0
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return {
            "estimated_input_tokens": estimate_prompt_tokens(serialized),
            "documents_available": documents_available,
            "documents_included": included,
            "documents_omitted": max(0, documents_available - included),
            "document_excerpt_max_tokens": max(64, int(settings.PBOS_LLM_CONTEXT_DOCUMENT_MAX_TOKENS)),
            "max_output_tokens": max(256, int(settings.PBOS_LLM_MAX_OUTPUT_TOKENS)),
            "max_structured_attempts": max(1, min(3, int(settings.PBOS_LLM_MAX_STRUCTURED_ATTEMPTS))),
        }

    @classmethod
    def _remove_vault_echoes(cls, plan: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
        """Keep private Vault text in the bounded prompt, never in the persisted plan."""
        if not documents:
            return plan

        plan["title"] = cls._sanitize_vault_text(
            str(plan.get("title") or ""), documents, field="title"
        )
        for key in ("rationale", "risks", "success_criteria", "evidence_gap_plan"):
            plan[key] = [
                cls._sanitize_vault_text(str(item), documents, field=key)
                for item in plan.get(key, [])
                if str(item).strip()
            ]
        for phase in plan.get("phases", []):
            if not isinstance(phase, dict):
                continue
            phase["title"] = cls._sanitize_vault_text(
                str(phase.get("title") or ""), documents, field="title"
            )
            phase["why_now"] = cls._sanitize_vault_text(
                str(phase.get("why_now") or ""), documents, field="why_now"
            )
            for key in ("inputs", "actions", "outputs", "checks"):
                phase[key] = [
                    cls._sanitize_vault_text(str(item), documents, field=key)
                    for item in phase.get(key, [])
                    if str(item).strip()
                ]
            decision = phase.get("decision_point")
            if isinstance(decision, dict):
                phase["decision_point"] = {
                    key: cls._sanitize_vault_text(str(value), documents, field="decision")
                    for key, value in decision.items()
                    if str(value).strip()
                }
        return plan

    @classmethod
    def _sanitize_vault_text(cls, value: str, documents: list[dict[str, Any]], *, field: str) -> str:
        """Replace a verbatim context echo with a reference-led execution instruction."""
        document = cls._matching_vault_document(value, documents)
        if document is None:
            return value
        ref = str(document.get("ref") or document.get("path") or "governed Vault source")
        title = str(document.get("title") or document.get("path") or "governed project context")[:200]
        if field == "title":
            return "Evidence-grounded execution phase"
        if field == "why_now":
            return "This phase needs a cited, decision-relevant fact before work widens."
        if field == "inputs":
            return f"Governed source reference: {ref}"
        if field == "decision":
            return "Is the cited evidence sufficient for the next bounded decision?"
        if field in {"rationale", "risks", "success_criteria", "evidence_gap_plan"}:
            return f"Use governed Vault source {title} ({ref}) as a cited planning input."
        return (
            f"Review governed Vault source {title} ({ref}) and record only the task-relevant "
            "evidence in this phase output."
        )

    @staticmethod
    def _matching_vault_document(value: str, documents: list[dict[str, Any]]) -> dict[str, Any] | None:
        normalized_value = " ".join(value.casefold().split())
        if not normalized_value:
            return None
        for document in documents:
            for line in str(document.get("excerpt") or "").splitlines():
                candidate = " ".join(line.strip().casefold().split())
                if len(candidate) < 32:
                    continue
                signature = candidate[: min(120, len(candidate))]
                if signature in normalized_value:
                    return document
        return None

    def _baseline(
        self,
        *,
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact | None,
        profile: PersonalProfileArtifact | None,
        capabilities: list[CapabilityArtifact],
        experiences: list[ExperienceArtifact],
        feedback: list[dict[str, str]],
        knowledge_context: dict[str, Any],
    ) -> dict[str, Any]:
        documents = [item for item in knowledge_context.get("documents", []) if isinstance(item, dict)]
        document_refs = list(dict.fromkeys(
            str(reference)
            for item in documents
            for reference in [item.get("ref"), *(item.get("supporting_refs") or [])]
            if str(reference)
        ))
        document_titles = [str(item.get("title") or item.get("path") or "project context") for item in documents]
        source_references = self._context_source_references(documents)
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        diagnosis_context = self._diagnosis_context(diagnosis)
        constraint_values = mission_context.get("constraints") or []
        constraints = [
            *[str(item) for item in constraint_values if str(item).strip()],
            *[str(item) for item in diagnosis_context.get("constraints", []) if str(item).strip()],
        ]
        constraints = list(dict.fromkeys(constraints))
        focus = profile.focus if profile else []
        verified_capabilities = [item.name for item in capabilities if item.evidence_count > 0]
        verified_experiences = [item.statement for item in experiences]
        # Task kind is determined by the Mission and its diagnosed constraints,
        # not a broad profile focus. A knowledge-engineering practitioner can
        # still have a distinct engineering or growth Mission.
        task_text = " ".join([
            mission.title,
            mission.intent,
            json.dumps(mission_context, ensure_ascii=False),
            json.dumps(diagnosis_context, ensure_ascii=False),
        ]).lower()
        kind = self._task_kind(task_text)
        # A Mission's explicit wording owns the domain. Profile focus is only
        # a tie-breaker for otherwise generic delivery requests, so a
        # knowledge-oriented profile cannot turn an explicit growth Mission
        # into a knowledge-delivery template.
        if kind == "delivery" and focus:
            kind = self._task_kind(" ".join(str(item) for item in focus))
        comparison = self._comparison_identity(mission, diagnosis_context, profile, kind)
        phases = self._phases(kind, mission, source_references, constraints)
        self._add_phase_contracts(phases, mission, document_titles, constraints, comparison["context"])
        feedback_actions = [item["statement"] for item in feedback if item.get("statement")]
        if feedback_actions:
            phases[-1]["actions"].extend(f"Resolve prior feedback: {item}" for item in feedback_actions[:3])
        context_grounded = bool(profile and documents)
        personalized = bool(context_grounded and (verified_capabilities or verified_experiences))
        state = "personalized" if personalized else ("context_grounded" if context_grounded else "capture_required")
        gaps: list[str] = []
        if not profile:
            gaps.append("Record your role, objectives, resources, and operating constraints before treating this as a personal plan.")
        if not documents:
            gaps.append("Add one governed project note, approved method, or evaluated output to connect the plan to your Vault.")
        if not verified_capabilities and not verified_experiences:
            gaps.append("Attach an observable delivery receipt and a three-minute reflection; do not promote a personal method yet.")
        rationale = [
            f"Mission intent: {mission.intent}",
            f"Mission objective: {mission_context.get('goal') or mission.intent}",
            f"Personal focus: {', '.join(focus) if focus else 'not declared'}",
            f"Comparable scenario: {comparison['context']}",
            f"Vault context: {', '.join(document_titles[:3]) if document_titles else 'none available'}",
            f"Verified personal assets: {', '.join(verified_capabilities + verified_experiences) if (verified_capabilities or verified_experiences) else 'none yet'}",
        ]
        operational_state = self._safe_operational_state(knowledge_context)
        if operational_state["managed_source_mirror"]["state"] == "available":
            rationale.append(
                "Operational state: the BSC evidence mirror is already available; advance the Mission instead of repeating source projection."
            )
        configured_route_count = sum(
            item["route_state"] in {"configured_awaiting_export", "configured_awaiting_output"}
            for item in operational_state["plugin_bridges"]["routes"]
        )
        if configured_route_count:
            rationale.append(
                "Operational state: configured Obsidian bridge routes are awaiting a real export; use the active Mission instead of repeating plugin setup."
            )
        rationale.extend(f"Governed source available for review: {source}" for source in source_references[:2])
        rationale.extend(
            f"Recorded feedback (unverified direction): {item}"
            for item in feedback_actions[:3]
        )
        return {
            "title": f"{mission.title}: personal execution system",
            "rationale": rationale,
            "phases": phases,
            "risks": self._risks(constraints, documents, feedback_actions),
            "success_criteria": [
                "A reviewable project result is linked to the Mission.",
                "At least one observable receipt and a three-minute reflection are recorded.",
            ],
            "evidence_gap_plan": gaps,
            "compilation_state": state,
            "confidence": 0.82 if personalized else (0.58 if context_grounded else 0.22),
            "knowledge_context_refs": document_refs,
            "comparison_key": comparison["key"],
            "comparison_context": comparison["context"],
            "personal_context_fingerprint": comparison["fingerprint"],
            "personalization_basis": self._personalization_basis(
                profile, diagnosis_context, documents, verified_capabilities, verified_experiences, feedback_actions
            ),
            "execution_contract": {
                "side_effect_boundary": "This plan does not authorize external side effects; DBOS Mission confirmation and capability authorization remain required.",
                "reflection_entry": "After the first observable receipt, record what changed, what blocked progress, and what should change next time.",
                "promotion_gate": "A capability or Strategy Genome requires three comparable, complete, accepted outcomes and the configured quality gate.",
            },
            "compiler_metadata": {
                "mode": "contextual_deterministic",
                "context_availability": str(knowledge_context.get("availability") or "unavailable"),
                "document_paths": [str(item.get("path") or "") for item in documents],
                "task_kind": kind,
                "diagnosis_context": diagnosis_context,
                "operational_state": operational_state,
            },
        }

    @staticmethod
    def _matching_strategy_assets(
        strategies: list[SOPVersionArtifact],
        *,
        comparison_key: str,
        comparison_context: str,
    ) -> list[dict[str, Any]]:
        """Expose only active, exact-context Strategy Genomes to a new plan."""
        assets: list[dict[str, Any]] = []
        for strategy in strategies:
            if not isinstance(strategy, SOPVersionArtifact) or strategy.status != ArtifactStatus.ACTIVE:
                continue
            genome = strategy.genome if isinstance(strategy.genome, dict) else {}
            if (
                str(genome.get("comparison_key") or "") != comparison_key
                or str(genome.get("comparison_context") or "") != comparison_context
            ):
                continue
            asset = {
                "artifact_id": str(strategy.artifact_id),
                "strategy_name": str(strategy.strategy_name or strategy.label or "Personal strategy")[:160],
                "version": int(strategy.version),
                "decision_rules": PBOSPlanCompiler._strategy_text_items(genome.get("decision_rules"), limit=2),
                "execution_paths": PBOSPlanCompiler._strategy_text_items(genome.get("execution_paths"), limit=2),
                "failure_boundaries": PBOSPlanCompiler._strategy_text_items(genome.get("failure_boundaries"), limit=2),
                "success_metrics": PBOSPlanCompiler._strategy_text_items(genome.get("success_metrics"), limit=2),
                "confidence": PBOSPlanCompiler._strategy_confidence(genome.get("confidence")),
            }
            if asset["artifact_id"] and asset["strategy_name"]:
                assets.append(asset)
        return assets[:3]

    @staticmethod
    def _strategy_text_items(value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = str(item).strip()[:320]
            if text and text not in items:
                items.append(text)
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _strategy_confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def _apply_strategy_assets(self, baseline: dict[str, Any], assets: list[dict[str, Any]]) -> None:
        """Bind prior verified strategies without letting them erase Mission context."""
        if not assets:
            baseline["strategy_refs"] = []
            return
        metadata = baseline.setdefault("compiler_metadata", {})
        metadata["active_strategy_assets"] = assets
        baseline["strategy_refs"] = [str(asset["artifact_id"]) for asset in assets]
        references = [
            f"{asset['strategy_name']} v{asset['version']} ({asset['artifact_id']})"
            for asset in assets
        ]
        baseline.setdefault("rationale", []).append(
            f"Verified Strategy Genome in this comparable context: {', '.join(references)}"
        )
        basis = baseline.setdefault("personalization_basis", [])
        basis.append({
            "kind": "verified_strategy_genome",
            "signals": {"refs": baseline["strategy_refs"], "names": references},
            "state": "verified",
        })
        # A matching promoted strategy is evidence-backed personal history. It
        # can personalize a plan only after profile and governed context are
        # also present; it never turns an evidence-poor plan into a claim.
        if baseline.get("compilation_state") == "context_grounded":
            baseline["compilation_state"] = "personalized"
            baseline["confidence"] = max(float(baseline.get("confidence") or 0), 0.82)
        contract = baseline.setdefault("execution_contract", {})
        contract["strategy_application"] = {
            "strategy_refs": list(baseline["strategy_refs"]),
            "scope": "exact comparison_key and comparison_context match required",
            "rollback_boundary": "Preserve the Strategy Genome failure boundaries during execution review.",
        }
        self._ensure_strategy_guidance(baseline)

    @staticmethod
    def _ensure_strategy_guidance(plan: dict[str, Any]) -> dict[str, Any]:
        """Prevent an LLM wording pass from silently dropping verified strategy use."""
        metadata = plan.get("compiler_metadata")
        assets = metadata.get("active_strategy_assets") if isinstance(metadata, dict) else None
        if not isinstance(assets, list) or not assets:
            return plan
        first = next((item for item in assets if isinstance(item, dict)), None)
        phases = plan.get("phases")
        if not isinstance(first, dict) or not isinstance(phases, list) or not phases:
            return plan
        strategy_name = str(first.get("strategy_name") or "Personal strategy")[:160]
        version = str(first.get("version") or "1")[:20]
        reference = str(first.get("artifact_id") or "")[:160]
        rules = [str(item).strip() for item in first.get("decision_rules") or [] if str(item).strip()]
        boundaries = [str(item).strip() for item in first.get("failure_boundaries") or [] if str(item).strip()]
        phase = phases[0] if isinstance(phases[0], dict) else None
        if phase is None:
            return plan
        strategy_input = f"Verified Strategy Genome: {strategy_name} v{version} ({reference})"
        inputs = [strategy_input, *[str(item).strip() for item in phase.get("inputs") or [] if str(item).strip()]]
        phase["inputs"] = list(dict.fromkeys(inputs))[:6]
        if rules:
            strategy_action = f"Apply verified strategy decision rule: {rules[0]}"
            actions = [strategy_action, *[str(item).strip() for item in phase.get("actions") or [] if str(item).strip()]]
            phase["actions"] = list(dict.fromkeys(actions))[:2]
        if boundaries:
            checks = [*[str(item).strip() for item in phase.get("checks") or [] if str(item).strip()], f"Respect strategy failure boundary: {boundaries[0]}"]
            phase["checks"] = list(dict.fromkeys(checks))[:6]
        return plan

    @staticmethod
    def _personalization_basis(
        profile: PersonalProfileArtifact | None,
        diagnosis: dict[str, Any],
        documents: list[dict[str, Any]],
        capabilities: list[str],
        experiences: list[str],
        feedback: list[str],
    ) -> list[dict[str, Any]]:
        """Make every personal-plan claim inspectable without inventing history."""
        basis: list[dict[str, Any]] = []
        if profile:
            basis.append({
                "kind": "declared_profile",
                "signals": {"focus": profile.focus[:6], "constraints": profile.constraints[:6], "resources": profile.resources[:6]},
                "state": "declared",
            })
        if diagnosis:
            basis.append({
                "kind": "mission_diagnosis",
                "signals": {key: diagnosis.get(key) for key in ("role", "industry", "organization_stage", "goal") if diagnosis.get(key)},
                "state": "governed",
            })
        if documents:
            basis.append({
                "kind": "governed_vault_context",
                "signals": {"refs": [str(item.get("ref") or item.get("path") or "") for item in documents[:4]]},
                "state": "governed",
            })
        if capabilities or experiences:
            basis.append({
                "kind": "verified_personal_assets",
                "signals": {"capabilities": capabilities[:6], "experiences": experiences[:4]},
                "state": "verified",
            })
        if feedback:
            basis.append({"kind": "prior_feedback", "signals": {"items": feedback[:3]}, "state": "unverified_direction"})
        return basis

    @staticmethod
    def _add_phase_contracts(
        phases: list[dict[str, Any]],
        mission: MissionArtifact,
        document_titles: list[str],
        constraints: list[str],
        comparison_context: str,
    ) -> None:
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        objective = str(mission_context.get("goal") or mission.intent or mission.title).strip()[:320]
        boundary = document_titles[0] if document_titles else "declared Mission context"
        constraint = constraints[0] if constraints else "declared scope"
        decisions = [
            ("Is the problem boundary and success signal explicit?", "Proceed when facts, owner, and metric are explicit.", "Capture the missing fact instead of expanding scope."),
            ("Does this slice prove the Mission under the declared constraint?", "Proceed when one observable loop fits the boundary.", "Reduce the slice or reject an unsupported dependency."),
            ("Is the result sufficient to learn from?", "Proceed when a receipt and reflection are linked to the outcome.", "Keep the result unverified and schedule the next evidence capture."),
        ]
        for index, phase in enumerate(phases):
            question, proceed, adapt = decisions[min(index, len(decisions) - 1)]
            phase.setdefault("why_now", f"This phase advances {objective} without widening beyond {constraint}.")
            phase.setdefault("inputs", [f"Mission objective: {objective}", f"Comparison context: {comparison_context}", f"Governed boundary: {boundary}"])
            phase.setdefault("outputs", [str(item) for item in phase.get("checks", [])[:2]] or ["A reviewable phase receipt"])
            phase.setdefault("decision_point", {"question": question, "proceed_when": proceed, "adapt_when": adapt})

    @staticmethod
    def _diagnosis_context(diagnosis: DiagnosisArtifact | None) -> dict[str, Any]:
        if diagnosis is None:
            return {}
        return {
            "role": diagnosis.role,
            "industry": diagnosis.industry,
            "organization_stage": diagnosis.organization_stage,
            "goal": diagnosis.goal,
            "constraints": diagnosis.constraints,
            "success_metrics": diagnosis.success_metrics,
        }

    @staticmethod
    def _comparison_identity(
        mission: MissionArtifact,
        diagnosis: dict[str, Any],
        profile: PersonalProfileArtifact | None,
        task_kind: str,
    ) -> dict[str, str]:
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        explicit_key = str(mission_context.get("comparison_key") or "").strip()
        key_parts = [
            task_kind,
            str(diagnosis.get("role") or "").strip(),
            str(diagnosis.get("industry") or "").strip(),
            str(diagnosis.get("organization_stage") or "").strip(),
        ]
        key = explicit_key or ":".join(part.lower().replace(" ", "-") for part in key_parts if part) or "personal_ai_project_delivery"
        explicit_context = str(mission_context.get("comparison_context") or "").strip()
        context_parts = [
            explicit_context,
            str(diagnosis.get("role") or "").strip(),
            str(diagnosis.get("industry") or "").strip(),
            str(diagnosis.get("organization_stage") or "").strip(),
        ]
        context = " / ".join(part for part in context_parts if part) or task_kind
        fingerprint_payload = {
            "key": key,
            "context": context,
            "focus": profile.focus if profile else [],
            "constraints": profile.constraints if profile else [],
            "preferences": profile.preferences if profile else {},
            "mission_constraints": mission_context.get("constraints") or [],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        return {"key": key[:160], "context": context[:300], "fingerprint": fingerprint}

    @staticmethod
    def _task_kind(text: str) -> str:
        if any(signal in text for signal in (
            "wiki", "obsidian", "horizon", "prd", "sop",
            "\u77e5\u8bc6\u5e93", "\u9700\u6c42\u6587\u6863", "\u6d41\u7a0b",
        )):
            return "knowledge_delivery"
        if any(signal in text for signal in ("content", "growth", "retention", "audience", "运营", "增长", "内容", "账号")):
            return "growth"
        if any(signal in text for signal in ("agent", "runtime", "api", "artifact", "code", "system", "engineering", "开发", "工程", "架构")):
            return "engineering"
        return "delivery"

    @staticmethod
    def _context_source_references(documents: list[dict[str, Any]], limit: int = 3) -> list[str]:
        """Expose traceable source labels without persisting Vault excerpts in a plan."""
        references: list[str] = []
        for document in documents[:limit]:
            ref = str(document.get("ref") or document.get("path") or "project context")
            title = str(document.get("title") or document.get("path") or "governed project context")
            references.append(f"{title[:200]} ({ref})")
        return references

    @staticmethod
    def _phases(
        kind: str,
        mission: MissionArtifact,
        source_references: list[str],
        constraints: list[str],
    ) -> list[dict[str, Any]]:
        context_note = source_references[0] if source_references else "the declared Mission context"
        limit = constraints[0] if constraints else "the declared scope"
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        objective = str(mission_context.get("goal") or mission.intent).strip()[:320]
        boundary = f"Review {context_note} and record only the task-relevant evidence."
        if kind == "knowledge_delivery":
            return [
                {
                    "title": "Evidence triage and boundary",
                    "actions": [
                        f"Separate verified sources, open gaps, and decision owners for: {objective}",
                        f"Use {boundary}",
                    ],
                    "checks": ["Every proposed knowledge change has a source reference or an explicit gap"],
                },
                {
                    "title": "Context pack and custom SOP",
                    "actions": [
                        "Build one PRD-specific context pack from cited Wiki pages and approved weekly distillation.",
                        f"Compile one reviewable SOP inside {limit} without promoting a template as a method.",
                    ],
                    "checks": ["The SOP names its project boundary, evidence inputs, and approval gate"],
                },
                {
                    "title": "Delivery review and feedback",
                    "actions": [
                        "Capture one observable delivery receipt and distinguish outcome evidence from model suggestions.",
                        "Route accepted results back for review; keep unaccepted results as candidates.",
                    ],
                    "checks": ["Mission, plan, receipt, and feedback remain traceable in one lineage"],
                },
            ]
        if kind == "growth":
            return [
                {"title": "Audience and signal diagnosis", "actions": [f"Define the measurable audience change required for: {objective}", f"Ground the hypothesis in: {boundary}"], "checks": ["Audience and baseline metric are explicit"]},
                {"title": "Smallest content experiment", "actions": ["Create one contrastive hook and one alternative opening tied to the named audience behavior.", f"Keep the experiment inside {limit}."], "checks": ["Variants share one success metric"]},
                {"title": "Measurement and learning", "actions": ["Record retention, response, and production cost against the declared hypothesis.", "Keep the winning and failing pattern separate in the reflection."], "checks": ["Outcome includes evidence and a next experiment"]},
            ]
        if kind == "engineering":
            is_pbos = "pbos" in f"{mission.title} {mission.intent}".lower()
            if is_pbos:
                return [
                    {"title": "Personal loop boundary decision", "actions": [f"Turn this objective into one acceptance card: {objective}", boundary], "checks": ["Obsidian input, Artifact Graph record, Cockpit readback, and Vault projection each have an observable owner and failure path"]},
                    {"title": "One evidence-backed PBOS slice", "actions": ["Compile one Mission into a Personal Execution Plan from governed Vault references only.", f"Keep raw capture, unverified feedback, and external connectors outside the accepted-result claim; stay within {limit}."], "checks": ["The current Cockpit plan exposes context references and an explicit evidence-gap state"]},
                    {"title": "Runtime receipt and reflection", "actions": ["Capture focused test and live API receipts for the same plan lineage.", "Record the observed result and blocker as unverified feedback; do not promote a capability or strategy yet."], "checks": ["A reviewer can trace Mission -> Plan -> Execution -> Outcome -> Feedback without a narrative-only assertion"]},
                ]
            return [
                {"title": "Architecture and boundary gate", "actions": [f"Turn the current objective into an acceptance card: {objective}", f"Apply this governed boundary before changing the contract: {boundary}"], "checks": ["Contract has an owner, input, output, and failure path"]},
                {"title": "Smallest executable loop", "actions": ["Implement one end-to-end path with real persistence and a readback.", f"Do not widen beyond {limit} until the loop is observable."], "checks": ["One integration test proves the loop"]},
                {"title": "Operational proof and reflection", "actions": ["Run the real service path and capture its receipt.", "Record what changed, what failed, and the next boundary decision."], "checks": ["Result can be reviewed without relying on a narrative claim"]},
            ]
        return [
            {"title": "Situation diagnosis", "actions": [f"Separate facts, constraints, and unknowns for: {objective}", f"Use this governed project signal: {boundary}"], "checks": ["Decision owner and evidence gap are explicit"]},
            {"title": "Bounded execution", "actions": [f"Run the smallest action allowed by {limit}.", "Capture an observable result instead of a completion assertion."], "checks": ["Output and success measure are reviewable"]},
            {"title": "Reflection and reuse decision", "actions": ["Record the outcome, failure modes, and next action.", "Only propose a reusable method when comparable evidence exists."], "checks": ["Reflection differentiates evidence from inference"]},
        ]

    @staticmethod
    def _risks(constraints: list[str], documents: list[dict[str, Any]], feedback: list[str]) -> list[str]:
        values = ["Treat unverified feedback as a direction, not evidence."]
        if not documents:
            values.append("No governed Vault context was available; personalization is limited.")
        if constraints:
            values.append(f"Declared constraint may block the plan: {constraints[0]}")
        if feedback:
            values.append("Prior feedback remains unresolved until the new result corroborates it.")
        return values

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Return one JSON object only. Personalize three execution phases from the facts supplied. "
            "Never invent facts, skills, outcomes, preferences, or citations. Never copy Vault excerpts; use supplied refs only. "
            "This is a planning delta: the platform preserves inputs, outputs, checks, authority boundaries, and evidence references. "
            "Schema exactly: {title:string, phases:[{title:string, actions:[string]}, "
            "{title:string, actions:[string]}, {title:string, actions:[string]}]}. "
            "Return exactly three phases, no other keys, at most two actions per phase. "
            "Keep every title under 12 words and every action under 18 words. "
            "Make phases specific to the mission, constraints, profile, and governed context; never write a generic SOP. "
            "Use active_strategy_genomes only when supplied: preserve their decision rule and failure boundary in the plan, and never invent a strategy reference. "
            "Use response_language for user-facing titles and actions. "
            "When operational_state says managed_source_mirror is available, never recommend BSC-to-Obsidian source sync, import, mirroring, or projection. "
            "When a named plugin_bridges route is configured_awaiting_export or configured_awaiting_output, never install, configure, or reconfigure that named Obsidian bridge; it awaits a real user export. "
            "In either case phase one must advance a Mission-specific decision, metric, experiment, or delivery."
        )

    @classmethod
    def _prompt_payload(
        cls,
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact | None,
        profile: PersonalProfileArtifact | None,
        capabilities: list[CapabilityArtifact],
        experiences: list[ExperienceArtifact],
        strategy_assets: list[dict[str, Any]],
        feedback: list[dict[str, str]],
        knowledge_context: dict[str, Any],
    ) -> dict[str, Any]:
        document_limit = max(1, min(int(settings.PBOS_LLM_MAX_CONTEXT_DOCUMENTS), 8))
        excerpt_limit = max(64, min(int(settings.PBOS_LLM_CONTEXT_DOCUMENT_MAX_TOKENS), 600))
        documents = [item for item in knowledge_context.get("documents", []) if isinstance(item, dict)]
        profile_payload = None
        if profile:
            profile_payload = {
                "focus": [cls._bounded_prompt_text(item, 80) for item in profile.focus[:6]],
                "goals": [cls._bounded_prompt_text(item, 80) for item in profile.goals[:6]],
                "preferences": {
                    cls._bounded_prompt_text(key, 40): cls._bounded_prompt_text(value, 80)
                    for key, value in list(profile.preferences.items())[:6]
                },
                "resources": [cls._bounded_prompt_text(item, 80) for item in profile.resources[:6]],
                "constraints": [cls._bounded_prompt_text(item, 80) for item in profile.constraints[:6]],
            }
        return {
            "response_language": "Chinese" if cls._uses_chinese(mission.title, mission.intent) else "Match the Mission's primary language",
            "mission": {
                "title": cls._bounded_prompt_text(mission.title, 100),
                "intent": cls._bounded_prompt_text(mission.intent, 160),
                "context": cls._bounded_prompt_text(json.dumps(mission.context, ensure_ascii=False, sort_keys=True), 320),
            },
            "diagnosis": {
                key: cls._bounded_prompt_text(value, 100)
                for key, value in cls._diagnosis_context(diagnosis).items()
                if value not in (None, "", [], {})
            },
            "personal_profile": profile_payload,
            "verified_capabilities": [
                {
                    "name": cls._bounded_prompt_text(item.name, 80),
                    "type": cls._bounded_prompt_text(item.capability_type, 40),
                    "level": item.level,
                    "evidence_count": item.evidence_count,
                }
                for item in capabilities if item.evidence_count > 0
            ][:6],
            "verified_experiences": [
                {
                    "statement": cls._bounded_prompt_text(item.statement, 100),
                    "applicability": [cls._bounded_prompt_text(value, 50) for value in item.applicability[:4]],
                    "verification_state": cls._bounded_prompt_text(item.verification_state, 40),
                }
                for item in experiences
            ][:4],
            "active_strategy_genomes": [
                {
                    "artifact_id": cls._bounded_prompt_text(item.get("artifact_id"), 80),
                    "strategy_name": cls._bounded_prompt_text(item.get("strategy_name"), 80),
                    "version": item.get("version"),
                    "decision_rules": [cls._bounded_prompt_text(value, 80) for value in item.get("decision_rules") or []],
                    "execution_paths": [cls._bounded_prompt_text(value, 80) for value in item.get("execution_paths") or []],
                    "failure_boundaries": [cls._bounded_prompt_text(value, 80) for value in item.get("failure_boundaries") or []],
                    "success_metrics": [cls._bounded_prompt_text(value, 80) for value in item.get("success_metrics") or []],
                    "confidence": item.get("confidence"),
                }
                for item in strategy_assets[:3] if isinstance(item, dict)
            ],
            "feedback": [
                {
                    "source": cls._bounded_prompt_text(item.get("source", ""), 40),
                    "statement": cls._bounded_prompt_text(item.get("statement", ""), 100),
                }
                for item in feedback[:3] if isinstance(item, dict)
            ],
            "operational_state": cls._safe_operational_state(knowledge_context),
            "vault_context": [
                {
                    "ref": cls._bounded_prompt_text(item.get("ref"), 80),
                    "title": cls._bounded_prompt_text(item.get("title"), 80),
                    "path": cls._bounded_prompt_text(item.get("path"), 100),
                    "excerpt": cls._bounded_prompt_text(item.get("excerpt"), excerpt_limit),
                }
                for item in documents[:document_limit]
            ],
        }

    @staticmethod
    def _bounded_prompt_text(value: Any, max_tokens: int) -> str:
        return truncate_prompt_text(str(value or ""), max(1, max_tokens))

    @staticmethod
    def _normalize(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        title = str(value.get("title") or "").strip()[:300]
        phases_raw = value.get("phases")
        if not title or not isinstance(phases_raw, list) or len(phases_raw) != 3:
            return None
        phases: list[dict[str, Any]] = []
        for item in phases_raw:
            if not isinstance(item, dict):
                return None
            phase_title = str(item.get("title") or "").strip()[:200]
            why_now = str(item.get("why_now") or "").strip()[:600]
            actions = [str(entry).strip()[:500] for entry in item.get("actions", []) if str(entry).strip()][:2]
            checks = [str(entry).strip()[:500] for entry in item.get("checks", []) if str(entry).strip()][:6]
            inputs = [str(entry).strip()[:500] for entry in item.get("inputs", []) if str(entry).strip()][:6]
            outputs = [str(entry).strip()[:500] for entry in item.get("outputs", []) if str(entry).strip()][:6]
            raw_decision = item.get("decision_point")
            decision_point = {
                key: str(raw_decision.get(key) or "").strip()[:500]
                for key in ("question", "proceed_when", "adapt_when")
            } if isinstance(raw_decision, dict) else {}
            if not phase_title or not actions:
                return None
            phases.append({
                "title": phase_title,
                "why_now": why_now,
                "inputs": inputs,
                "actions": actions,
                "outputs": outputs,
                "checks": checks,
                "decision_point": {key: value for key, value in decision_point.items() if value},
            })
        if len(phases) != 3:
            return None
        return {
            "title": title,
            "rationale": [str(item).strip()[:600] for item in value.get("rationale", []) if str(item).strip()][:8],
            "phases": phases,
            "risks": [str(item).strip()[:500] for item in value.get("risks", []) if str(item).strip()][:8],
            "success_criteria": [str(item).strip()[:500] for item in value.get("success_criteria", []) if str(item).strip()][:8],
            "evidence_gap_plan": [str(item).strip()[:500] for item in value.get("evidence_gap_plan", []) if str(item).strip()][:8],
        }
