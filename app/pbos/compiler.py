"""Contextual Personal Execution Plan compiler with an auditable fallback."""

from __future__ import annotations

import json
import hashlib
from typing import Any

from app.artifacts import CapabilityArtifact, DiagnosisArtifact, ExperienceArtifact, MissionArtifact, PersonalProfileArtifact
from app.core.config import settings
from app.services.sop_llm_client import PROVIDER_KEY_MAP, SOPLLMClient


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
            return cls(SOPLLMClient(provider=provider, timeout=45.0))
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
        feedback: list[dict[str, str]],
        knowledge_context: dict[str, Any],
    ) -> dict[str, Any]:
        baseline = self._baseline(
            mission=mission,
            diagnosis=diagnosis,
            profile=profile,
            capabilities=capabilities,
            experiences=experiences,
            feedback=feedback,
            knowledge_context=knowledge_context,
        )
        if self.client is None:
            return baseline
        try:
            generated = self.client.chat_structured(
                system_prompt=self._system_prompt(),
                user_prompt=json.dumps(self._prompt_payload(
                    mission, diagnosis, profile, capabilities, experiences, feedback, knowledge_context
                ), ensure_ascii=False),
                temperature=0.2,
                max_tokens=2_600,
                max_structured_attempts=2,
            )
            normalized = self._normalize(generated)
        except Exception as exc:
            baseline["compiler_metadata"]["llm_failure"] = str(getattr(exc, "category", "request_failed"))
            self._record_llm_diagnostics(baseline)
            return baseline
        if normalized is None:
            baseline["compiler_metadata"]["llm_failure"] = str(
                getattr(self.client, "last_structured_failure", "structured_response_invalid")
            )
            self._record_llm_diagnostics(baseline)
            return baseline
        # The model may improve the execution wording, but cannot erase the
        # declared profile, evidence state, or governed-context traceability.
        for key in ("rationale", "risks", "success_criteria", "evidence_gap_plan"):
            baseline[key] = self._merge_text_items(baseline[key], normalized.get(key, []))
        baseline["title"] = normalized["title"]
        baseline["phases"] = normalized["phases"]
        baseline["compiler_metadata"] = {
            **baseline["compiler_metadata"],
            "mode": "llm_contextual",
            "provider": str(getattr(self.client, "provider", "configured")),
            "model": str(getattr(self.client, "model", "")),
        }
        return baseline

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
        document_refs = [str(item.get("ref") or "") for item in documents if item.get("ref")]
        document_titles = [str(item.get("title") or item.get("path") or "project context") for item in documents]
        context_signals = self._context_signals(documents)
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
        text = " ".join([
            mission.title, mission.intent, json.dumps(mission_context, ensure_ascii=False), " ".join(focus)
        ]).lower()
        kind = self._task_kind(text)
        comparison = self._comparison_identity(mission, diagnosis_context, profile, kind)
        phases = self._phases(kind, mission, document_titles, constraints, context_signals)
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
        rationale.extend(f"Governed context signal: {signal}" for signal in context_signals[:2])
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
            "compiler_metadata": {
                "mode": "contextual_deterministic",
                "context_availability": str(knowledge_context.get("availability") or "unavailable"),
                "document_paths": [str(item.get("path") or "") for item in documents],
                "task_kind": kind,
                "diagnosis_context": diagnosis_context,
            },
        }

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
        if any(signal in text for signal in ("content", "growth", "retention", "audience", "运营", "增长", "内容", "账号")):
            return "growth"
        if any(signal in text for signal in ("agent", "runtime", "api", "artifact", "code", "system", "engineering", "开发", "工程", "架构")):
            return "engineering"
        return "delivery"

    @staticmethod
    def _context_signals(documents: list[dict[str, Any]], limit: int = 3) -> list[str]:
        """Keep concrete Vault statements visible in deterministic fallback plans."""
        signals: list[str] = []
        for document in documents:
            ref = str(document.get("ref") or document.get("path") or "project context")
            for line in str(document.get("excerpt") or "").splitlines():
                value = line.strip().lstrip("- ").strip()
                if not value or value.startswith("#") or len(value) < 24:
                    continue
                signals.append(f"{ref}: {value[:260]}")
                break
            if len(signals) >= limit:
                break
        return signals

    @staticmethod
    def _phases(
        kind: str,
        mission: MissionArtifact,
        document_titles: list[str],
        constraints: list[str],
        context_signals: list[str],
    ) -> list[dict[str, Any]]:
        context_note = document_titles[0] if document_titles else "the declared Mission context"
        limit = constraints[0] if constraints else "the declared scope"
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        objective = str(mission_context.get("goal") or mission.intent).strip()[:320]
        boundary = context_signals[0] if context_signals else f"Use {context_note} as the reviewable project boundary."
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
                    {"title": "Personal loop boundary decision", "actions": [f"Turn this objective into one acceptance card: {objective}", f"Use the governed Vault boundary verbatim: {boundary}"], "checks": ["Obsidian input, Artifact Graph record, Cockpit readback, and Vault projection each have an observable owner and failure path"]},
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
            "You compile a Personal Execution Plan for one person. Return one JSON object only. "
            "Use only facts in the input. Do not invent skills, outcomes, user preferences, or citations. "
            "Do not write a generic SOP. Make phases specific to the mission, constraints, and supplied Vault context. "
            "Be concise: return exactly three phases, with at most three actions and two checks per phase. "
            "Schema: title(string), rationale(array of strings), phases(array of {title, actions, checks}), "
            "risks(array of strings), success_criteria(array of strings), evidence_gap_plan(array of strings)."
        )

    @staticmethod
    def _prompt_payload(
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact | None,
        profile: PersonalProfileArtifact | None,
        capabilities: list[CapabilityArtifact],
        experiences: list[ExperienceArtifact],
        feedback: list[dict[str, str]],
        knowledge_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mission": {"title": mission.title, "intent": mission.intent, "context": mission.context},
            "diagnosis": PBOSPlanCompiler._diagnosis_context(diagnosis),
            "personal_profile": profile.model_dump(mode="json") if profile else None,
            "verified_capabilities": [item.model_dump(mode="json") for item in capabilities if item.evidence_count > 0],
            "verified_experiences": [item.model_dump(mode="json") for item in experiences],
            "feedback": feedback,
            "vault_context": [
                {"ref": item.get("ref"), "title": item.get("title"), "path": item.get("path"), "excerpt": str(item.get("excerpt") or "")[:600]}
                for item in knowledge_context.get("documents", []) if isinstance(item, dict)
            ],
        }

    @staticmethod
    def _normalize(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        title = str(value.get("title") or "").strip()[:300]
        phases_raw = value.get("phases")
        if not title or not isinstance(phases_raw, list) or not phases_raw:
            return None
        phases: list[dict[str, list[str] | str]] = []
        for item in phases_raw[:5]:
            if not isinstance(item, dict):
                continue
            phase_title = str(item.get("title") or "").strip()[:200]
            actions = [str(entry).strip()[:500] for entry in item.get("actions", []) if str(entry).strip()][:8]
            checks = [str(entry).strip()[:500] for entry in item.get("checks", []) if str(entry).strip()][:6]
            if phase_title and actions:
                phases.append({"title": phase_title, "actions": actions, "checks": checks})
        if not phases:
            return None
        return {
            "title": title,
            "rationale": [str(item).strip()[:600] for item in value.get("rationale", []) if str(item).strip()][:8],
            "phases": phases,
            "risks": [str(item).strip()[:500] for item in value.get("risks", []) if str(item).strip()][:8],
            "success_criteria": [str(item).strip()[:500] for item in value.get("success_criteria", []) if str(item).strip()][:8],
            "evidence_gap_plan": [str(item).strip()[:500] for item in value.get("evidence_gap_plan", []) if str(item).strip()][:8],
        }
