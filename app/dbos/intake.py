"""Governed, deterministic project-intake state for DBOS."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.artifacts import ArtifactGraphStore, ArtifactStatus, ArtifactType, IntakeAnswerRevisionArtifact, IntakeSessionArtifact
from app.core.config import settings


class IntakeError(ValueError):
    """Base error for invalid governed-intake transitions."""


class IntakeDisabledError(IntakeError):
    """Raised when the feature flag intentionally disables intake writes."""


class IntakeService:
    """Persist bounded questions without treating model output as state."""

    QUALIFYING_FIELDS = ("role", "goal")
    COMPLETION_FIELDS = {
        "product_build": ("industry", "organization_stage", "success_metrics"),
        "automation": ("industry", "constraints", "success_metrics"),
        "data_analysis": ("industry", "success_metrics", "constraints"),
        "career": ("organization_stage", "stakeholders", "time_horizon"),
        "business": ("industry", "organization_stage", "constraints"),
    }
    QUESTION_COPY = {
        "role": ("Who owns the outcome?", ["Founder or owner", "Product or operations lead", "Individual contributor", "Other"]),
        "goal": ("What must be true when this work succeeds?", ["A usable first version exists", "A measurable business result improves", "A decision is ready for review", "Other"]),
        "industry": ("Which operating context is closest?", ["Software or AI", "Services or consulting", "Commerce or retail", "Other"]),
        "organization_stage": ("What is the current stage?", ["Exploring", "First delivery", "Growth", "Other"]),
        "success_metrics": ("How will you judge the result?", ["Adoption or delivery", "Revenue or conversion", "Decision quality", "Other"]),
        "constraints": ("Which constraint is most binding?", ["Time", "Budget", "Decision authority", "Other"]),
        "stakeholders": ("Who must review or approve the work?", ["One owner", "Cross-functional team", "External client", "Other"]),
        "time_horizon": ("What is the working time horizon?", ["This week", "This month", "This quarter", "Other"]),
        "primary_risk": ("What would make this plan fail even if the work is completed?", ["No evidence", "No decision owner", "Too much scope", "Other"]),
    }

    def __init__(self, store: ArtifactGraphStore) -> None:
        self.store = store

    def create_session(
        self,
        project_id: str,
        request_text: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> IntakeSessionArtifact:
        self._ensure_enabled()
        request_text = request_text.strip()
        if not project_id.strip() or not request_text:
            raise IntakeError("project_id and request_text are required")
        classification, confidence, rationale, domain = self.classify(request_text)
        phase = {
            "build": "clarifying",
            "direct": "ready_for_review",
            "help": "exited",
            "uncertain": "classified",
        }[classification]
        initial_context = self._clean_context(context or {})
        session = IntakeSessionArtifact(
            project_id=project_id,
            label=f"Intake: {request_text[:100]}",
            original_request=request_text,
            classification=classification,
            classification_confidence=confidence,
            classification_rationale=rationale,
            domain=domain,
            phase=phase,
            initial_context=initial_context,
            declared_context=dict(initial_context),
            source_agent="dbos_blindspot_intake",
            tags=["dbos", "blindspot_intake", classification, domain],
        )
        session.session_id = session.artifact_id
        if classification == "direct":
            session.unresolved_fields = self._missing_expected_fields(session)
            session.classification_rationale.append("direct path preserves unanswered context as explicit gaps")
        self.store.add(session)
        return session

    @classmethod
    def classify(cls, request_text: str) -> tuple[str, float, list[str], str]:
        text = request_text.lower().strip()
        direct_signals = ("direct execution", "skip questions", "just do it", "别问", "直接执行", "直接做", "直接开始")
        help_signals = ("what is", "explain", "why", "帮我看看", "是什么意思", "怎么回事", "为什么")
        build_signals = ("build", "create", "website", "app", "automation", "workflow", "data analysis", "搭建", "做一个", "网站", "应用", "自动化", "数据分析")
        direct_matches = [signal for signal in direct_signals if signal in text]
        help_matches = [signal for signal in help_signals if signal in text]
        build_matches = [signal for signal in build_signals if signal in text]
        domain = cls._domain(text)
        if direct_matches:
            return "direct", 0.98, [f"explicit direct signal: {direct_matches[0]}"], domain
        explicit_help_markers = (
            "what is",
            "explain",
            "why",
            "\u662f\u4ec0\u4e48\u610f\u601d",
            "\u5e2e\u6211\u770b\u770b",
            "\u600e\u4e48\u56de\u4e8b",
            "\u4e3a\u4ec0\u4e48",
        )
        if any(marker in text for marker in explicit_help_markers):
            return "help", 0.9, ["explicit explanation request"], domain
        if build_matches and not help_matches:
            return "build", min(0.95, 0.72 + len(build_matches) * 0.08), [f"build signal: {build_matches[0]}"], domain
        if help_matches and not build_matches:
            return "help", min(0.95, 0.75 + len(help_matches) * 0.08), [f"help signal: {help_matches[0]}"], domain
        if build_matches and help_matches:
            return "uncertain", 0.45, ["build and help signals conflict"], domain
        return "uncertain", 0.2, ["no reliable build, direct, or help signal"], domain

    @staticmethod
    def _domain(text: str) -> str:
        # Specific analytic work must win over its generic workflow wording.
        if any(token in text for token in ("data analysis", "dataset")):
            return "data_analysis"
        if "portal" in text:
            return "product_build"
        if any(token in text for token in ("career", "interview", "job search", "职业", "求职", "面试")):
            return "career"
        if any(token in text for token in ("automation", "workflow", "script", "自动化", "脚本", "工作流")):
            return "automation"
        if any(token in text for token in ("data analysis", "dataset", "数据分析", "数据集")):
            return "data_analysis"
        if any(token in text for token in ("website", "app", "product", "site", "网站", "应用", "产品", "搭建")):
            return "product_build"
        return "business"

    def get_session(self, session_id: str) -> IntakeSessionArtifact:
        item = self.store.get(session_id)
        if not isinstance(item, IntakeSessionArtifact):
            raise IntakeError("intake session not found")
        return item

    def resolve_uncertain(self, session_id: str, action: str) -> IntakeSessionArtifact:
        self._ensure_enabled()
        session = self.get_session(session_id)
        if session.classification != "uncertain" or session.phase != "classified":
            raise IntakeError("session does not require an uncertainty choice")
        mapping = {
            "clarify": ("build", "clarifying"),
            "direct": ("direct", "ready_for_review"),
            "help": ("help", "exited"),
        }
        if action not in mapping:
            raise IntakeError("action must be clarify, direct, or help")
        classification, phase = mapping[action]
        session.classification = classification
        session.phase = phase
        if classification == "direct":
            session.active_question = {}
            session.unresolved_fields = self._missing_expected_fields(session)
        session.classification_rationale.append(f"user resolved uncertainty: {action}")
        self.store.update(session)
        return session

    def next_question(self, session_id: str) -> dict[str, Any] | None:
        self._ensure_enabled()
        session = self.get_session(session_id)
        if session.phase != "clarifying":
            return None
        if session.active_question:
            return dict(session.active_question)
        answered_fields = self._known_fields(session)
        candidate = self._next_candidate(session, answered_fields)
        if candidate is None:
            session.phase = "ready_for_review"
            self.store.update(session)
            return None
        phase, field = candidate
        prompt, options = self.QUESTION_COPY[field]
        question = {
            "question_id": f"{phase}-{field}",
            "phase": phase,
            "field": field,
            "prompt": prompt,
            "options": [{"label": option, "value": option} for option in options],
        }
        session.active_question = question
        self.store.update(session)
        return question

    def answer(self, session_id: str, question_id: str, answer: str = "", *, skipped: bool = False) -> IntakeSessionArtifact:
        self._ensure_enabled()
        session = self.get_session(session_id)
        question = session.active_question
        if session.phase != "clarifying" or not question or question.get("question_id") != question_id:
            raise IntakeError("question is not active for this session")
        if not skipped and not answer.strip():
            raise IntakeError("answer is required unless the question is skipped")
        revision = IntakeAnswerRevisionArtifact(
            project_id=session.project_id,
            label=f"Intake answer: {question.get('field')}",
            session_id=session.artifact_id,
            question_id=question_id,
            question_field=str(question.get("field") or ""),
            question_phase=str(question.get("phase") or ""),
            answer=answer.strip(),
            skipped=skipped,
            context_updates=self._context_updates(str(question.get("field") or ""), answer.strip(), skipped),
            revision_ordinal=len(self._all_revisions(session)) + 1,
            parent_ids=[session.artifact_id],
            source_agent="dbos_blindspot_intake",
            tags=["dbos", "blindspot_intake", str(question.get("phase") or "")],
        )
        self.store.add(revision)
        session.active_question = {}
        self._recalculate(session)
        self.store.update(session)
        return session

    def revert(self, session_id: str, revision_id: str) -> IntakeSessionArtifact:
        self._ensure_enabled()
        session = self.get_session(session_id)
        if session.phase == "converted":
            raise IntakeError("converted intake answers are immutable; create a new intake revision")
        revision = self.store.get(revision_id)
        if not isinstance(revision, IntakeAnswerRevisionArtifact) or revision.session_id != session.artifact_id:
            raise IntakeError("answer revision not found for this session")
        if revision.status == ArtifactStatus.SUPERSEDED:
            return session
        revision.status = ArtifactStatus.SUPERSEDED
        self.store.update(revision)
        session.active_question = {}
        session.phase = "clarifying"
        self._recalculate(session)
        self.store.update(session)
        return session

    def select_tier(self, session_id: str, tier: str) -> IntakeSessionArtifact:
        self._ensure_enabled()
        session = self.get_session(session_id)
        normalized = tier.strip().lower()
        if normalized not in {"lite", "standard", "full"}:
            raise IntakeError("tier must be lite, standard, or full")
        if session.phase not in {"ready_for_review", "converted"}:
            raise IntakeError("tier selection requires a reviewable session")
        session.tier = normalized
        self.store.update(session)
        return session

    def direct_to_review(self, session_id: str) -> IntakeSessionArtifact:
        """End optional questioning while preserving all remaining unknowns."""
        self._ensure_enabled()
        session = self.get_session(session_id)
        if session.phase in {"converted", "exited", "cancelled"}:
            raise IntakeError("intake cannot enter direct review in its current phase")
        if session.phase == "classified":
            raise IntakeError("resolve the uncertainty choice before entering direct review")
        session.active_question = {}
        session.unresolved_fields = list(dict.fromkeys([
            *session.unresolved_fields,
            *self._missing_expected_fields(session),
        ]))
        session.phase = "ready_for_review"
        session.classification_rationale.append("user bypassed remaining intake questions")
        self.store.update(session)
        return session

    def list_revisions(self, session_id: str) -> list[IntakeAnswerRevisionArtifact]:
        session = self.get_session(session_id)
        return self._all_revisions(session)

    def _next_candidate(self, session: IntakeSessionArtifact, answered_fields: set[str]) -> tuple[str, str] | None:
        if session.qualifying_question_count < 2:
            for field in self.QUALIFYING_FIELDS:
                if field not in answered_fields:
                    return "qualify", field
        if session.completion_question_count < 3:
            for field in self.COMPLETION_FIELDS[session.domain]:
                if field not in answered_fields:
                    return "complete", field
        if session.probe_question_count < 1 and "primary_risk" not in answered_fields:
            return "probe", "primary_risk"
        return None

    def _recalculate(self, session: IntakeSessionArtifact) -> None:
        revisions = self._active_revisions(session)
        context = dict(session.initial_context)
        unresolved: list[str] = []
        for revision in revisions:
            if revision.skipped:
                unresolved.append(revision.question_field)
            else:
                context = self._merge_context(context, revision.context_updates)
        session.declared_context = context
        session.unresolved_fields = list(dict.fromkeys(unresolved))
        session.qualifying_question_count = sum(item.question_phase == "qualify" for item in revisions)
        session.completion_question_count = sum(item.question_phase == "complete" for item in revisions)
        session.probe_question_count = sum(item.question_phase == "probe" for item in revisions)
        if session.classification == "build" and self._next_candidate(session, self._known_fields(session)) is None:
            session.phase = "ready_for_review"

    def _known_fields(self, session: IntakeSessionArtifact) -> set[str]:
        return {
            *session.initial_context.keys(),
            *(item.question_field for item in self._active_revisions(session)),
        }

    def _missing_expected_fields(self, session: IntakeSessionArtifact) -> list[str]:
        expected = [*self.QUALIFYING_FIELDS, *self.COMPLETION_FIELDS[session.domain], "primary_risk"]
        return [field for field in expected if field not in self._known_fields(session)]

    def _active_revisions(self, session: IntakeSessionArtifact) -> list[IntakeAnswerRevisionArtifact]:
        return [
            item for item in self._all_revisions(session)
            if item.status != ArtifactStatus.SUPERSEDED
        ]

    def _all_revisions(self, session: IntakeSessionArtifact) -> list[IntakeAnswerRevisionArtifact]:
        items = [
            item for item in self.store.get_by_type(ArtifactType.INTAKE_ANSWER_REVISION)
            if isinstance(item, IntakeAnswerRevisionArtifact) and item.session_id == session.artifact_id
        ]
        return sorted(items, key=lambda item: (item.revision_ordinal, item.created_at, item.artifact_id))

    @staticmethod
    def _context_updates(field: str, answer: str, skipped: bool) -> dict[str, Any]:
        if skipped:
            return {}
        if field in {"constraints", "stakeholders", "success_metrics"}:
            return {field: [answer]}
        if field == "primary_risk":
            return {"constraints": [f"Blindspot risk: {answer}"]}
        return {field: answer}

    @classmethod
    def _merge_context(cls, current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        for field, value in updates.items():
            if isinstance(value, list):
                existing = merged.get(field)
                existing_items = existing if isinstance(existing, list) else ([existing] if existing else [])
                merged[field] = list(dict.fromkeys([*existing_items, *value]))
            else:
                merged[field] = value
        return merged

    @staticmethod
    def _clean_context(context: dict[str, Any]) -> dict[str, Any]:
        allowed = {"role", "industry", "organization_stage", "goal", "time_horizon", "constraints", "stakeholders", "decision_rights", "success_metrics", "evidence"}
        return {key: value for key, value in context.items() if key in allowed and value not in (None, "", [])}

    @staticmethod
    def _ensure_enabled() -> None:
        if not settings.DBOS_BLINDSPOT_INTAKE_ENABLED:
            raise IntakeDisabledError("governed blindspot intake is disabled")
