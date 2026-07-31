"""Evidence-first PBOS lifecycle on top of the existing Artifact Graph."""

from __future__ import annotations

import inspect
import time
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Any

from app.artifacts import (
    ArtifactGraphStore, ArtifactStatus, ArtifactType, CapabilityArtifact,
    DiagnosisArtifact, ExperienceArtifact, PersonalExecutionPlanArtifact, PersonalProfileArtifact,
    MissionArtifact, SOPPromotionArtifact, SOPVersionArtifact, WorkExecutionRecordArtifact,
    WorkFeedbackArtifact, WorkOutcomeArtifact,
)
from app.core.config import settings
from .capture import local_receipts
from .compiler import PBOSPlanCompiler


class PBOSService:
    _BSC_WORKSPACE_PREFIXES = ("app/", "src/", "tests/", "docs/", "scripts/")
    _BSC_WORKSPACE_FILES = {
        "Dockerfile",
        "docker-compose.yml",
        "package-lock.json",
        "package.json",
        "requirements-production.txt",
        "requirements.txt",
    }

    def __init__(
        self,
        store: ArtifactGraphStore,
        project_id: str,
        *,
        context_provider=None,
        plan_compiler: PBOSPlanCompiler | None = None,
    ):
        self.store = store
        self.project_id = project_id
        self.context_provider = context_provider or (lambda: {"availability": "unavailable", "documents": [], "refs": []})
        self.plan_compiler = plan_compiler or PBOSPlanCompiler()

    def profile(self) -> PersonalProfileArtifact | None:
        items = self._latest(self.store.get_by_type(ArtifactType.PERSONAL_PROFILE))
        return next((item for item in items if isinstance(item, PersonalProfileArtifact)), None)

    @staticmethod
    def _latest(items: list[Any]) -> list[Any]:
        """Prefer the last persisted write over client-provided creation clocks."""
        return sorted(
            items,
            key=lambda item: (str(getattr(item, "updated_at", "")), str(getattr(item, "created_at", ""))),
            reverse=True,
        )

    def save_profile(self, payload: dict[str, Any]) -> PersonalProfileArtifact:
        previous = self.profile()
        artifact = PersonalProfileArtifact(project_id=self.project_id, parent_ids=[previous.artifact_id] if previous else [], **payload)
        self.store.add(artifact)
        return artifact

    def record_execution(self, mission_id: str, plan_id: str, payload: dict[str, Any]) -> WorkExecutionRecordArtifact:
        if not isinstance(self.store.get(mission_id), MissionArtifact):
            raise ValueError("PBOS execution requires an existing project Mission")
        if plan_id and not isinstance(self.store.get(plan_id), PersonalExecutionPlanArtifact):
            raise ValueError("PBOS execution requires an existing personal execution plan")
        artifact = WorkExecutionRecordArtifact(project_id=self.project_id, mission_id=mission_id, plan_id=plan_id, parent_ids=[plan_id] if plan_id else [], **payload)
        self.store.add(artifact)
        return artifact

    def record_manual_execution(self, mission_id: str, plan_id: str, payload: dict[str, Any]) -> WorkExecutionRecordArtifact:
        """Persist user-supplied notes without letting them self-certify receipts."""
        values = dict(payload)
        receipts = values.get("tool_receipts") or []
        values["tool_receipts"] = [
            {**dict(receipt), "verified": False}
            for receipt in receipts
            if isinstance(receipt, dict)
        ]
        return self.record_execution(mission_id, plan_id, values)

    def capture_local_execution(self, mission_id: str, plan_id: str, root: str, paths: list[str]) -> WorkExecutionRecordArtifact:
        return self.record_execution(mission_id, plan_id, {"actions": ["Captured local evidence"], "tool_receipts": local_receipts(root, paths)})

    def capture_bsc_workspace_execution(
        self,
        mission_id: str,
        plan_id: str,
        *,
        paths: list[str],
        actions: list[str] | None = None,
        reflection: dict[str, str] | None = None,
        observed_at: str = "",
        workspace_root: Path | str | None = None,
    ) -> WorkExecutionRecordArtifact:
        """Attach only declared, non-secret BSC workspace receipts to one execution."""
        root = Path(workspace_root).resolve() if workspace_root else self._bsc_workspace_root()
        selected_paths = self._safe_bsc_workspace_paths(paths)
        receipts = local_receipts(str(root), selected_paths)
        captured_paths = {
            str(receipt.get("path") or "")
            for receipt in receipts
            if str(receipt.get("kind") or "") == "local_file"
        }
        missing_paths = [path for path in selected_paths if path not in captured_paths]
        if missing_paths:
            raise ValueError("Selected BSC workspace evidence files are unavailable in the deployed workspace")
        if not receipts:
            raise ValueError("No safe BSC workspace evidence receipt was captured")
        return self.record_execution(
            mission_id,
            plan_id,
            {
                "actions": actions or ["Captured BSC workspace evidence"],
                "tool_receipts": receipts,
                "reflection": reflection or {},
                "observed_at": observed_at,
            },
        )

    @staticmethod
    def _bsc_workspace_root() -> Path:
        """Prefer the explicit read-only local workspace mount when configured."""
        configured = str(settings.PBOS_WORKSPACE_ROOT or "").strip()
        return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]

    @classmethod
    def _safe_bsc_workspace_paths(cls, paths: list[str]) -> list[str]:
        selected: list[str] = []
        for raw_path in paths:
            normalized = str(raw_path).strip().replace("\\", "/")
            candidate = PurePosixPath(normalized)
            if not normalized or candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("BSC workspace evidence paths must be relative and stay inside an approved directory")
            value = candidate.as_posix()
            allowed = value in cls._BSC_WORKSPACE_FILES or value.startswith(cls._BSC_WORKSPACE_PREFIXES)
            if not allowed:
                raise ValueError("BSC workspace evidence paths must be in an approved project directory")
            if value not in selected:
                selected.append(value)
        if not selected:
            raise ValueError("Select at least one BSC workspace evidence file")
        return selected

    def record_outcome(self, execution_id: str, payload: dict[str, Any]) -> WorkOutcomeArtifact:
        execution = self.store.get(execution_id)
        if not isinstance(execution, WorkExecutionRecordArtifact):
            raise ValueError("PBOS outcome requires an existing execution record")
        if any(
            isinstance(item, WorkOutcomeArtifact) and item.execution_record_id == execution_id
            for item in self.store.get_by_type(ArtifactType.WORK_OUTCOME)
        ):
            raise ValueError("PBOS execution already has an outcome record")
        values = dict(payload)
        acceptance_status = str(values.get("acceptance_status") or "unverified")
        if acceptance_status not in {"unverified", "accepted"}:
            raise ValueError("PBOS outcomes must start as unverified or be explicitly accepted with a score")
        if acceptance_status == "accepted":
            self._require_quality_score(values.get("quality_score"))
        elif values.get("quality_score") is not None:
            raise ValueError("PBOS quality scores are recorded only with explicit acceptance")
        metrics = dict(values.get("metrics") or {})
        plan = self.store.get(execution.plan_id) if execution.plan_id else None
        if isinstance(plan, PersonalExecutionPlanArtifact):
            values.setdefault("comparison_key", plan.comparison_key)
            values.setdefault("comparison_context", plan.comparison_context)
            values.setdefault("personal_context_fingerprint", plan.personal_context_fingerprint)
        values["comparison_key"] = str(values.get("comparison_key") or "personal_ai_project_delivery")
        values["comparison_context"] = str(values.get("comparison_context") or metrics.get("comparison_context") or "unclassified")
        values["personal_context_fingerprint"] = str(values.get("personal_context_fingerprint") or metrics.get("personal_context_fingerprint") or "")
        if values.get("baseline_quality") is None and metrics.get("baseline_quality") is not None:
            values["baseline_quality"] = metrics["baseline_quality"]
        values["hard_failure_resolved"] = bool(values.get("hard_failure_resolved") or metrics.get("hard_failure_resolved"))
        values["metrics"] = metrics
        mission_id = getattr(execution, "mission_id", "")
        artifact = WorkOutcomeArtifact(project_id=self.project_id, mission_id=mission_id, execution_record_id=execution_id, parent_ids=[execution_id], **values)
        self.store.add(artifact)
        return artifact

    def review_outcome(self, outcome_id: str, payload: dict[str, Any]) -> WorkOutcomeArtifact:
        """Record one explicit human review without replacing the evidence record.

        An outcome is an audit record, not a mutable score card. A review can
        resolve its initial ``unverified`` state exactly once and stores the
        previous values in the artifact before it is written back to the graph.
        """
        outcome = self.store.get(outcome_id)
        if not isinstance(outcome, WorkOutcomeArtifact):
            raise ValueError("outcome record not found")
        if outcome.acceptance_status != "unverified":
            raise ValueError("PBOS outcomes can only be reviewed while unverified")
        decision = str(payload.get("decision") or "").strip()
        if decision not in {"accepted", "rejected"}:
            raise ValueError("PBOS outcome review decision must be accepted or rejected")
        quality_score = payload.get("quality_score")
        if decision == "accepted":
            self._require_quality_score(quality_score)
            missing_evidence = [
                item
                for item in self._outcome_observation(outcome)["missing_requirements"]
                if item not in {"accepted_outcome", "quality_score"}
            ]
            if missing_evidence:
                raise ValueError(
                    "PBOS outcomes require reviewable execution evidence before acceptance: "
                    + ", ".join(missing_evidence)
                )
        review_note = str(payload.get("review_note") or "").strip()
        reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        outcome.review_history.append({
            "decision": decision,
            "previous_acceptance_status": outcome.acceptance_status,
            "previous_quality_score": outcome.quality_score,
            "review_note": review_note,
            "reviewed_at": reviewed_at,
            "source": "explicit_manual_review",
        })
        outcome.acceptance_status = decision
        outcome.quality_score = float(quality_score) if decision == "accepted" else None
        outcome.review_note = review_note
        outcome.reviewed_at = reviewed_at
        self.store.update(outcome)
        return outcome

    @staticmethod
    def _require_quality_score(value: Any) -> None:
        if isinstance(value, bool):
            raise ValueError("An accepted PBOS outcome requires a quality score from 0 to 100")
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("An accepted PBOS outcome requires a quality score from 0 to 100") from exc
        if not 0 <= score <= 100:
            raise ValueError("An accepted PBOS outcome requires a quality score from 0 to 100")

    def record_feedback(self, outcome_id: str, payload: dict[str, Any]) -> WorkFeedbackArtifact:
        outcome = self.store.get(outcome_id)
        if not isinstance(outcome, WorkOutcomeArtifact):
            raise ValueError("outcome record not found")
        statement = str(payload.get("statement") or "").strip()
        if not statement:
            raise ValueError("feedback statement is required")
        artifact = WorkFeedbackArtifact(
            project_id=self.project_id,
            outcome_id=outcome_id,
            parent_ids=[outcome_id],
            **{**payload, "statement": statement},
        )
        self.store.add(artifact)
        return artifact

    def compile_plan(self, mission_id: str, diagnosis_id: str = "") -> PersonalExecutionPlanArtifact:
        profile = self.profile()
        capabilities = self._latest_capabilities()
        experiences = [item for item in self.store.get_by_type(ArtifactType.EXPERIENCE) if isinstance(item, ExperienceArtifact) and item.verification_state == "verified"]
        strategies = self._latest([
            item for item in self.store.get_by_type(ArtifactType.SOP_VERSION)
            if isinstance(item, SOPVersionArtifact) and item.status == ArtifactStatus.ACTIVE
        ])
        feedback = self._recent_feedback()
        parents = [value for value in (mission_id, diagnosis_id, profile.artifact_id if profile else "", *(item.artifact_id for item in feedback)) if value]
        mission = self.store.get(mission_id)
        if not isinstance(mission, MissionArtifact):
            raise ValueError("PBOS plan requires an existing project Mission")
        diagnosis = self.store.get(diagnosis_id) if diagnosis_id else None
        if diagnosis_id and not isinstance(diagnosis, DiagnosisArtifact):
            raise ValueError("PBOS plan requires a project-scoped Diagnosis")
        knowledge_context = self._build_knowledge_context(mission)
        if not isinstance(knowledge_context, dict):
            knowledge_context = {"availability": "unavailable", "documents": [], "refs": []}
        plan_values = self.plan_compiler.compile(
            mission=mission,
            diagnosis=diagnosis if isinstance(diagnosis, DiagnosisArtifact) else None,
            profile=profile,
            capabilities=capabilities,
            experiences=experiences,
            strategies=strategies,
            feedback=[{"statement": item.statement, "source": item.source} for item in feedback],
            knowledge_context=knowledge_context,
        )
        artifact = PersonalExecutionPlanArtifact(
            project_id=self.project_id,
            mission_id=mission_id,
            diagnosis_id=diagnosis_id,
            parent_ids=parents,
            feedback_refs=[item.artifact_id for item in feedback],
            **plan_values,
        )
        self.store.add(artifact)
        return artifact

    def _build_knowledge_context(self, mission: MissionArtifact) -> dict[str, Any]:
        mission_context = mission.context if isinstance(mission.context, dict) else {}
        task_constraints = [
            mission.title,
            mission.intent,
            str(mission_context.get("goal") or ""),
            *[str(item) for item in mission_context.get("constraints") or []],
        ]
        try:
            parameters = inspect.signature(self.context_provider).parameters.values()
            accepts_constraints = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                or parameter.name == "task_constraints"
                for parameter in parameters
            )
        except (TypeError, ValueError):
            accepts_constraints = False
        if accepts_constraints:
            return self.context_provider(task_constraints=task_constraints)
        return self.context_provider()

    def _recent_feedback(self, limit: int = 3) -> list[WorkFeedbackArtifact]:
        """Return the bounded feedback context without promoting it to evidence."""
        feedback = self._latest([
            item for item in self.store.get_by_type(ArtifactType.WORK_FEEDBACK)
            if isinstance(item, WorkFeedbackArtifact) and item.outcome_id
        ])
        return feedback[:limit]

    def evolve(self, comparison_key: str = "", comparison_context: str = "") -> dict[str, Any]:
        outcomes = self._latest([
            item for item in self.store.get_by_type(ArtifactType.WORK_OUTCOME)
            if isinstance(item, WorkOutcomeArtifact)
        ])
        group, selection = self._select_comparison_group(outcomes, comparison_key, comparison_context)
        if group is None:
            return selection
        key, context = selection["comparison_key"], selection["comparison_context"]
        current = self._active_strategies(key, context)
        active = current[0] if current else None
        evaluated = set(active.genome.get("evidence") or []) if active else set()
        cycle = [item for item in group if item.artifact_id not in evaluated]
        complete = [item for item in cycle if self._is_complete_record(item)]
        severe = [item for item in cycle if item.severe_failure and self._is_complete_record(item)]
        summary = {
            "comparison_key": key,
            "comparison_context": context,
            "complete_records": len(complete),
            "total_cycle_records": len(cycle),
            "comparable_records": [item.artifact_id for item in complete],
        }
        baseline = self._baseline_quality(active, complete)
        scores = [float(item.quality_score) for item in reversed(complete) if item.quality_score is not None]
        two_regressions = bool(active and baseline is not None and len(scores) >= 2 and all(score < baseline for score in scores[-2:]))
        if severe or two_regressions:
            return self._rollback(active, complete, severe, summary)
        if len(complete) < 3:
            return {"state": "insufficient_evidence", **summary, "required_complete_records": 3}
        hard_failure_resolved = any(item.hard_failure_resolved for item in complete)
        if baseline is None and not hard_failure_resolved:
            return {
                "state": "candidate",
                **summary,
                "reason": "A promotion needs a declared baseline quality or a verified hard-failure repair.",
            }
        median_quality = median(scores)
        improvement = median_quality - baseline if baseline is not None else None
        if not hard_failure_resolved and (improvement is None or improvement < 10):
            return {
                "state": "candidate",
                **summary,
                "baseline_quality": baseline,
                "median_quality": median_quality,
                "improvement": improvement,
                "reason": "Comparable evidence has not improved median quality by ten points.",
            }
        return self._promote(active, complete, key, context, baseline, median_quality, hard_failure_resolved, summary)

    def today_action(self) -> dict[str, Any]:
        """Select the first unfinished, reviewable action from the active personal plan.

        Plans are ordered by their compiler-produced phases. This deliberately
        surfaces that order instead of inventing a priority from incomplete
        personal evidence.
        """
        plans = self._latest([
            item for item in self.store.get_by_type(ArtifactType.PERSONAL_EXECUTION_PLAN)
            if isinstance(item, PersonalExecutionPlanArtifact)
        ])
        if not plans:
            return {
                "state": "capture_required",
                "title": "Capture a bounded Mission and one governed project context.",
                "rationale": ["PBOS has no active personal execution plan to prioritize yet."],
                "success_check": "The Mission, its constraint, and one reviewable input are recorded.",
                "knowledge_context_refs": [],
                "plan_id": "",
                "mission_id": "",
                "phase_title": "Evidence capture",
                "selection_basis": "no_active_plan",
            }

        plan = plans[0]
        completed_actions = {
            str(action).strip()
            for record in self.store.get_by_type(ArtifactType.WORK_EXECUTION_RECORD)
            if isinstance(record, WorkExecutionRecordArtifact) and record.plan_id == plan.artifact_id
            for action in record.actions
            if str(action).strip()
        }
        selected_phase: dict[str, Any] = {}
        selected_action = ""
        for phase in plan.phases:
            if not isinstance(phase, dict):
                continue
            actions = [str(item).strip() for item in phase.get("actions") or [] if str(item).strip()]
            pending = next((item for item in actions if item not in completed_actions), "")
            if pending:
                selected_phase = phase
                selected_action = pending
                break
            if not selected_phase:
                selected_phase = phase

        if not selected_action:
            selected_action = str(selected_phase.get("title") or plan.title or "Record the next reviewable delivery result.").strip()
        checks = [str(item).strip() for item in selected_phase.get("checks") or [] if str(item).strip()]
        if not checks:
            checks = [str(item).strip() for item in plan.success_criteria if str(item).strip()]
        return {
            "state": "recommended" if plan.compilation_state != "capture_required" else "capture_required",
            "title": selected_action,
            "rationale": [str(item).strip() for item in plan.rationale[:3] if str(item).strip()],
            "success_check": checks[0] if checks else "Record an observable receipt and a concise reflection.",
            "knowledge_context_refs": list(plan.knowledge_context_refs),
            "plan_id": plan.artifact_id,
            "mission_id": plan.mission_id,
            "phase_title": str(selected_phase.get("title") or "Current plan phase"),
            "selection_basis": "first_unfinished_compiler_phase_action",
        }

    def cockpit(self) -> dict[str, Any]:
        profile = self.profile()
        capabilities = self._latest_capabilities()
        plans = self._latest([
            item for item in self.store.get_by_type(ArtifactType.PERSONAL_EXECUTION_PLAN)
            if isinstance(item, PersonalExecutionPlanArtifact)
        ])
        outcomes = self._latest([
            item for item in self.store.get_by_type(ArtifactType.WORK_OUTCOME)
            if isinstance(item, WorkOutcomeArtifact)
        ])
        executions = self._latest([
            item for item in self.store.get_by_type(ArtifactType.WORK_EXECUTION_RECORD)
            if isinstance(item, WorkExecutionRecordArtifact)
        ])
        feedback = self._recent_feedback()
        strategies = self._latest([
            item for item in self.store.get_by_type(ArtifactType.SOP_VERSION)
            if isinstance(item, SOPVersionArtifact)
        ])
        accepted = [item for item in outcomes if item.acceptance_status == "accepted"]
        outcome_observations = [self._outcome_observation(item) for item in outcomes]
        eligible_outcomes = [item for item in outcome_observations if item["eligible_for_evolution"]]
        active_plan = plans[0] if plans else None
        knowledge_context_refs = list(active_plan.knowledge_context_refs) if active_plan else []
        # A governed Vault input and learned personal evidence are distinct
        # states. Keeping them separate prevents a useful context pack from
        # being misreported as a missing connection just because PBOS has not
        # yet earned a personal capability claim.
        knowledge_context_ready = bool(knowledge_context_refs)
        personal_learning_ready = bool(
            active_plan and active_plan.compilation_state == "personalized"
        )
        personalization_readiness = self._personalization_readiness(
            profile,
            active_plan,
            outcomes,
        )
        outcome_by_execution_id = {str(item.execution_record_id): observation for item, observation in zip(outcomes, outcome_observations)}
        execution_observations = [
            self._execution_observation(item, outcome_by_execution_id.get(item.artifact_id))
            for item in executions[:6]
        ]
        return {
            "profile": profile.model_dump(mode="json") if profile else None,
            "today": plans[0].model_dump(mode="json") if plans else None,
            "today_action": self.today_action(),
            "capabilities": [item.model_dump(mode="json") for item in capabilities],
            "outcomes": [item.model_dump(mode="json") for item in outcomes],
            "outcome_observations": outcome_observations,
            "executions": execution_observations,
            "feedback": [item.model_dump(mode="json") for item in feedback],
            "strategies": [item.model_dump(mode="json") for item in strategies],
            "failure_patterns": self._failure_patterns(outcomes, feedback),
            "project_health": {
                "accepted_outcomes": len(accepted),
                "eligible_personal_outcomes": len(eligible_outcomes),
                "unverified_outcomes": len([item for item in outcomes if item.acceptance_status == "unverified"]),
                "rejected_outcomes": len([item for item in outcomes if item.acceptance_status == "rejected"]),
                "reviewable_executions": len([item for item in executions if self._is_reviewable_execution(item)]),
                "verified_capabilities": len(capabilities),
                "active_strategies": len([item for item in strategies if item.status == ArtifactStatus.ACTIVE]),
                "knowledge_context_ready": knowledge_context_ready,
                "knowledge_context_reference_count": len(knowledge_context_refs),
                "personal_learning_ready": personal_learning_ready,
                # Compatibility alias for earlier Cockpit consumers. It has
                # always meant personal-plan readiness, not Vault connection.
                "evidence_ready": personal_learning_ready,
            },
            "personalization_readiness": personalization_readiness,
            "connectors": {"github": "awaiting_authorization", "feishu": "awaiting_authorization"},
        }

    def _personalization_readiness(
        self,
        profile: PersonalProfileArtifact | None,
        active_plan: PersonalExecutionPlanArtifact | None,
        outcomes: list[WorkOutcomeArtifact],
    ) -> dict[str, Any]:
        """Expose the exact gates between a context-aware plan and a learned method."""
        metadata = active_plan.compiler_metadata if active_plan else {}
        effective_context = (
            metadata.get("effective_personal_context")
            if isinstance(metadata, dict) and isinstance(metadata.get("effective_personal_context"), dict)
            else {}
        )
        fields = ("role", "industry", "organization_stage")
        missing = [field for field in fields if not str(effective_context.get(field) or "").strip()]
        if not effective_context and profile:
            missing = [
                field for field in fields
                if not str(getattr(profile, field, "") or "").strip()
            ]
        comparison_key = active_plan.comparison_key if active_plan else ""
        comparison_context = active_plan.comparison_context if active_plan else ""
        comparable_complete = [
            outcome for outcome in outcomes
            if self._is_complete_record(outcome)
            and (not comparison_key or outcome.comparison_key == comparison_key)
            and (not comparison_context or outcome.comparison_context == comparison_context)
        ]
        if active_plan and active_plan.compilation_state == "personalized":
            state = "personalized"
        elif missing:
            state = "profile_context_required"
        elif len(comparable_complete) < 3:
            state = "learning_evidence_required"
        else:
            state = "promotion_evaluation_required"
        return {
            "state": state,
            "declared_profile_ready": bool(profile) and not missing,
            "missing_profile_fields": missing,
            "accepted_outcome_count": len(comparable_complete),
            "required_comparable_outcomes": 3,
            "comparison_key": comparison_key,
            "comparison_context": comparison_context,
        }

    def _execution_observation(
        self,
        execution: WorkExecutionRecordArtifact,
        outcome_observation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Expose receipt integrity, not raw work content, to the cockpit."""
        verified_receipt_count = sum(
            1 for receipt in execution.tool_receipts
            if isinstance(receipt, dict) and receipt.get("verified") is True
        )
        if outcome_observation is None:
            outcome_state = "awaiting_outcome"
        elif outcome_observation["eligible_for_evolution"]:
            outcome_state = "learning_eligible"
        elif outcome_observation["acceptance_status"] == "accepted":
            outcome_state = "accepted_incomplete"
        elif outcome_observation["acceptance_status"] == "rejected":
            outcome_state = "rejected_outcome"
        else:
            outcome_state = "unverified_outcome"
        return {
            "artifact_id": execution.artifact_id,
            "mission_id": execution.mission_id,
            "plan_id": execution.plan_id,
            "actions_count": len(execution.actions),
            "receipt_count": len(execution.tool_receipts),
            "verified_receipt_count": verified_receipt_count,
            "reflection_recorded": any(str(value).strip() for value in execution.reflection.values()),
            "outcome_state": outcome_state,
            "created_at": str(execution.created_at),
        }

    @staticmethod
    def _is_reviewable_execution(execution: WorkExecutionRecordArtifact) -> bool:
        return bool(
            execution.actions
            and PBOSService._has_verified_receipt(execution)
            and any(str(value).strip() for value in execution.reflection.values())
        )

    def _outcome_observation(self, outcome: WorkOutcomeArtifact) -> dict[str, Any]:
        """Expose whether an accepted outcome is sufficiently complete to teach PBOS.

        Acceptance alone can represent a technical delivery check. Personal
        learning additionally requires a reviewable execution receipt and a
        reflection, so historical validation runs cannot silently inflate a
        user's capability profile.
        """
        missing: list[str] = []
        if outcome.acceptance_status != "accepted":
            missing.append("accepted_outcome")
        if outcome.quality_score is None:
            missing.append("quality_score")
        execution = self.store.get(outcome.execution_record_id)
        if not isinstance(execution, WorkExecutionRecordArtifact):
            missing.append("execution_record")
        else:
            if not execution.actions:
                missing.append("actions")
            if not execution.tool_receipts:
                missing.append("tool_receipts")
            elif not self._has_verified_receipt(execution):
                missing.append("verified_tool_receipt")
            if not any(str(value).strip() for value in execution.reflection.values()):
                missing.append("reflection")
        return {
            "artifact_id": outcome.artifact_id,
            "acceptance_status": outcome.acceptance_status,
            "quality_score": outcome.quality_score,
            "eligible_for_evolution": not missing,
            "missing_requirements": missing,
        }

    def _latest_capabilities(self) -> list[CapabilityArtifact]:
        latest: dict[str, CapabilityArtifact] = {}
        for item in self._latest([
            value for value in self.store.get_by_type(ArtifactType.CAPABILITY)
            if isinstance(value, CapabilityArtifact)
        ]):
            latest.setdefault(item.name, item)
        return list(latest.values())

    def _active_strategies(self, comparison_key: str, comparison_context: str) -> list[SOPVersionArtifact]:
        return self._latest([
            item for item in self.store.get_by_type(ArtifactType.SOP_VERSION)
            if isinstance(item, SOPVersionArtifact)
            and item.status == ArtifactStatus.ACTIVE
            and str(item.genome.get("comparison_key") or "") == comparison_key
            and str(item.genome.get("comparison_context") or "") == comparison_context
        ])

    def _select_comparison_group(
        self,
        outcomes: list[WorkOutcomeArtifact],
        comparison_key: str,
        comparison_context: str,
    ) -> tuple[list[WorkOutcomeArtifact] | None, dict[str, Any]]:
        groups: dict[tuple[str, str], list[WorkOutcomeArtifact]] = {}
        for item in outcomes:
            key = item.comparison_key or "personal_ai_project_delivery"
            context = item.comparison_context or "unclassified"
            groups.setdefault((key, context), []).append(item)
        summaries = [
            {
                "comparison_key": key,
                "comparison_context": context,
                "complete_records": len([item for item in values if self._is_complete_record(item)]),
                "total_records": len(values),
            }
            for (key, context), values in sorted(groups.items())
        ]
        if comparison_key:
            matching = [(identity, values) for identity, values in groups.items() if identity[0] == comparison_key]
            if comparison_context:
                matching = [(identity, values) for identity, values in matching if identity[1] == comparison_context]
            if not matching:
                return None, {"state": "insufficient_evidence", "complete_records": 0, "comparison_groups": summaries}
            if len(matching) > 1:
                return None, {"state": "comparison_context_required", "comparison_key": comparison_key, "comparison_groups": summaries}
            (key, context), values = matching[0]
            return values, {"comparison_key": key, "comparison_context": context, "comparison_groups": summaries}
        if len(groups) == 1:
            (key, context), values = next(iter(groups.items()))
            return values, {"comparison_key": key, "comparison_context": context, "comparison_groups": summaries}
        if not groups:
            return None, {"state": "insufficient_evidence", "complete_records": 0, "comparison_groups": []}
        return None, {"state": "comparison_required", "comparison_groups": summaries}

    def _is_complete_record(self, outcome: WorkOutcomeArtifact) -> bool:
        if outcome.acceptance_status != "accepted" or outcome.quality_score is None:
            return False
        execution = self.store.get(outcome.execution_record_id)
        if not isinstance(execution, WorkExecutionRecordArtifact):
            return False
        has_reflection = any(str(value).strip() for value in execution.reflection.values())
        return bool(execution.actions and self._has_verified_receipt(execution) and has_reflection)

    @staticmethod
    def _has_verified_receipt(execution: WorkExecutionRecordArtifact) -> bool:
        return any(
            isinstance(receipt, dict) and receipt.get("verified") is True
            for receipt in execution.tool_receipts
        )

    @staticmethod
    def _baseline_quality(active: SOPVersionArtifact | None, outcomes: list[WorkOutcomeArtifact]) -> float | None:
        if active is not None:
            value = active.genome.get("median_quality")
            return float(value) if value is not None else None
        values = [float(item.baseline_quality) for item in outcomes if item.baseline_quality is not None]
        return float(median(values)) if values else None

    def _promote(
        self,
        active: SOPVersionArtifact | None,
        outcomes: list[WorkOutcomeArtifact],
        comparison_key: str,
        comparison_context: str,
        baseline: float | None,
        median_quality: float,
        hard_failure_resolved: bool,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        if active is not None:
            active.status = ArtifactStatus.SUPERSEDED
            self.store.update(active)
        evidence_ids = [item.artifact_id for item in outcomes]
        execution_paths = self._execution_paths(outcomes)
        feedback_patterns = self._feedback_for_outcomes(evidence_ids)
        genome = {
            "scope": "personal_ai_project_delivery",
            "comparison_key": comparison_key,
            "comparison_context": comparison_context,
            "input_conditions": {"comparison_key": comparison_key, "comparison_context": comparison_context},
            "decision_rules": [
                "Use this strategy only when the recorded comparison context matches.",
                "Require a reviewable receipt, reflection, accepted outcome, and quality score for every evidence record.",
            ],
            "execution_paths": execution_paths,
            "capabilities": [item.name for item in self._latest_capabilities()],
            "risks": feedback_patterns,
            "failure_boundaries": ["severe failure", "two comparable quality regressions"],
            "success_metrics": ["accepted outcome quality"],
            "verification": {
                "complete_records": len(outcomes),
                "baseline_quality": baseline,
                "median_improvement": median_quality - baseline if baseline is not None else None,
                "hard_failure_resolved": hard_failure_resolved,
            },
            "evidence": evidence_ids,
            "success_cases": evidence_ids,
            "failure_cases": [],
            "median_quality": median_quality,
            "confidence": min(0.95, 0.55 + len(outcomes) * 0.1),
        }
        version = SOPVersionArtifact(
            project_id=self.project_id,
            label=f"{self._strategy_name(comparison_key)} v{(active.version + 1) if active else 1}",
            strategy_name=self._strategy_name(comparison_key),
            version=(active.version + 1) if active else 1,
            genome=genome,
            promotion_state="promote",
            supersedes_id=active.artifact_id if active else "",
            parent_ids=evidence_ids + ([active.artifact_id] if active else []),
            status=ArtifactStatus.ACTIVE,
        )
        self.store.add(version)
        promotion = SOPPromotionArtifact(
            project_id=self.project_id,
            sop_version_id=version.artifact_id,
            previous_version_id=active.artifact_id if active else "",
            decision="promote",
            reason="Comparable complete records improved the verified baseline or resolved a hard failure.",
            comparable_record_ids=evidence_ids,
            parent_ids=[version.artifact_id],
        )
        self.store.add(promotion)
        experience = ExperienceArtifact(
            project_id=self.project_id,
            label=f"Verified experience: {self._strategy_name(comparison_key)}",
            statement=f"{self._strategy_name(comparison_key)} improved median quality to {median_quality:.1f} in {comparison_context}.",
            applicability=[comparison_key, comparison_context],
            success_factors=execution_paths[:5],
            failure_patterns=feedback_patterns,
            verification_state="verified",
            parent_ids=evidence_ids + [version.artifact_id],
            evidence_refs=evidence_ids,
        )
        self.store.add(experience)
        name = self._capability_name(comparison_key)
        previous = next((item for item in self._latest_capabilities() if item.name == name), None)
        curve = list(previous.growth_curve) if previous else []
        curve.append({"score": median_quality, "baseline_quality": baseline, "evidence_count": len(evidence_ids), "strategy_id": version.artifact_id})
        capability = CapabilityArtifact(
            project_id=self.project_id,
            label=name,
            name=name,
            level=min(5, (previous.level + 1) if previous else 1),
            evidence_count=(previous.evidence_count if previous else 0) + len(evidence_ids),
            related_strategy_ids=[*(previous.related_strategy_ids if previous else []), version.artifact_id],
            growth_curve=curve,
            parent_ids=[experience.artifact_id, version.artifact_id, *([previous.artifact_id] if previous else [])],
            evidence_refs=evidence_ids,
        )
        self.store.add(capability)
        return {"state": "promote", "sop_version": version, "promotion": promotion, **summary}

    def _rollback(
        self,
        active: SOPVersionArtifact | None,
        outcomes: list[WorkOutcomeArtifact],
        severe: list[WorkOutcomeArtifact],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_ids = [item.artifact_id for item in outcomes] + [item.artifact_id for item in severe if item.artifact_id not in {value.artifact_id for value in outcomes}]
        if active is None or not active.supersedes_id:
            return {
                "state": "rollback_unavailable",
                **summary,
                "reason": "A severe failure or two regressions require review, but there is no prior promoted strategy to restore.",
                "comparable_record_ids": evidence_ids,
            }
        previous = self.store.get(active.supersedes_id)
        if not isinstance(previous, SOPVersionArtifact):
            return {"state": "rollback_unavailable", **summary, "reason": "The prior strategy version is unavailable.", "comparable_record_ids": evidence_ids}
        active.status = ArtifactStatus.DEPRECATED
        active.promotion_state = "rolled_back"
        self.store.update(active)
        previous.status = ArtifactStatus.ACTIVE
        self.store.update(previous)
        promotion = SOPPromotionArtifact(
            project_id=self.project_id,
            sop_version_id=active.artifact_id,
            previous_version_id=previous.artifact_id,
            decision="rollback",
            reason="Severe failure or two comparable quality regressions triggered the rollback boundary.",
            comparable_record_ids=evidence_ids,
            parent_ids=[active.artifact_id, previous.artifact_id, *evidence_ids],
        )
        self.store.add(promotion)
        return {"state": "rollback", "sop_version": previous, "promotion": promotion, **summary}

    def _execution_paths(self, outcomes: list[WorkOutcomeArtifact]) -> list[str]:
        paths: list[str] = []
        for outcome in outcomes:
            execution = self.store.get(outcome.execution_record_id)
            if not isinstance(execution, WorkExecutionRecordArtifact):
                continue
            for action in execution.actions:
                value = str(action).strip()
                if value and value not in paths:
                    paths.append(value[:500])
        return paths[:12]

    def _feedback_for_outcomes(self, outcome_ids: list[str]) -> list[str]:
        values: list[str] = []
        for item in self.store.get_by_type(ArtifactType.WORK_FEEDBACK):
            if isinstance(item, WorkFeedbackArtifact) and item.outcome_id in outcome_ids and item.statement:
                values.append(item.statement)
        return list(dict.fromkeys(values))[:8]

    def _failure_patterns(self, outcomes: list[WorkOutcomeArtifact], feedback: list[WorkFeedbackArtifact]) -> list[dict[str, Any]]:
        patterns: list[dict[str, Any]] = []
        severe = [item for item in outcomes if item.severe_failure and self._is_complete_record(item)]
        if severe:
            patterns.append({"kind": "severe_failure", "count": len(severe), "evidence_refs": [item.artifact_id for item in severe]})
        negative = [item for item in feedback if item.sentiment == "negative"]
        if negative:
            patterns.append({"kind": "negative_feedback", "count": len(negative), "evidence_refs": [item.artifact_id for item in negative]})
        return patterns

    @staticmethod
    def _strategy_name(comparison_key: str) -> str:
        return "Personal AI project delivery" if comparison_key == "personal_ai_project_delivery" else comparison_key.replace("_", " ").replace("-", " ").title()

    @staticmethod
    def _capability_name(comparison_key: str) -> str:
        return "AI project delivery" if comparison_key == "personal_ai_project_delivery" else f"{PBOSService._strategy_name(comparison_key)} delivery"
