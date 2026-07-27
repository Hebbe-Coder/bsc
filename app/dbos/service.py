"""Persistent DBOS application service over the existing Artifact Graph."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.artifacts import (
    AssumptionArtifact,
    ArtifactGraphStore,
    ArtifactStatus,
    AdvisorReviewArtifact,
    CapabilitySelectionArtifact,
    DecisionArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    EvidenceArtifact,
    ExecutionResultArtifact,
    ExternalWorkerRunArtifact,
    GapArtifact,
    GapCategory,
    MemoryArtifact,
    MissionArtifact,
    RiskArtifact,
    Severity,
    RuntimeContextArtifact,
    SOPRoutingEvaluationArtifact,
    TaskVerificationArtifact,
)
from app.capabilities import CapabilityRegistry, build_default_registry
from app.core.config import settings
from app.services.sop_llm_client import PROVIDER_KEY_MAP

from .capabilities import CapabilitySelector
from .adaptive_compiler import AdaptiveSOPCompiler
from .advisor import MissionAdvisor
from .compiler import DynamicSOPCompiler
from .contracts import DBOSFlow, MissionInput
from .diagnosis import DiagnosisService
from .evaluation import SOPRoutingEvaluator
from .execution import (
    MissionExecutionService,
    MissionNotConfirmedError,
    MissionNotFoundError,
    MissionStateError,
    UnauthorizedCapabilityError,
)
from .memory import DBOSMemoryService, KnowledgeMemoryAdapter
from .intake import IntakeError, IntakeService
from .intake_evidence import IntakeEvidenceService
from .runtime import RuntimeContextBuilder, recover_interrupted_runs


class DBOSService:
    """The only DBOS business-policy entry point for REST, MCP, and UI."""

    def __init__(
        self,
        *,
        store: ArtifactGraphStore,
        registry: CapabilityRegistry | None = None,
        capability_executor: Any | None = None,
        knowledge_repository: Any | None = None,
        knowledge_repository_factory: Callable[[], Any] | None = None,
        adaptive_compiler: Any | None = None,
        routing_evaluator: SOPRoutingEvaluator | None = None,
        advisor: MissionAdvisor | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or build_default_registry()
        self.diagnosis_service = DiagnosisService()
        self.selector = CapabilitySelector(self.registry)
        self.compiler = DynamicSOPCompiler()
        self.adaptive_compiler = adaptive_compiler or AdaptiveSOPCompiler()
        self.routing_evaluator = routing_evaluator or SOPRoutingEvaluator(
            diagnosis_service=self.diagnosis_service,
            selector=self.selector,
            compiler=self.compiler,
        )
        self.advisor = advisor or MissionAdvisor()
        self.execution_service = MissionExecutionService(store, self.registry, capability_executor)
        self.knowledge_adapter = KnowledgeMemoryAdapter(
            knowledge_repository,
            repository_factory=knowledge_repository_factory,
        )
        self._knowledge_repository = knowledge_repository
        self._knowledge_repository_factory = knowledge_repository_factory
        self.memory_service = DBOSMemoryService()
        self.runtime_context_builder = RuntimeContextBuilder()
        self.intake_service = IntakeService(store)

    def create_intake(self, project_id: str, request_text: str, *, context: dict[str, Any] | None = None):
        """Classify and persist one governed intake without creating a Mission."""
        return self.intake_service.create_session(project_id, request_text, context=context)

    def get_intake(self, session_id: str):
        return self.intake_service.get_session(session_id)

    def resolve_intake_uncertainty(self, session_id: str, action: str):
        return self.intake_service.resolve_uncertain(session_id, action)

    def next_intake_question(self, session_id: str) -> dict[str, Any] | None:
        return self.intake_service.next_question(session_id)

    def answer_intake(self, session_id: str, question_id: str, answer: str = "", *, skipped: bool = False):
        return self.intake_service.answer(session_id, question_id, answer, skipped=skipped)

    def revert_intake_answer(self, session_id: str, revision_id: str):
        return self.intake_service.revert(session_id, revision_id)

    def list_intake_revisions(self, session_id: str):
        return self.intake_service.list_revisions(session_id)

    def direct_to_review(self, session_id: str):
        return self.intake_service.direct_to_review(session_id)

    def select_intake_tier(self, session_id: str, tier: str):
        return self.intake_service.select_tier(session_id, tier)

    def recommend_intake(self, session_id: str):
        return self._with_intake_evidence(lambda service, session: service.recommend(session), session_id)

    def export_intake_handoff(self, session_id: str, *, actor_id: str, approved: bool):
        return self._with_intake_evidence(
            lambda service, session: service.export_handoff(session, actor_id=actor_id, approved=approved), session_id
        )

    def _with_intake_evidence(self, operation, session_id: str):
        self.intake_service._ensure_enabled()
        session = self.intake_service.get_session(session_id)
        repository = self._knowledge_repository
        owned = False
        if repository is None and self._knowledge_repository_factory is not None:
            repository = self._knowledge_repository_factory()
            owned = True
        try:
            return operation(IntakeEvidenceService(self.store, repository), session)
        finally:
            if owned and hasattr(repository, "close"):
                repository.close()

    def convert_intake(self, session_id: str, *, title: str = "") -> DBOSFlow:
        """Create exactly one review-gated Mission from a ready Intake session."""
        self.intake_service._ensure_enabled()
        session = self.intake_service.get_session(session_id)
        if session.linked_mission_id:
            mission = self._mission(session.linked_mission_id)
            return self.diagnose_and_compile(mission.artifact_id)
        if session.phase != "ready_for_review":
            raise IntakeError("intake must be ready for review before conversion")

        context = dict(session.declared_context)
        context.update({
            "intake_session_id": session.artifact_id,
            "intake_domain": session.domain,
            "intake_tier": session.tier,
            "intake_unresolved_fields": list(session.unresolved_fields),
            "sop_generation_mode": "adaptive",
        })
        mission = self.create_mission(
            project_id=session.project_id,
            title=(title.strip() or f"Intake mission: {session.original_request[:240]}")[:300],
            intake_mode="career" if session.domain == "career" else "business",
            intent=session.original_request,
            context=context,
        )
        mission.parent_ids = [session.artifact_id]
        self.store.update(mission)
        flow = self.diagnose_and_compile(mission.artifact_id)
        self._persist_unresolved_intake_gaps(session, flow.diagnosis.artifact_id)
        session.linked_mission_id = mission.artifact_id
        session.phase = "converted"
        self.store.update(session)
        return self.diagnose_and_compile(mission.artifact_id)

    def _persist_unresolved_intake_gaps(self, session, diagnosis_id: str) -> None:
        """Keep skipped or bypassed fields explicit rather than inferring a fact."""
        for field in session.unresolved_fields:
            self.store.add(AssumptionArtifact(
                project_id=session.project_id,
                label=f"Unanswered intake: {field}",
                statement=f"No value was supplied for intake field '{field}'; it must not be inferred.",
                category="intake_gap",
                criticality=Severity.MEDIUM,
                validation_method="owner confirmation",
                counterfactual=f"If {field} changes, review the Mission context and recompile the SOP.",
                parent_ids=[diagnosis_id, session.artifact_id],
                source_agent="dbos_blindspot_intake",
                tags=["dbos", "blindspot_intake", "unanswered"],
            ))
            self.store.add(GapArtifact(
                project_id=session.project_id,
                label=f"Unanswered intake: {field}",
                gap_statement=f"The intake owner did not declare '{field}', so it remains an explicit gap.",
                category=GapCategory.EVIDENCE_MISSING,
                severity=Severity.MEDIUM,
                affected_artifact_ids=[diagnosis_id, session.artifact_id],
                resolution=f"Capture and approve a declared value for {field} before widening execution scope.",
                parent_ids=[diagnosis_id, session.artifact_id],
                source_agent="dbos_blindspot_intake",
                tags=["dbos", "blindspot_intake", "unanswered"],
            ))

    def create_mission(self, **values: Any) -> MissionArtifact:
        payload = MissionInput(**values)
        mission = MissionArtifact(
            project_id=payload.project_id,
            label=payload.title,
            title=payload.title,
            intent=payload.intent,
            intake_mode=payload.intake_mode,
            context=payload.context,
            mission_status="draft",
            status=ArtifactStatus.DRAFT,
            source_agent="dbos_intake",
        )
        mission.mission_id = mission.artifact_id
        self.store.add(mission)
        return mission

    def diagnose_and_compile(self, mission_id: str) -> DBOSFlow:
        mission = self._mission(mission_id)
        existing = self._existing_flow(mission)
        if existing is not None:
            self._ensure_sop_routing_evaluation(mission)
            return self._existing_flow(self._mission(mission_id)) or existing
        if mission.mission_status != "draft":
            raise MissionStateError("mission cannot be diagnosed in its current state")
        diagnosis, assumptions, gaps, risks, evidence = self.diagnosis_service.diagnose(mission)
        self.store.add(diagnosis)
        for artifact in evidence:
            artifact.parent_ids = [diagnosis.artifact_id]
            self.store.add(artifact)
        for artifact in assumptions:
            self.store.add(artifact)
        for artifact in gaps:
            self.store.add(artifact)
        for artifact in risks:
            self.store.add(artifact)
        knowledge_context = self.knowledge_adapter.snapshot(mission.project_id, task=mission.intent)
        selection = self.selector.select(diagnosis, knowledge_context=knowledge_context)
        self.store.add(selection)
        runtime_context = self.runtime_context_builder.build(
            mission=mission,
            diagnosis=diagnosis,
            selection=selection,
            knowledge_context=knowledge_context,
            purpose="dynamic_sop_and_execution",
        )
        self.store.add(runtime_context)
        sop = self.compiler.compile(diagnosis, selection)
        if self._adaptive_sop_requested(mission):
            sop = self.adaptive_compiler.refine(
                sop,
                diagnosis=diagnosis,
                selection=selection,
                evidence=evidence,
                knowledge_context=knowledge_context,
            )
        self.store.add(sop)
        routing_evaluation = self.routing_evaluator.evaluate(
            mission=mission,
            diagnosis=diagnosis,
            selection=selection,
            sop=sop,
        )
        self.store.add(routing_evaluation)
        prepared = mission.model_copy(
            update={
                "mission_status": "ready_for_confirmation",
                "status": ArtifactStatus.READY_FOR_CONFIRMATION,
                "authorization": {
                    "diagnosis_id": diagnosis.artifact_id,
                    "selection_id": selection.artifact_id,
                    "dynamic_sop_id": sop.artifact_id,
                    "sop_routing_evaluation_id": routing_evaluation.artifact_id,
                    "sop_routing_evaluation_status": routing_evaluation.evaluation_status,
                    "selection": {"selected_capabilities": selection.selected_names},
                },
            }
        )
        self.store.update(prepared)
        return DBOSFlow(
            mission=prepared,
            diagnosis=diagnosis,
            selection=selection,
            sop=sop,
            routing_evaluation_id=routing_evaluation.artifact_id,
            context_snapshot_id=runtime_context.artifact_id,
            assumption_ids=[item.artifact_id for item in assumptions],
            gap_ids=[item.artifact_id for item in gaps],
            risk_ids=[item.artifact_id for item in risks],
            evidence_ids=[item.artifact_id for item in evidence],
        )

    @classmethod
    def _adaptive_sop_requested(cls, mission: MissionArtifact) -> bool:
        """Choose a model refinement policy without weakening an explicit opt-out.

        Studio always requests adaptive composition, but API and MCP callers may
        omit the optional mode. When the configured SOP provider is actually
        usable, omission means the same adaptive experience as Studio. A caller
        must explicitly choose a deterministic mode to receive the structural
        baseline only.
        """
        context = mission.context if isinstance(mission.context, dict) else {}
        mode = str(context.get("sop_generation_mode") or "").strip().lower()
        if mode in {"deterministic", "baseline", "off"}:
            return False
        if mode == "adaptive":
            # An explicit request still reaches the compiler so its persisted
            # fallback metadata records a provider/configuration failure.
            return True
        if mode not in {"", "auto"}:
            return False
        return cls._adaptive_sop_available()

    @staticmethod
    def _adaptive_sop_available() -> bool:
        provider = str(settings.SOP_LLM_PROVIDER or settings.LLM_PROVIDER or "mock").strip().lower()
        key_setting = PROVIDER_KEY_MAP.get(provider)
        if key_setting is None:
            return False
        return bool(str(getattr(settings, key_setting[0], "") or "").strip())

    def confirm(self, mission_id: str, *, actor_id: str, authorized_capabilities: list[str]) -> MissionArtifact:
        self._ensure_sop_routing_evaluation(self._mission(mission_id))
        return self.execution_service.confirm(
            self._mission(mission_id),
            actor_id=actor_id,
            authorized_capabilities=authorized_capabilities,
        )

    async def execute(
        self,
        mission_id: str,
        capability_name: str,
        *,
        idempotency_key: str = "",
        executor: Callable[[str, dict[str, Any]], Awaitable[Any] | Any] | None = None,
    ) -> ExecutionResultArtifact:
        mission = self._mission(mission_id)
        self._ensure_sop_routing_evaluation(mission)
        mission = self._mission(mission_id)
        sop_id = str(mission.authorization.get("dynamic_sop_id") or "")
        if not sop_id:
            raise MissionStateError("mission has no compiled Dynamic SOP")
        granted = {str(name) for name in mission.authorization.get("authorized_capabilities", []) if str(name)}
        if mission.mission_status in {"confirmed", "executing"} and capability_name in granted:
            self._require_persisted_decision(mission, capability_name, sop_id)
        key = idempotency_key.strip() or f"{mission.artifact_id}:{capability_name}"
        context = {
            "project_id": mission.project_id,
            "mission_id": mission.artifact_id,
            "intent": mission.intent,
            "diagnosis_id": str(mission.authorization.get("diagnosis_id") or ""),
            "dynamic_sop_id": sop_id,
            "runtime_context_id": self._runtime_context_id(mission),
        }
        return await self.execution_service.execute(
            mission,
            capability_name=capability_name,
            dynamic_sop_id=sop_id,
            idempotency_key=key,
            context_snapshot_id=str(context["runtime_context_id"]),
            context=context,
            callback=executor,
        )

    def get_mission(self, mission_id: str) -> MissionArtifact:
        return self._mission(mission_id)

    def record_decision(
        self,
        mission_id: str,
        *,
        task_id: str,
        statement: str,
        rationale: str,
        alternatives: list[str],
        actor_id: str,
    ) -> DecisionArtifact:
        """Persist a reviewer decision against a compiled task before execution."""
        mission = self._mission(mission_id)
        sop_id = str(mission.authorization.get("dynamic_sop_id") or "")
        sop = self.store.get(sop_id)
        if not isinstance(sop, DynamicSOPArtifact):
            raise MissionStateError("mission has no compiled Dynamic SOP")
        task = next((item for phase in sop.phases for item in phase.tasks if item.task_id == task_id), None)
        if task is None:
            raise ValueError("task_id is not part of this mission's Dynamic SOP")
        diagnosis = self._first(self.store.get_by_project(mission.project_id), DiagnosisArtifact, mission_id)
        return self.store.create_decision(
            statement.strip(),
            project_id=mission.project_id,
            label=f"Decision: {task.title}"[:140],
            parent_ids=list(dict.fromkeys([mission.artifact_id, sop.artifact_id, *task.parent_refs])),
            rationale=rationale.strip(),
            alternatives=list(dict.fromkeys(item.strip() for item in alternatives if item.strip())),
            assumption_confidence=diagnosis.coverage if diagnosis else 0.0,
            coverage_pct=round((diagnosis.coverage if diagnosis else 0.0) * 100, 1),
            recommendation=task.decision_point,
            decision_makers=[actor_id.strip()],
            metadata={
                "mission_id": mission.artifact_id,
                "dynamic_sop_id": sop.artifact_id,
                "task_id": task.task_id,
            },
            source_agent="dbos_decision_log",
            tags=["dbos", "decision", task.task_family],
        )

    def list_missions(self) -> list[dict[str, Any]]:
        """Return the persisted authorization roots for this scoped ledger."""
        missions = [
            item for item in self.store.get_by_type(MissionArtifact.model_fields["artifact_type"].default)
            if isinstance(item, MissionArtifact)
        ]
        missions.sort(key=lambda item: item.created_at, reverse=True)
        return [self._mission_view(item) for item in missions]

    def record_feedback(self, mission_id: str, statement: str, source_refs: list[str] | None = None) -> MemoryArtifact:
        mission = self._mission(mission_id)
        executions = [
            item for item in self.store.get_by_project(mission.project_id)
            if isinstance(item, ExecutionResultArtifact) and item.mission_id == mission_id
        ]
        if not executions:
            raise MissionStateError("feedback requires an audited execution result")
        latest = sorted(executions, key=lambda item: item.created_at, reverse=True)[0]
        memory = self.record_feedback_memory(
            mission_id,
            latest.artifact_id,
            statement=statement,
        )
        if source_refs:
            memory.source_refs = list(dict.fromkeys([*memory.source_refs, *source_refs]))
            self.store.update(memory)
        return memory

    def run_external_worker(
        self,
        mission_id: str,
        *,
        dynamic_sop_id: str,
        capability_name: str,
        worker_id: str,
        model_id: str,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
        estimated_cost_microusd: int = 0,
    ) -> ExternalWorkerRunArtifact:
        """Queue one policy-governed external HTTPS worker attempt.

        The Profile repository is opened only for this request.  No provider
        credential flows through this public service method.
        """
        from .external_worker import ExternalWorkerService

        repository = self._knowledge_repository
        owned = False
        if repository is None:
            factory = self._knowledge_repository_factory
            if factory is None:
                from app.knowledge.growth_repository import GrowthRepository
                factory = GrowthRepository
            repository = factory()
            owned = True
        try:
            return ExternalWorkerService(self.store, repository).start(
                mission_id=mission_id,
                dynamic_sop_id=dynamic_sop_id,
                capability_name=capability_name,
                worker_id=worker_id,
                model_id=model_id,
                endpoint=endpoint,
                payload=payload,
                idempotency_key=idempotency_key,
                estimated_cost_microusd=estimated_cost_microusd,
            )
        finally:
            if owned and hasattr(repository, "close"):
                repository.close()

    def cancel_external_worker(self, run_id: str, *, reason: str):
        """Request a real transport cancellation for one project-scoped run."""
        from .external_worker import ExternalWorkerService

        repository = self._knowledge_repository
        owned = False
        if repository is None:
            factory = self._knowledge_repository_factory
            if factory is None:
                from app.knowledge.growth_repository import GrowthRepository
                factory = GrowthRepository
            repository = factory()
            owned = True
        try:
            return ExternalWorkerService(self.store, repository).request_cancel(run_id, reason=reason)
        finally:
            if owned and hasattr(repository, "close"):
                repository.close()

    def review_mission(self, mission_id: str, *, idempotency_key: str) -> AdvisorReviewArtifact:
        """Run one bounded Advisor review without changing mission authority.

        The persisted result is intentionally an advisory artifact, rather
        than a decision or a capability grant. Reusing the same key returns
        the original review so an impatient UI or MCP client cannot silently
        spend a second provider call for the same operator action.
        """
        key = idempotency_key.strip()
        if not key:
            raise ValueError("advisor review requires an idempotency key")
        mission = self._mission(mission_id)
        artifacts = self.store.get_by_project(mission.project_id)
        existing = [
            item
            for item in artifacts
            if isinstance(item, AdvisorReviewArtifact)
            and item.mission_id == mission.artifact_id
            and item.idempotency_key == key
        ]
        if existing:
            return max(existing, key=lambda item: item.created_at)
        diagnosis = self._first(artifacts, DiagnosisArtifact, mission_id)
        selection = self._first(artifacts, CapabilitySelectionArtifact, mission_id)
        sop = self._first(artifacts, DynamicSOPArtifact, mission_id)
        if not all((diagnosis, selection, sop)):
            raise MissionStateError("advisor review requires a diagnosed mission and compiled Dynamic SOP")
        evidence = [
            item for item in artifacts
            if isinstance(item, EvidenceArtifact) and diagnosis.artifact_id in item.parent_ids
        ]
        gaps = [
            item for item in artifacts
            if isinstance(item, GapArtifact) and diagnosis.artifact_id in item.parent_ids
        ]
        risks = [
            item for item in artifacts
            if isinstance(item, RiskArtifact) and diagnosis.artifact_id in item.parent_ids
        ]
        review = self.advisor.review(
            mission=mission,
            diagnosis=diagnosis,
            selection=selection,
            sop=sop,
            runtime_context=self._runtime_context(mission, artifacts),
            evidence=evidence,
            gaps=gaps,
            risks=risks,
            idempotency_key=key,
        )
        self.store.add(review)
        return review

    def record_feedback_memory(
        self,
        mission_id: str,
        execution_id: str,
        *,
        statement: str,
        feedback_kind: str = "feedback",
    ) -> MemoryArtifact:
        mission = self._mission(mission_id)
        execution = self.store.get(execution_id)
        if not isinstance(execution, ExecutionResultArtifact) or execution.mission_id != mission.artifact_id:
            raise MissionNotFoundError("execution was not found for this mission")
        memory = self.memory_service.record_feedback(
            mission=mission,
            execution=execution,
            statement=statement,
            feedback_kind=feedback_kind,
        )
        self.store.add(memory)
        return memory

    def control_center(self, mission_id: str) -> dict[str, Any]:
        mission = self._mission(mission_id)
        artifacts = self.store.get_by_project(mission.project_id)
        diagnosis = self._first(artifacts, DiagnosisArtifact, mission_id)
        selection = self._first(artifacts, CapabilitySelectionArtifact, mission_id)
        sop = self._first(artifacts, DynamicSOPArtifact, mission_id)
        executions = [
            item for item in artifacts
            if isinstance(item, ExecutionResultArtifact) and item.mission_id == mission_id
        ]
        executions.sort(key=lambda item: item.created_at, reverse=True)
        memories = [
            item for item in artifacts
            if isinstance(item, MemoryArtifact)
            and any(execution.artifact_id in item.parent_ids for execution in executions)
        ]
        decisions = [
            item for item in artifacts
            if isinstance(item, DecisionArtifact) and mission.artifact_id in item.parent_ids
        ]
        decisions.sort(key=lambda item: item.created_at, reverse=True)
        assumptions = [
            item for item in artifacts
            if isinstance(item, AssumptionArtifact) and diagnosis and diagnosis.artifact_id in item.parent_ids
        ]
        gaps = [
            item for item in artifacts
            if isinstance(item, GapArtifact) and diagnosis and diagnosis.artifact_id in item.parent_ids
        ]
        risks = [
            item for item in artifacts
            if isinstance(item, RiskArtifact) and diagnosis and diagnosis.artifact_id in item.parent_ids
        ]
        evidence = [
            item for item in artifacts
            if isinstance(item, EvidenceArtifact) and diagnosis and diagnosis.artifact_id in item.parent_ids
        ]
        verifications = [
            item for item in artifacts
            if isinstance(item, TaskVerificationArtifact)
            and any(item.execution_id == execution.execution_id for execution in executions)
        ]
        verifications.sort(key=lambda item: item.created_at, reverse=True)
        external_worker_runs = [
            item for item in artifacts
            if isinstance(item, ExternalWorkerRunArtifact) and item.mission_id == mission_id
        ]
        external_worker_runs.sort(key=lambda item: item.created_at, reverse=True)
        advisor_reviews = [
            item for item in artifacts
            if isinstance(item, AdvisorReviewArtifact) and item.mission_id == mission_id
        ]
        advisor_reviews.sort(key=lambda item: item.created_at, reverse=True)
        routing_evaluation = self._routing_evaluation(mission, artifacts)
        flow = self._existing_flow(mission)
        completed = [item for item in executions if item.execution_status == "completed"]
        runtime_context = self._runtime_context(mission, artifacts)
        return {
            "mission": self._mission_view(mission),
            "diagnosis": self._view(diagnosis),
            "selection": self._view(selection),
            "dynamic_sop": self._view(sop),
            "execution_results": [self._execution_view(item) for item in executions],
            "decisions": [self._view(item) for item in decisions],
            "memories": [self._view(item) for item in memories],
            "assumptions": [self._view(item) for item in assumptions],
            "gaps": [self._view(item) for item in gaps],
            "risks": [self._view(item) for item in risks],
            "evidence": [self._view(item) for item in evidence],
            "verifications": [self._view(item) for item in verifications],
            "external_worker_runs": [self._view(item) for item in external_worker_runs],
            "advisor_reviews": [self._view(item) for item in advisor_reviews],
            "sop_routing_evaluation": self._view(routing_evaluation),
            "runtime_context": self._view(runtime_context),
            "knowledge_context": selection.metadata.get("knowledge_context", {"availability": "unavailable"}) if selection else {"availability": "unavailable"},
            "health": {
                "status": mission.mission_status,
                "confirmed": mission.mission_status not in {"draft", "ready_for_confirmation"},
                "selected_capability_count": len(selection.selected) if selection else 0,
                "executions_total": len(executions),
                "executions_completed": len(completed),
                "executions_failed": sum(item.execution_status == "failed" for item in executions),
                "executions_rejected": sum(item.execution_status == "rejected" for item in executions),
                "unresolved_gaps": len(diagnosis.missing_fields) if diagnosis else 0,
                "evidence_gaps": sum(item.category.value == "evidence_missing" and not item.resolved for item in gaps),
                "executions_verified": sum(item.verification_status == "passed" for item in verifications),
                "executions_verification_failed": sum(item.verification_status == "failed" for item in verifications),
                "executions_unverified": max(len(executions) - len(verifications), 0),
                "external_worker_runs_total": len(external_worker_runs),
                "external_worker_runs_completed": sum(item.worker_status == "completed" for item in external_worker_runs),
                "external_worker_runs_failed": sum(item.worker_status == "failed" for item in external_worker_runs),
                "external_worker_runs_rejected": sum(item.worker_status == "rejected" for item in external_worker_runs),
                "external_worker_runs_active": sum(item.worker_status in {"queued", "executing", "cancellation_requested"} for item in external_worker_runs),
                "external_worker_runs_cancellation_requested": sum(item.worker_status == "cancellation_requested" for item in external_worker_runs),
                "external_worker_runs_cancelled": sum(item.worker_status == "cancelled" for item in external_worker_runs),
                "external_worker_runs_interrupted": sum(item.worker_status == "interrupted" for item in external_worker_runs),
                "advisor_reviews_total": len(advisor_reviews),
                "advisor_reviews_completed": sum(item.advisor_status == "completed" for item in advisor_reviews),
                "advisor_reviews_unavailable": sum(item.advisor_status == "unavailable" for item in advisor_reviews),
                "advisor_reviews_failed": sum(item.advisor_status == "failed" for item in advisor_reviews),
                "advisor_findings_open": sum(len(item.findings) for item in advisor_reviews if item.advisor_status == "completed"),
                "context_compaction_required": bool(runtime_context and runtime_context.compaction_required),
                "sop_routing_evaluation_status": routing_evaluation.evaluation_status if routing_evaluation else "unavailable",
                "sop_routing_holdouts_passed": bool(routing_evaluation and routing_evaluation.holdout_passed),
            },
            "reasoning_graph": self.store.get_subgraph(mission_id, max_depth=8),
        }

    def _existing_flow(self, mission: MissionArtifact) -> DBOSFlow | None:
        if mission.mission_status not in {"ready_for_confirmation", "confirmed", "executing", "completed", "failed", "stopped", "rolled_back"}:
            return None
        artifacts = self.store.get_by_project(mission.project_id)
        diagnosis = self._first(artifacts, DiagnosisArtifact, mission.artifact_id)
        selection = self._first(artifacts, CapabilitySelectionArtifact, mission.artifact_id)
        sop = self._first(artifacts, DynamicSOPArtifact, mission.artifact_id)
        if not all((diagnosis, selection, sop)):
            return None
        assumptions = [item.artifact_id for item in artifacts if isinstance(item, AssumptionArtifact) and diagnosis.artifact_id in item.parent_ids]
        gaps = [item.artifact_id for item in artifacts if isinstance(item, GapArtifact) and diagnosis.artifact_id in item.parent_ids]
        risks = [item.artifact_id for item in artifacts if isinstance(item, RiskArtifact) and diagnosis.artifact_id in item.parent_ids]
        evidence = [item.artifact_id for item in artifacts if isinstance(item, EvidenceArtifact) and diagnosis.artifact_id in item.parent_ids]
        routing_evaluation = self._routing_evaluation(mission, artifacts)
        return DBOSFlow(
            mission=mission,
            diagnosis=diagnosis,
            selection=selection,
            sop=sop,
            routing_evaluation_id=routing_evaluation.artifact_id if routing_evaluation else "",
            context_snapshot_id=self._runtime_context_id(mission),
            assumption_ids=assumptions,
            gap_ids=gaps,
            risk_ids=risks,
            evidence_ids=evidence,
        )

    def recover_interrupted_executions(self) -> list[ExecutionResultArtifact]:
        return recover_interrupted_runs(self.store)

    def reconcile_execution_verifications(self, mission_id: str = "") -> list[TaskVerificationArtifact]:
        """Reconcile historic provider-backed execution proof without dispatching work."""
        if mission_id:
            self._mission(mission_id)
        return self.execution_service.reconcile_completed_verifications(mission_id=mission_id)

    def _require_persisted_decision(self, mission: MissionArtifact, capability_name: str, sop_id: str) -> None:
        """Require a reviewer decision for the exact compiled task before dispatch."""
        sop = self.store.get(sop_id)
        if not isinstance(sop, DynamicSOPArtifact):
            raise MissionStateError("mission has no compiled Dynamic SOP")
        task_ids = {
            task.task_id
            for phase in sop.phases
            for task in phase.tasks
            if task.capability_name == capability_name
        }
        if not task_ids:
            raise MissionStateError("selected capability has no Dynamic SOP task")
        decisions = [
            item for item in self.store.get_by_project(mission.project_id)
            if isinstance(item, DecisionArtifact) and mission.artifact_id in item.parent_ids
        ]
        decided_task_ids = {
            str(item.metadata.get("task_id") or "")
            for item in decisions
        }
        if not task_ids.intersection(decided_task_ids):
            raise MissionStateError("capability requires a persisted decision for its Dynamic SOP task before execution")

    def _ensure_sop_routing_evaluation(self, mission: MissionArtifact) -> SOPRoutingEvaluationArtifact:
        """Require durable routing evidence before a mission crosses a runtime gate."""
        artifacts = self.store.get_by_project(mission.project_id)
        evaluation = self._routing_evaluation(mission, artifacts)
        if evaluation is None:
            diagnosis = self._first(artifacts, DiagnosisArtifact, mission.artifact_id)
            selection = self._first(artifacts, CapabilitySelectionArtifact, mission.artifact_id)
            sop = self._first(artifacts, DynamicSOPArtifact, mission.artifact_id)
            if not all((diagnosis, selection, sop)):
                raise MissionStateError("mission has no diagnosable Dynamic SOP routing state")
            evaluation = self.routing_evaluator.evaluate(
                mission=mission,
                diagnosis=diagnosis,
                selection=selection,
                sop=sop,
            )
            self.store.add(evaluation)
            self.store.update(mission.model_copy(update={
                "authorization": {
                    **mission.authorization,
                    "sop_routing_evaluation_id": evaluation.artifact_id,
                    "sop_routing_evaluation_status": evaluation.evaluation_status,
                },
            }))
        if evaluation.evaluation_status != "passed" or not evaluation.holdout_passed:
            raise MissionStateError(
                "Dynamic SOP routing evaluation must pass positive, near-negative, and isolated holdout cases before confirmation or execution"
            )
        return evaluation

    @staticmethod
    def _routing_evaluation(
        mission: MissionArtifact,
        artifacts: list[Any],
    ) -> SOPRoutingEvaluationArtifact | None:
        expected_id = str(mission.authorization.get("sop_routing_evaluation_id") or "")
        matches = [
            item
            for item in artifacts
            if isinstance(item, SOPRoutingEvaluationArtifact)
            and item.mission_id == mission.artifact_id
        ]
        if expected_id:
            return next((item for item in matches if item.artifact_id == expected_id), None)
        return max(matches, key=lambda item: item.created_at) if matches else None

    def _runtime_context_id(self, mission: MissionArtifact) -> str:
        value = self._runtime_context(mission, self.store.get_by_project(mission.project_id))
        return value.artifact_id if value is not None else ""

    @staticmethod
    def _runtime_context(mission: MissionArtifact, artifacts: list[Any]) -> RuntimeContextArtifact | None:
        values = [
            item for item in artifacts
            if isinstance(item, RuntimeContextArtifact) and item.mission_id == mission.artifact_id
        ]
        return max(values, key=lambda item: item.created_at) if values else None

    def _mission(self, mission_id: str) -> MissionArtifact:
        item = self.store.get(mission_id)
        if not isinstance(item, MissionArtifact):
            raise MissionNotFoundError("mission was not found in this project")
        return item

    @staticmethod
    def _first(artifacts: list[Any], artifact_class: type[Any], mission_id: str):
        for item in artifacts:
            if isinstance(item, artifact_class) and getattr(item, "mission_id", "") == mission_id:
                return item
        return None

    @staticmethod
    def _view(item: Any) -> dict[str, Any] | None:
        return item.model_dump(mode="json") if item is not None else None

    @staticmethod
    def _mission_view(mission: MissionArtifact) -> dict[str, Any]:
        value = mission.model_dump(mode="json")
        value["status"] = mission.mission_status
        return value

    @staticmethod
    def _execution_view(execution: ExecutionResultArtifact) -> dict[str, Any]:
        value = execution.model_dump(mode="json")
        value["status"] = execution.execution_status
        return value


__all__ = [
    "DBOSService",
    "MissionNotConfirmedError",
    "MissionNotFoundError",
    "MissionStateError",
    "UnauthorizedCapabilityError",
]
