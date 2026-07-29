"""Production REST contract for the project-scoped A/B/C/D growth loop."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.growth_ws import public_event, stream_run_events, validate_event_cursor
from app.api.response import ApiResponse
from app.core.celery_app import get_celery_app, is_celery_broker_available, is_celery_real
from app.core.config import settings
from app.knowledge.capture_adapters import CaptureAdapter, redact_secrets
from app.knowledge.feedback_router import FeedbackRouter
from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeCandidateStatus,
    KnowledgeFailureCode,
    KnowledgeFailurePattern,
    KnowledgeFailureRecord,
    OutputAsset,
    OutputFeedback,
    ProjectKnowledgeProfile,
    ProjectSourcePolicy,
    ExternalWorkerPolicy,
    is_verified_output_status,
)
from app.knowledge.candidate_extraction import CANDIDATE_EXTRACTION_RUN_TYPE, SourceCandidateExtractionService
from app.knowledge.growth_distillation import GrowthDistillationService
from app.knowledge.growth_distillation_revisions import growth_distillation_revision_metadata
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector
from app.knowledge.method_distillation import SOURCE_METHOD_DISTILLATION_RUN_TYPE, SourceMethodDistillationService
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_evolution import METHOD_EVOLUTION_RUN_TYPE, MethodEvolutionService
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry
from app.knowledge.output_evaluator import OutputEvaluator
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.project_profile import ProfileRevisionConflict, ProjectProfileService
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 500
MAX_METADATA_BYTES = 64 * 1024
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
GROWTH_JOB_TYPES = {"growth_daily", "growth_weekly_distillation"}
# These runs are part of the evidence supply chain and need to be auditable in
# the same workspace as the daily and weekly growth cycles.
GROWTH_WORKSPACE_RUN_TYPES = GROWTH_JOB_TYPES | {
    "source_sync",
    "horizon_capture",
    SOURCE_METHOD_DISTILLATION_RUN_TYPE,
    CANDIDATE_EXTRACTION_RUN_TYPE,
    METHOD_EVOLUTION_RUN_TYPE,
}
# The scheduler bit is advisory metadata included on every growth read response.
# A broker probe can exceed its requested timeout when DNS or a Redis endpoint is
# unavailable, so a very short cache turns ordinary metadata reads into repeated
# multi-second network waits.  Commands that submit work deliberately perform a
# fresh broker check; this cache never authorizes execution.
SCHEDULER_AVAILABILITY_CACHE_TTL_SECONDS = 30.0
_scheduler_availability_lock = Lock()
_scheduler_availability_cache: tuple[tuple[object, ...], float, bool] | None = None


def require_growth_enabled() -> None:
    if not settings.KNOWLEDGE_GROWTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "knowledge_growth_disabled",
                "message": "Knowledge growth is disabled by configuration",
                "availability": {"growth": False},
            },
        )


router = APIRouter(tags=["Knowledge Growth"], dependencies=[Depends(require_growth_enabled)])
project_router = APIRouter(prefix="/{project_id}")


def get_growth_repository() -> GrowthRepository:
    return GrowthRepository()


def dispatch_source_method_distillation(project_id: str, run_id: str, *, repository: GrowthRepository) -> dict[str, str]:
    """Load the worker adapter only when an HTTP request actually submits work."""
    from app.tasks.method_distillation_tasks import dispatch_source_method_distillation as dispatch

    return dispatch(project_id, run_id, repository=repository)


def dispatch_source_candidate_extraction(project_id: str, run_id: str, *, repository: GrowthRepository) -> dict[str, str]:
    """Load the detached five-way extractor only when it is explicitly requested."""
    from app.tasks.candidate_extraction_tasks import dispatch_source_candidate_extraction as dispatch

    return dispatch(project_id, run_id, repository=repository)


class GrowthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfilePatch(GrowthRequest):
    expected_revision: int = Field(ge=0)
    research_domains: list[str] | None = Field(default=None, max_length=100)
    user_role: str | None = Field(default=None, max_length=200)
    primary_output_types: list[str] | None = Field(default=None, max_length=50)
    target_audiences: list[str] | None = Field(default=None, max_length=100)
    preferred_channels: list[str] | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=32)
    content_voice: str | None = Field(default=None, max_length=1_000)
    evidence_threshold: int | None = Field(default=None, ge=0, le=100)
    automatic_publication_policy: str | None = Field(default=None, max_length=100)
    method_promotion_policy: str | None = Field(default=None, max_length=100)
    source_policy: ProjectSourcePolicy | None = None
    external_worker_policy: ExternalWorkerPolicy | None = None


class SourceCreateRequest(GrowthRequest):
    source_type: str = Field(min_length=1, max_length=100)
    origin: str = Field(default="", max_length=2_000)
    raw_content: str = Field(min_length=1, max_length=2_000_000)
    vault_path: str = Field(default="", max_length=512)
    trust_level: str = Field(default="untrusted", max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_metadata(self) -> "SourceCreateRequest":
        _validate_metadata_size(self.metadata)
        return self


class MethodProposalRequest(GrowthRequest):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    body: str = Field(min_length=1, max_length=100_000)
    source_output_ids: list[str] = Field(min_length=3, max_length=100)
    manifest: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_manifest(self) -> "MethodProposalRequest":
        _validate_metadata_size(self.manifest)
        return self


class MethodReviewRequest(GrowthRequest):
    # The evaluator derives its decision from persisted outputs and evaluations.
    # These optional fields preserve supplied telemetry for the audit record.
    comparable_uses: int = Field(default=0, ge=0, le=10_000)
    average_quality: float = Field(default=0, ge=0, le=100)
    groundedness: float = Field(default=0, ge=0, le=1)
    security_failures: int = Field(default=0, ge=0, le=10_000)
    regression_failures: int = Field(default=0, ge=0, le=10_000)


class MethodEvolutionRequest(GrowthRequest):
    candidate_body: str = Field(min_length=1, max_length=100_000)
    candidate_manifest: dict[str, Any] = Field(default_factory=dict)
    supporting_output_ids: list[str] = Field(min_length=3, max_length=100)
    mutation_dimension: Literal[
        "body",
        "trigger_contract",
        "applicability",
        "exclusions",
        "steps",
        "evidence_rules",
        "failure_handling",
    ]
    rationale: str = Field(min_length=24, max_length=4_000)
    idempotency_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def bound_experiment(self) -> "MethodEvolutionRequest":
        _validate_metadata_size(self.candidate_manifest)
        self.supporting_output_ids = list(
            dict.fromkeys(value.strip() for value in self.supporting_output_ids if value.strip())
        )
        if len(self.supporting_output_ids) < 3:
            raise ValueError("supporting_output_ids must contain three distinct non-empty values")
        self.rationale = self.rationale.strip()
        if len(self.rationale) < 24:
            raise ValueError("rationale must explain the mutation in at least 24 characters")
        return self


class SourceMethodDistillationRequest(GrowthRequest):
    source_id: str = Field(min_length=1, max_length=128)
    candidate_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def bound_candidate_selection(self) -> "SourceMethodDistillationRequest":
        self.candidate_ids = [item.strip() for item in self.candidate_ids]
        if any(not item for item in self.candidate_ids):
            raise ValueError("candidate_ids must not contain blank values")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("candidate_ids must be distinct")
        return self


class SourceCandidateExtractionRequest(GrowthRequest):
    source_id: str = Field(min_length=1, max_length=128)


class CandidateReviewRequest(GrowthRequest):
    decision: Literal["accepted", "rejected"]
    review_note: str = Field(default="", max_length=2_000)


class MethodPublishRequest(GrowthRequest):
    expected_profile_revision: int | None = Field(default=None, ge=0)


class MutationReasonRequest(GrowthRequest):
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def normalize_reason(self) -> "MutationReasonRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be blank")
        return self


class OutputRegisterRequest(GrowthRequest):
    kind: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=500)
    mime_type: str = Field(default="text/markdown", max_length=200)
    content_hash: str = Field(min_length=64, max_length=128)
    vault_path: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=8_000_000)
    run_id: str = Field(default="", max_length=128)
    method_revision_id: str = Field(default="", max_length=128)
    context_revision: str = Field(default="", max_length=128)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    page_refs: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_metadata(self) -> "OutputRegisterRequest":
        _validate_metadata_size(self.metadata)
        return self


class OutputEvaluationRequest(GrowthRequest):
    groundedness: float = Field(ge=0, le=1)
    task_fit: float = Field(ge=0, le=1)
    usefulness: float = Field(ge=0, le=1)
    coherence: float = Field(ge=0, le=1)
    format_quality: float = Field(ge=0, le=1)
    findings: list[str] = Field(default_factory=list, max_length=100)


class OutputEvidenceRequest(GrowthRequest):
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    page_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_evidence_reference(self) -> "OutputEvidenceRequest":
        self.source_ids = list(dict.fromkeys(value.strip() for value in self.source_ids if value.strip()))
        self.page_ids = list(dict.fromkeys(value.strip() for value in self.page_ids if value.strip()))
        if not self.source_ids and not self.page_ids:
            raise ValueError("at least one source_ids or page_ids reference is required")
        return self


class FeedbackRequest(GrowthRequest):
    feedback_type: FeedbackType
    actor_id: str = Field(default="", max_length=200)
    rating: int | None = Field(default=None, ge=0, le=100)
    correction: str = Field(default="", max_length=100_000)
    comment: str = Field(default="", max_length=20_000)


class ReviewRequest(GrowthRequest):
    target_type: Literal["feedback", "method_detection"]
    target_id: str = Field(default="", max_length=128)
    minimum_uses: int = Field(default=3, ge=3, le=100)


class ScheduleRequest(GrowthRequest):
    job_type: Literal["growth_daily", "growth_weekly_distillation"]
    cron: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="Asia/Shanghai", max_length=100)


class RunRequest(GrowthRequest):
    job_type: Literal["growth_daily", "growth_weekly_distillation"]
    idempotency_key: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=32)
    week: str = Field(default="", max_length=32)
    source_cutoff: str = Field(default="", max_length=64)


class FailureCreateRequest(GrowthRequest):
    code: KnowledgeFailureCode
    diagnostic_pattern: KnowledgeFailurePattern | None = None
    secondary_diagnostic_patterns: list[KnowledgeFailurePattern] = Field(default_factory=list, max_length=2)
    severity: Literal["info", "warning", "error", "critical"] = "error"
    summary: str = Field(min_length=1, max_length=2_000)
    run_id: str = Field(default="", max_length=128)
    event_sequence: int | None = Field(default=None, ge=1)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    root_cause: str = Field(default="", max_length=8_000)
    minimal_structural_fix: str = Field(default="", max_length=8_000)
    retryable: bool = False


class FailureResolveRequest(GrowthRequest):
    resolution_note: str = Field(min_length=1, max_length=2_000)
    retry_scheduled: bool = False

    @model_validator(mode="after")
    def normalize_resolution_note(self) -> "FailureResolveRequest":
        self.resolution_note = self.resolution_note.strip()
        if not self.resolution_note:
            raise ValueError("resolution_note must not be blank")
        return self


@project_router.get("/profile")
def read_profile(
    project_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    profile = _guard(lambda: repo.get_profile(project_id))
    value = profile or ProjectKnowledgeProfile(project_id=project_id).model_dump(mode="json")
    return _ok(request, repo, project_id, {"profile": value})


@project_router.patch("/profile")
def patch_profile(
    project_id: str,
    payload: ProfilePatch,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    values = {
        key: value
        for key, value in payload.model_dump(exclude={"expected_revision"}).items()
        if value is not None
    }
    saved = _guard(
        lambda: ProjectProfileService(repo).update_profile(
            project_id,
            values,
            expected_revision=payload.expected_revision,
            actor_id=_actor(request),
        ).model_dump(mode="json")
    )
    return _ok(request, repo, project_id, {"profile": saved})


@project_router.get("/growth/assets")
@project_router.get("/assets", include_in_schema=False)
def list_assets(
    project_id: str,
    request: Request,
    stage: Literal["A", "B", "C", "D", "review"] | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    items: list[dict[str, Any]] = []
    if stage in {None, "A"}:
        items.extend({**_public_source(item), "stage": "A", "asset_type": "source"} for item in _guard(lambda: repo.list_sources(project_id)))
    if stage in {None, "B"}:
        items.extend({**_public_record(item), "stage": "B", "asset_type": "page"} for item in _guard(lambda: repo.list_pages(project_id)))
    if stage in {None, "C"}:
        items.extend({**_public_record(item), "stage": "C", "asset_type": "method"} for item in _guard(lambda: repo.list_methods(project_id, limit=MAX_PAGE_SIZE)))
    if stage in {None, "D"}:
        items.extend({**_public_record(item), "stage": "D", "asset_type": "output"} for item in _guard(lambda: repo.list_outputs(project_id, limit=MAX_PAGE_SIZE)))
    if stage in {None, "review"}:
        items.extend({**_public_candidate(item), "stage": "review", "asset_type": "candidate"} for item in _guard(lambda: repo.list_candidates(project_id, limit=MAX_PAGE_SIZE)))
        items.extend({**_public_record(item), "stage": "review", "asset_type": "feedback"} for item in _guard(lambda: repo.list_feedback(project_id, limit=MAX_PAGE_SIZE)))
        items.extend({**_public_proposal(item), "stage": "review", "asset_type": "wiki_proposal"} for item in _guard(lambda: repo.list_proposals(project_id, limit=MAX_PAGE_SIZE)))
        items.extend({**_public_method_proposal(item), "stage": "review", "asset_type": "method_proposal"} for item in _guard(lambda: repo.list_method_proposals(project_id, limit=MAX_PAGE_SIZE)))
    page, pagination = _paginate(items, limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"project_id": project_id, "stage": stage or "all", "items": page, "pagination": pagination})


@project_router.post("/sources", status_code=201)
def create_source(
    project_id: str,
    payload: SourceCreateRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    normalized = _guard(
        lambda: CaptureAdapter().normalize(
            project_id=project_id,
            source_type=payload.source_type,
            origin=payload.origin,
            content=payload.raw_content,
            metadata=payload.metadata,
            trust_level=payload.trust_level,
            vault_path=payload.vault_path,
        )
    )
    result = _guard(
        lambda: WikiCommandService(repo).capture_source(
            normalized.model_dump(mode="json"), actor_id=_actor(request)
        )
    )
    return _ok(
        request,
        repo,
        project_id,
        {"source": _public_source(result["source"]), "created": result["created"], "run_id": result["run_id"]},
    )


@project_router.get("/sources/{source_id}/triage")
def read_source_triage(
    project_id: str,
    source_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    source = _guard(lambda: repo.get_source(project_id, source_id))
    if not source:
        raise _http_error(404, "growth_resource_not_found", "source not found in project")
    records = [item for item in _guard(lambda: repo.list_triage(project_id, limit=MAX_PAGE_SIZE)) if item.get("source_id") == source_id]
    return _ok(
        request,
        repo,
        project_id,
        {"source_id": source_id, "triage": _public_record(records[0]) if records else None, "status": "completed" if records else "not_run"},
    )


@project_router.post("/sources/{source_id}/triage")
def triage_source(
    project_id: str,
    source_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    triage = _guard(lambda: SourceTriageService(repo).triage_source(project_id, source_id))
    return _ok(request, repo, project_id, {"triage": _public_record(triage)})


@project_router.get("/methods")
def list_methods(
    project_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_methods(project_id, status=status, limit=MAX_PAGE_SIZE))
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"methods": page, "pagination": pagination})


@project_router.get("/methods/proposals")
def list_method_proposals(
    project_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_method_proposals(project_id, status=status, limit=MAX_PAGE_SIZE))
    page, pagination = _paginate([_public_method_proposal(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"proposals": page, "pagination": pagination})


@project_router.get("/methods/proposals/{proposal_id}")
def read_method_proposal(
    project_id: str,
    proposal_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    proposal = _guard(lambda: repo.get_method_proposal(project_id, proposal_id))
    if not proposal:
        raise _http_error(404, "growth_resource_not_found", "method proposal not found in project")
    return _ok(request, repo, project_id, {"proposal": _public_record(proposal)})


@project_router.get("/methods/{method_id}/experiments")
def list_method_evolution_experiments(
    project_id: str,
    method_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    if not _guard(lambda: repo.get_method(project_id, method_id)):
        raise _http_error(404, "growth_resource_not_found", "method not found in project")
    records = _guard(
        lambda: repo.list_method_evolution_runs(
            project_id, method_id=method_id, status=status, limit=MAX_PAGE_SIZE
        )
    )
    page, pagination = _paginate(
        [_public_record(item) for item in records], limit=limit, cursor=cursor
    )
    return _ok(
        request,
        repo,
        project_id,
        {"method_id": method_id, "experiments": page, "pagination": pagination},
    )


@project_router.get("/methods/experiments/{experiment_id}")
def read_method_evolution_experiment(
    project_id: str,
    experiment_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    experiment = _guard(lambda: repo.get_method_evolution_run(project_id, experiment_id))
    if not experiment:
        raise _http_error(
            404,
            "growth_resource_not_found",
            "method evolution experiment not found in project",
        )
    return _ok(request, repo, project_id, {"experiment": _public_record(experiment)})


@project_router.post("/methods/{method_id}/experiments", status_code=201)
def start_method_evolution_experiment(
    project_id: str,
    method_id: str,
    payload: MethodEvolutionRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    experiment, idempotent = _guard(
        lambda: MethodEvolutionService(repo).start(
            project_id=project_id,
            method_id=method_id,
            candidate_body=payload.candidate_body,
            candidate_manifest=payload.candidate_manifest,
            supporting_output_ids=payload.supporting_output_ids,
            mutation_dimension=payload.mutation_dimension,
            rationale=payload.rationale,
            idempotency_key=payload.idempotency_key,
            actor_id=_actor(request),
        )
    )
    return _ok(
        request,
        repo,
        project_id,
        {
            "experiment": _public_record(experiment),
            "idempotent": idempotent,
            "publication_status": "review_required"
            if experiment.get("decision") == "retain"
            else "not_publishable",
        },
    )


@project_router.post("/methods", status_code=201)
def propose_method(
    project_id: str,
    payload: MethodProposalRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    output_ids = list(dict.fromkeys(payload.source_output_ids))
    if len(output_ids) < 3:
        raise _http_error(400, "growth_invalid_request", "three distinct source outputs are required")
    for output_id in output_ids:
        output = _guard(lambda output_id=output_id: repo.get_output(project_id, output_id))
        if not output:
            raise _http_error(404, "growth_resource_not_found", "source output not found in project")
        if not is_verified_output_status(output.get("status")):
            raise _http_error(409, "growth_gate_not_satisfied", "method proposals require verified outputs")
    proposal = _guard(
        lambda: MethodDetector(repo).create_proposal(
            project_id,
            payload.slug,
            payload.body,
            output_ids,
            {**payload.manifest, "task_family": payload.slug},
        )
    )
    return _ok(request, repo, project_id, {"proposal": _public_record(proposal), "publication_status": "proposal_only"})


@project_router.post("/methods/distill", status_code=202)
def distill_source_methods(
    project_id: str,
    payload: SourceMethodDistillationRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    """Submit review-only RIA-TV++ proposal generation from one admitted source."""
    project_id = _enforce_growth_access(request, project_id, write=True)
    run = _guard(
        lambda: SourceMethodDistillationService(repo).submit(
            project_id=project_id,
            source_id=payload.source_id,
            actor_id=_actor(request),
            trigger="http",
            candidate_ids=payload.candidate_ids,
        )
    )
    try:
        execution = dispatch_source_method_distillation(project_id, str(run["id"]), repository=repo)
    except Exception as exc:
        repo.update_run_status(
            project_id,
            str(run["id"]),
            RunStatus.FAILED,
            error=str(exc)[:2_000],
            output_refs={
                "failure": {
                    "category": "transient_dependency",
                    "code": "source_method_distillation_dispatch_failed",
                    "retryable": True,
                }
            },
        )
        raise _translate_error(exc) from exc
    persisted = _guard(lambda: repo.get_run(project_id, str(run["id"])))
    return _ok(
        request,
        repo,
        project_id,
        {
            "run": _public_record(persisted),
            "proposals": [],
            "publication_status": "proposal_only",
            "execution": execution,
        },
    )


@project_router.get("/candidates")
def list_candidates(
    project_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    source_id: str = Query(default="", max_length=128),
    run_id: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(
        lambda: repo.list_candidates(
            project_id,
            status=status,
            source_id=source_id,
            extraction_run_id=run_id,
            limit=MAX_PAGE_SIZE,
        )
    )
    page, pagination = _paginate([_public_candidate(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"candidates": page, "pagination": pagination})


@project_router.get("/candidates/{candidate_id}")
def read_candidate(
    project_id: str,
    candidate_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    candidate = _guard(lambda: repo.get_candidate(project_id, candidate_id))
    if not candidate:
        raise _http_error(404, "growth_resource_not_found", "candidate not found in project")
    return _ok(request, repo, project_id, {"candidate": _public_record(candidate)})


@project_router.post("/candidates/extract", status_code=202)
def extract_source_candidates(
    project_id: str,
    payload: SourceCandidateExtractionRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    """Submit five independent, review-only candidate extractors for one source."""
    project_id = _enforce_growth_access(request, project_id, write=True)
    run = _guard(
        lambda: SourceCandidateExtractionService(repo).submit(
            project_id=project_id,
            source_id=payload.source_id,
            actor_id=_actor(request),
            trigger="http",
        )
    )
    try:
        execution = dispatch_source_candidate_extraction(project_id, str(run["id"]), repository=repo)
    except Exception as exc:
        repo.update_run_status(
            project_id,
            str(run["id"]),
            RunStatus.FAILED,
            error=str(exc)[:2_000],
            output_refs={
                "failure": {
                    "category": "transient_dependency",
                    "code": "candidate_extraction_dispatch_failed",
                    "retryable": True,
                },
                "publication_status": "review_only",
            },
        )
        raise _translate_error(exc) from exc
    persisted = _guard(lambda: repo.get_run(project_id, str(run["id"])))
    return _ok(
        request,
        repo,
        project_id,
        {
            "run": _public_record(persisted),
            "candidates": [],
            "publication_status": "review_only",
            "execution": execution,
        },
    )


@project_router.post("/candidates/{candidate_id}/review")
def review_candidate(
    project_id: str,
    candidate_id: str,
    payload: CandidateReviewRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    candidate = _guard_state_transition(
        lambda: repo.review_candidate(
            project_id,
            candidate_id,
            decision=KnowledgeCandidateStatus(payload.decision),
            actor_id=_actor(request),
            review_note=payload.review_note,
        ),
        "candidate review state conflict",
    )
    return _ok(
        request,
        repo,
        project_id,
        {"candidate": _public_record(candidate), "publication_status": "review_only"},
    )


@project_router.get("/methods/{method_id}/revisions")
def list_method_revisions(
    project_id: str,
    method_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    if not _guard(lambda: repo.get_method(project_id, method_id)):
        raise _http_error(404, "growth_resource_not_found", "method not found in project")
    records = _guard(
        lambda: repo.list_method_revisions(
            project_id,
            method_id,
            limit=MAX_PAGE_SIZE,
        )
    )
    page, pagination = _paginate(records, limit=limit, cursor=cursor)
    return _ok(
        request,
        repo,
        project_id,
        {
            "method_id": method_id,
            "revisions": [_public_record(item) for item in page],
            "pagination": pagination,
        },
    )


@project_router.post("/methods/proposals/{proposal_id}/review")
def review_method_proposal(
    project_id: str,
    proposal_id: str,
    payload: MethodReviewRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    proposal = _guard(lambda: repo.get_method_proposal(project_id, proposal_id))
    if not proposal:
        raise _http_error(404, "growth_resource_not_found", "method proposal not found in project")
    evaluation = _guard(lambda: MethodEvaluator(repo).evaluate(proposal, **payload.model_dump()))
    return _ok(request, repo, project_id, {"proposal_id": proposal_id, "evaluation": evaluation})


@project_router.post("/methods/proposals/{proposal_id}/publish")
def publish_method_proposal(
    project_id: str,
    proposal_id: str,
    payload: MethodPublishRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    profile = _guard(lambda: repo.get_profile(project_id)) or ProjectKnowledgeProfile(project_id=project_id).model_dump(mode="json")
    if payload.expected_profile_revision is not None and int(profile.get("revision") or 0) != payload.expected_profile_revision:
        raise _http_error(409, "growth_revision_conflict", "project profile revision changed")
    policy = str(profile.get("method_promotion_policy") or "gated")
    method = _guard(
        lambda: MethodGate(repo).publish_prompt_method(
            project_id=project_id,
            proposal_id=proposal_id,
            actor_id=_actor(request),
            policy_allows=policy not in {"disabled", "manual_only"},
        )
    )
    return _ok(request, repo, project_id, {"method": _public_record(method), "publication_status": "published"})


@project_router.post("/methods/{method_id}/deprecate")
def deprecate_method(
    project_id: str,
    method_id: str,
    payload: MutationReasonRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    method = _guard(lambda: repo.get_method(project_id, method_id))
    if not method:
        raise _http_error(404, "growth_resource_not_found", "method not found in project")
    if method.get("status") == "deprecated":
        return _ok(
            request,
            repo,
            project_id,
            {"method": _public_record(method), "idempotent": True},
        )
    if method.get("status") != "published":
        raise _http_error(
            409,
            "growth_state_conflict",
            "only a published method can be deprecated",
        )
    deprecated = _guard_state_transition(
        lambda: MethodRegistry(repo, _vault_root()).deprecate(
            project_id,
            method_id,
            actor_id=_actor(request),
            reason=payload.reason,
        ),
        "method deprecation state conflict",
    )
    return _ok(
        request,
        repo,
        project_id,
        {"method": _public_record(deprecated), "idempotent": False},
    )


@project_router.get("/methods/{method_id}/resolve")
def resolve_method(
    project_id: str,
    method_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    method = _guard(lambda: repo.get_method(project_id, method_id))
    if not method:
        raise _http_error(404, "growth_resource_not_found", "method not found in project")
    revision = None
    if method.get("status") == "published" and method.get("active_revision_id"):
        revision = _guard(lambda: repo.get_method_revision(project_id, method["active_revision_id"]))
    experiments = _guard(
        lambda: repo.list_method_evolution_runs(
            project_id, method_id=method_id, limit=20
        )
    )
    return _ok(
        request,
        repo,
        project_id,
        {
            "method": _public_record(method),
            "revision": _public_record(revision) if revision else None,
            "evolution_experiments": [_public_record(item) for item in experiments],
            "resolution_status": "available" if revision else "unavailable",
        },
    )


@project_router.get("/outputs")
def list_outputs(
    project_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_outputs(project_id, status=status, limit=MAX_PAGE_SIZE))
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"outputs": page, "pagination": pagination})


@project_router.get("/outputs/{output_id}")
def read_output(
    project_id: str,
    output_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    output = _guard(lambda: repo.get_output(project_id, output_id))
    if not output:
        raise _http_error(404, "growth_resource_not_found", "output not found in project")
    evaluations = _guard(lambda: repo.list_output_evaluations(project_id, output_id=output_id, limit=MAX_PAGE_SIZE))
    feedback = _guard(lambda: repo.list_feedback(project_id, output_id=output_id, limit=MAX_PAGE_SIZE))
    evidence = _guard(lambda: repo.list_output_evidence_references(project_id, output_id))
    return _ok(
        request,
        repo,
        project_id,
        {
            "output": _public_record(output),
            "evidence": evidence,
            "evaluations": [_public_record(item) for item in evaluations],
            "feedback": [_public_record(item) for item in feedback],
        },
    )


@project_router.get("/outputs/{output_id}/content")
def read_output_content(
    project_id: str,
    output_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    content = _guard(
        lambda: OutputRegistry(repo, _vault_root()).read_content(
            project_id,
            output_id,
        )
    )
    return _ok(request, repo, project_id, {"content": _public_record(content)})


@project_router.post("/outputs", status_code=201)
def register_output(
    project_id: str,
    payload: OutputRegisterRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise _http_error(400, "invalid_output_encoding", "content_base64 is invalid") from exc
    output = _guard(
        lambda: OutputAsset(
            project_id=project_id,
            **payload.model_dump(exclude={"content_base64", "metadata"}),
            metadata=redact_secrets(payload.metadata),
        )
    )
    result = _guard(
        lambda: OutputRegistry(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).register_content(output, content)
    )
    return _ok(request, repo, project_id, {"output": _public_record(result)})


@project_router.post("/outputs/{output_id}/evaluate")
def evaluate_output(
    project_id: str,
    output_id: str,
    payload: OutputEvaluationRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    result = _guard(
        lambda: OutputEvaluator(repo).evaluate(
            project_id=project_id,
            output_id=output_id,
            components=payload.model_dump(exclude={"findings"}),
            findings=payload.findings,
        )
    )
    return _ok(request, repo, project_id, {"evaluation": _public_record(result)})


@project_router.post("/outputs/{output_id}/evidence")
def attach_output_evidence(
    project_id: str,
    output_id: str,
    payload: OutputEvidenceRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    result = _guard_state_transition(
        lambda: repo.attach_output_evidence_references(
            project_id,
            output_id,
            source_ids=payload.source_ids,
            page_ids=payload.page_ids,
        ),
        "output evidence attachment state conflict",
    )
    evidence = _guard(lambda: repo.list_output_evidence_references(project_id, output_id))
    return _ok(request, repo, project_id, {"output": _public_record(result), "evidence": evidence})


@project_router.post("/outputs/{output_id}/feedback", status_code=201)
def add_feedback(
    project_id: str,
    output_id: str,
    payload: FeedbackRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    values = payload.model_dump()
    values["actor_id"] = values["actor_id"] or _actor(request)
    feedback = _guard(
        lambda: repo.add_output_feedback(
            OutputFeedback(project_id=project_id, output_id=output_id, **values)
        )
    )
    return _ok(request, repo, project_id, {"feedback": _public_record(feedback)})


@project_router.post("/outputs/{output_id}/file")
def file_output(
    project_id: str,
    output_id: str,
    payload: MutationReasonRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    output = _guard(lambda: repo.get_output(project_id, output_id))
    if not output:
        raise _http_error(404, "growth_resource_not_found", "output not found in project")
    idempotent = output.get("status") == "filed"
    if output.get("status") not in {"accepted", "filed"}:
        raise _http_error(
            409,
            "growth_state_conflict",
            "only an accepted output can be filed",
        )
    filed = _guard_state_transition(
        lambda: OutputRegistry(repo, _vault_root()).file_output(
            project_id,
            output_id,
            actor_id=_actor(request),
            reason=payload.reason,
        ),
        "output filing state conflict",
    )
    _assert_output_immutable(output, filed)
    return _ok(
        request,
        repo,
        project_id,
        {"output": _public_record(filed), "idempotent": idempotent},
    )


@project_router.get("/feedback")
def list_feedback(
    project_id: str,
    request: Request,
    output_id: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_feedback(project_id, output_id=output_id, limit=MAX_PAGE_SIZE))
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"feedback": page, "pagination": pagination})


@project_router.post("/feedback/{feedback_id}/process")
def process_feedback(
    project_id: str,
    feedback_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    result = _guard(lambda: FeedbackRouter(repo).process(project_id, feedback_id))
    return _ok(request, repo, project_id, {"review": _public_record(result)})


@project_router.get("/growth/lineage")
@project_router.get("/lineage", include_in_schema=False)
def list_lineage(
    project_id: str,
    request: Request,
    relation: str = Query(default="", max_length=100),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_lineage(project_id, relation=relation, limit=MAX_PAGE_SIZE))
    endpoints = _guard(
        lambda: repo.lineage_endpoints(
            project_id,
            {
                endpoint_id
                for item in records
                for endpoint_id in (str(item.get("from_id") or ""), str(item.get("to_id") or ""))
                if endpoint_id
            },
        )
    )
    values = [
        _public_record(
            {
                **item,
                "from_type": endpoints.get(str(item.get("from_id") or ""), {}).get("type", "unknown"),
                "to_type": endpoints.get(str(item.get("to_id") or ""), {}).get("type", "unknown"),
            }
        )
        for item in records
    ]
    page, pagination = _paginate(values, limit=limit, cursor=cursor)
    visible_ids = {
        endpoint_id
        for edge in page
        for endpoint_id in (str(edge.get("from_id") or ""), str(edge.get("to_id") or ""))
        if endpoint_id
    }
    nodes = [
        _public_record(endpoints[endpoint_id])
        for endpoint_id in sorted(visible_ids)
        if endpoint_id in endpoints
    ]
    return _ok(
        request,
        repo,
        project_id,
        {"project_id": project_id, "edges": page, "nodes": nodes, "pagination": pagination},
    )


@project_router.get("/growth/summary")
@project_router.get("/summary", include_in_schema=False)
def growth_summary(
    project_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    result = _guard(lambda: _summary(repo, project_id))
    return _ok(request, repo, project_id, result)


@project_router.post("/growth/review")
def growth_review(
    project_id: str,
    payload: ReviewRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    if payload.target_type == "feedback":
        if not payload.target_id:
            raise _http_error(400, "growth_invalid_request", "target_id is required for feedback review")
        review = _guard(lambda: FeedbackRouter(repo).process(project_id, payload.target_id))
    else:
        review = {
            "target_type": "method_detection",
            "proposals": _guard(
                lambda: MethodDetector(repo).detect(project_id, minimum_uses=payload.minimum_uses)
            ),
        }
    return _ok(request, repo, project_id, {"review": _public_record(review)})


@project_router.get("/schedules")
def list_schedules(
    project_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = [item for item in _guard(lambda: repo.list_schedules(project_id)) if item.get("job_type") in GROWTH_JOB_TYPES]
    available = _scheduler_available()
    values = [
        {
            **_public_record(item),
            "scheduler_available": available,
            "last_result": _public_record(repo.latest_run_for_type(project_id, item["job_type"])),
        }
        for item in records
    ]
    page, pagination = _paginate(values, limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"schedules": page, "pagination": pagination})


@project_router.post("/schedules", status_code=201)
def configure_schedule(
    project_id: str,
    payload: ScheduleRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
        raise _http_error(503, "growth_dependency_unavailable", "knowledge schedules feature is disabled")
    schedule = _guard(
        lambda: WikiCommandService(repo).configure_schedule(
            project_id=project_id,
            job_type=payload.job_type,
            cron=payload.cron,
            timezone_name=payload.timezone,
        )
    )
    return _ok(request, repo, project_id, {"schedule": _public_record(schedule)})


@project_router.get("/runs")
def list_runs(
    project_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = [
        item
        for item in _guard(lambda: repo.list_runs(project_id, limit=MAX_PAGE_SIZE))
        if item.get("run_type") in GROWTH_WORKSPACE_RUN_TYPES
    ]
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"runs": page, "pagination": pagination})


@project_router.get("/capture-attempts")
def list_capture_attempts(
    project_id: str,
    request: Request,
    run_id: str = Query(default="", max_length=128),
    source_id: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    """Expose the privacy-bounded evidence capture ledger for one project."""
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(
        lambda: repo.list_source_capture_attempts(
            project_id,
            run_id=run_id,
            source_id=source_id,
            limit=MAX_PAGE_SIZE,
        )
    )
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(
        request,
        repo,
        project_id,
        {
            "capture_attempts": page,
            "pagination": pagination,
        },
    )


@project_router.get("/failures")
def list_failures(
    project_id: str,
    request: Request,
    status: str = Query(default="", max_length=32),
    run_id: str = Query(default="", max_length=128),
    diagnostic_pattern: KnowledgeFailurePattern | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(
        lambda: repo.list_failure_records(
            project_id,
            status=status,
            run_id=run_id,
            diagnostic_pattern=diagnostic_pattern.value if diagnostic_pattern else "",
            limit=MAX_PAGE_SIZE,
        )
    )
    page, pagination = _paginate([_public_record(item) for item in records], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"failures": page, "pagination": pagination})


@project_router.get("/failures/{failure_id}")
def read_failure(
    project_id: str,
    failure_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    failure = _guard(lambda: repo.get_failure_record(project_id, failure_id))
    if not failure:
        raise _http_error(404, "growth_resource_not_found", "failure record not found in project")
    return _ok(request, repo, project_id, {"failure": _public_record(failure)})


@project_router.post("/failures", status_code=201)
def create_failure(
    project_id: str,
    payload: FailureCreateRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    failure = _guard(
        lambda: repo.create_failure_record(
            KnowledgeFailureRecord(project_id=project_id, **payload.model_dump())
        )
    )
    return _ok(request, repo, project_id, {"failure": _public_record(failure)})


@project_router.post("/failures/{failure_id}/resolve")
def resolve_failure(
    project_id: str,
    failure_id: str,
    payload: FailureResolveRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    failure = _guard_state_transition(
        lambda: repo.resolve_failure_record(
            project_id,
            failure_id,
            actor_id=_actor(request),
            resolution_note=payload.resolution_note,
            retry_scheduled=payload.retry_scheduled,
        ),
        "failure resolution state conflict",
    )
    return _ok(request, repo, project_id, {"failure": _public_record(failure)})


@project_router.post("/runs")
def start_run(
    project_id: str,
    payload: RunRequest,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    input_refs = {
        key: value
        for key, value in {
            "date": payload.date,
            "week": payload.week,
            "source_cutoff": payload.source_cutoff,
        }.items()
        if value
    }
    result = _guard(
        lambda: _start_run(
            repo,
            project_id=project_id,
            job_type=payload.job_type,
            idempotency_key=payload.idempotency_key,
            input_refs=input_refs,
            actor_id=_actor(request),
        )
    )
    return _ok(request, repo, project_id, {"run": _public_record(result)})


@project_router.get("/runs/{run_id}/events")
def list_run_events(
    project_id: str,
    run_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    run = _guard(lambda: repo.get_run(project_id, run_id))
    if not run:
        raise _http_error(404, "growth_resource_not_found", "growth run not found in project")
    validate_event_cursor(repo, project_id=project_id, run_id=run_id, after_sequence=after_sequence)
    events = _guard(
        lambda: repo.list_run_events(
            project_id=project_id,
            run_id=run_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    )
    values = [public_event(item, run) for item in events]
    latest = repo.latest_run_event_sequence(project_id=project_id, run_id=run_id)
    return _ok(
        request,
        repo,
        project_id,
        {
            "run": _public_record(run),
            "events": values,
            "pagination": {
                "limit": limit,
                "after_sequence": after_sequence,
                "next_sequence": values[-1]["sequence"] if values and values[-1]["sequence"] < latest else None,
                "count": len(values),
            },
        },
    )


@project_router.get("/runs/{run_id}/events/stream")
async def stream_events(
    project_id: str,
    run_id: str,
    request: Request,
    after_sequence: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    run = _guard(lambda: repo.get_run(project_id, run_id))
    if not run:
        raise _http_error(404, "growth_resource_not_found", "growth run not found in project")
    selected = after_sequence
    if selected is None:
        header = request.headers.get("last-event-id", "0").strip() or "0"
        if not header.isdigit():
            raise _http_error(400, "growth_invalid_cursor", "Last-Event-ID must be a non-negative integer")
        selected = int(header)
    validate_event_cursor(repo, project_id=project_id, run_id=run_id, after_sequence=selected)
    return StreamingResponse(
        stream_run_events(
            request,
            repo,
            project_id=project_id,
            run_id=run_id,
            after_sequence=selected,
            page_limit=limit,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@project_router.get("/distillations")
def list_distillations(
    project_id: str,
    request: Request,
    kind: Literal["daily", "weekly"] | None = None,
    include_history: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=16),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_growth_distillations(project_id, kind=kind or "", limit=MAX_PAGE_SIZE))
    metadata = growth_distillation_revision_metadata(repo, records, vault_root=str(settings.OBSIDIAN_VAULT_ROOT or ""))
    visible = [
        {**record, **metadata.get(str(record.get("id") or ""), {"current": True, "revision_count": 1})}
        for record in records
        if include_history or bool(metadata.get(str(record.get("id") or ""), {"current": True})["current"])
    ]
    page, pagination = _paginate([_public_record(item) for item in visible], limit=limit, cursor=cursor)
    return _ok(request, repo, project_id, {"distillations": page, "pagination": pagination})


@project_router.get("/distillations/{distillation_id}")
def read_distillation(
    project_id: str,
    distillation_id: str,
    request: Request,
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id)
    records = _guard(lambda: repo.list_growth_distillations(project_id, limit=MAX_PAGE_SIZE))
    record = next((item for item in records if item.get("id") == distillation_id), None)
    if not record:
        raise _http_error(404, "growth_resource_not_found", "distillation not found in project")
    metadata = growth_distillation_revision_metadata(repo, records, vault_root=str(settings.OBSIDIAN_VAULT_ROOT or ""))
    revision = metadata.get(str(record.get("id") or ""), {"current": True, "revision_count": 1})
    return _ok(request, repo, project_id, {"distillation": _public_record({**record, **revision})})


@project_router.post("/distillations/weekly")
def run_weekly_distillation(
    project_id: str,
    request: Request,
    week: str = Query(min_length=1, max_length=32),
    source_cutoff: str = Query(min_length=1, max_length=64),
    repo: GrowthRepository = Depends(get_growth_repository),
):
    project_id = _enforce_growth_access(request, project_id, write=True)
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise _http_error(503, "growth_dependency_unavailable", "Obsidian Vault is not configured")
    result = _guard(
        lambda: GrowthDistillationService(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).run_weekly(
            project_id, week, source_cutoff=source_cutoff
        )
    )
    return _ok(request, repo, project_id, {"distillation": _public_record(result)})


def _enforce_growth_access(request: Request, project_id: str, *, write: bool = False) -> str:
    project_id = _validate_project_id(project_id)
    role = str(getattr(request.state, "knowledge_role", "") or "")
    scoped_project = getattr(request.state, "knowledge_project_id", None)
    if role == "admin":
        return project_id
    if role == "reader":
        if write:
            raise _http_error(403, "growth_permission_denied", "reader credentials are read-only")
        return project_id
    if role in {"system", "project_admin"}:
        if scoped_project and scoped_project != project_id:
            raise _http_error(403, "growth_project_scope_denied", "credential is bound to another project")
        if role == "system" and not scoped_project:
            raise _http_error(403, "growth_project_scope_denied", "system principals must be project scoped")
        return project_id
    if role == "project_reader":
        if scoped_project != project_id:
            raise _http_error(403, "growth_project_scope_denied", "credential is bound to another project")
        if write:
            raise _http_error(403, "growth_permission_denied", "project_reader credentials are read-only")
        return project_id
    raise _http_error(403, "growth_permission_denied", "knowledge growth access is not permitted")


def _validate_project_id(project_id: str) -> str:
    value = str(project_id or "").strip()
    if not PROJECT_ID_PATTERN.fullmatch(value):
        raise _http_error(400, "growth_invalid_project", "project_id has an invalid format")
    return value


def _ok(
    request: Request,
    repo: GrowthRepository,
    project_id: str,
    data: dict[str, Any],
) -> ApiResponse:
    payload = {
        **data,
        "availability": _availability(repo, project_id),
        "access": {
            "role": str(getattr(request.state, "knowledge_role", "")),
            "can_write": str(getattr(request.state, "knowledge_role", "")) in {"admin", "project_admin", "system"},
        },
    }
    return ApiResponse.ok(payload)


def _availability(repo: GrowthRepository, project_id: str) -> dict[str, Any]:
    mapping = repo.get_vault(project_id)
    vault_root = Path(settings.OBSIDIAN_VAULT_ROOT).resolve() if settings.OBSIDIAN_VAULT_ROOT else None
    return {
        "growth": bool(settings.KNOWLEDGE_GROWTH_ENABLED),
        "scheduler": _scheduler_available(),
        "vault": bool(mapping and vault_root and vault_root.is_dir()),
        "mcp_write": bool(settings.KNOWLEDGE_MCP_WRITE_ENABLED),
    }


def _scheduler_availability_context() -> tuple[object, ...]:
    """Identify the runtime whose scheduler status is safe to reuse briefly."""
    return (
        str(settings.CELERY_BROKER_URL or ""),
        id(get_celery_app()),
        id(is_celery_real),
        id(is_celery_broker_available),
    )


def _reset_scheduler_availability_cache() -> None:
    """Clear the response-only availability cache for tests and runtime reconfiguration."""
    global _scheduler_availability_cache
    with _scheduler_availability_lock:
        _scheduler_availability_cache = None


def _scheduler_available() -> bool:
    """Return a short-lived status for UI responses without probing Redis per request.

    Submitting work deliberately retains its direct broker check in ``_start_run``.
    This cache is only for the advisory availability field returned on every read.
    """
    global _scheduler_availability_cache
    if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
        _reset_scheduler_availability_cache()
        return False

    context = _scheduler_availability_context()
    now = monotonic()
    with _scheduler_availability_lock:
        cached = _scheduler_availability_cache
        if cached and cached[0] == context and now - cached[1] < SCHEDULER_AVAILABILITY_CACHE_TTL_SECONDS:
            return cached[2]

        available = bool(is_celery_real() and is_celery_broker_available())
        _scheduler_availability_cache = (context, now, available)
        return available


def _paginate(items: list[dict[str, Any]], *, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if cursor in {None, ""}:
        offset = 0
        normalized_cursor = None
    elif cursor.isdigit() and 0 <= int(cursor) <= MAX_PAGE_SIZE:
        offset = int(cursor)
        normalized_cursor = cursor
    else:
        raise _http_error(400, "growth_invalid_cursor", "cursor must be an integer between 0 and 500")
    bounded_total = min(len(items), MAX_PAGE_SIZE)
    end = min(offset + limit, bounded_total)
    page = items[offset:end] if offset < bounded_total else []
    next_cursor = str(end) if end < bounded_total else None
    return page, {
        "limit": limit,
        "cursor": normalized_cursor,
        "next_cursor": next_cursor,
        "count": len(page),
    }


def _public_source(record: dict[str, Any]) -> dict[str, Any]:
    value = _public_record(record)
    value.pop("raw_content", None)
    return value


def _public_proposal(record: dict[str, Any]) -> dict[str, Any]:
    value = _public_record(record)
    operations = value.pop("operations", []) or []
    value["operation_count"] = len(operations)
    value.pop("body", None)
    return value


def _public_method_proposal(record: dict[str, Any]) -> dict[str, Any]:
    """Return review-list metadata without sending a candidate body eagerly."""
    value = _public_record(record)
    value.pop("body", None)
    manifest = value.pop("manifest", {}) or {}
    source_output_ids = value.pop("source_output_ids", []) or []
    value["task_family"] = str(manifest.get("task_family") or "")
    value["source_output_count"] = len(source_output_ids)
    return value


def _public_candidate(record: dict[str, Any]) -> dict[str, Any]:
    """Keep source excerpts out of high-volume review lists until selected."""
    value = _public_record(record)
    value.pop("evidence", None)
    value.pop("fingerprint", None)
    value.pop("explanation", None)
    return value


def _public_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return redact_secrets(record)


def _summary(repo: GrowthRepository, project_id: str) -> dict[str, Any]:
    sources = repo.list_sources(project_id)
    outputs = repo.list_outputs(project_id, limit=MAX_PAGE_SIZE)
    methods = repo.list_methods(project_id, limit=MAX_PAGE_SIZE)
    feedback = repo.list_feedback(project_id, limit=MAX_PAGE_SIZE)
    proposals = repo.list_proposals(project_id, limit=MAX_PAGE_SIZE)
    method_proposals = repo.list_method_proposals(project_id, limit=MAX_PAGE_SIZE)
    candidates = repo.list_candidates(project_id, limit=MAX_PAGE_SIZE)
    failures = repo.list_failure_records(project_id, limit=MAX_PAGE_SIZE)
    return {
        "project_id": project_id,
        "counts": {
            "sources": len(sources),
            "eligible_sources": sum(item.get("status") == "eligible" for item in sources),
            "pages": len(repo.list_pages(project_id)),
            "methods": len(methods),
            "published_methods": sum(item.get("status") == "published" for item in methods),
            "outputs": len(outputs),
            # Kept as a compatibility field; it represents accepted and filed
            # outputs, both of which are verified and eligible for reuse.
            "accepted_outputs": sum(is_verified_output_status(item.get("status")) for item in outputs),
            "rejected_outputs": sum(item.get("status") == "rejected" for item in outputs),
            "feedback": len(feedback),
            "wiki_proposals": len(proposals),
            "method_proposals": len(method_proposals),
            "candidates": len(candidates),
            "pending_candidates": sum(item.get("status") == "pending_review" for item in candidates),
            "review_records": len(feedback) + len(proposals) + len(method_proposals) + len(candidates),
            "open_failures": sum(item.get("status") != "resolved" for item in failures),
        },
        "bounded": {
            "methods": len(methods) == MAX_PAGE_SIZE,
            "outputs": len(outputs) == MAX_PAGE_SIZE,
            "review": (
                len(feedback) == MAX_PAGE_SIZE
                or len(proposals) == MAX_PAGE_SIZE
                or len(method_proposals) == MAX_PAGE_SIZE
                or len(candidates) == MAX_PAGE_SIZE
            ),
        },
    }


def _start_run(
    repo: GrowthRepository,
    *,
    project_id: str,
    job_type: str,
    idempotency_key: str,
    input_refs: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    if job_type not in GROWTH_JOB_TYPES:
        raise ValueError("unsupported growth job type")
    if not idempotency_key:
        return WikiCommandService(repo).start_run(
            project_id=project_id,
            job_type=job_type,
            trigger="http",
            input_refs=input_refs,
        )
    run = KnowledgeRun(
        project_id=project_id,
        run_type=job_type,
        trigger="http",
        status=RunStatus.QUEUED,
        actor_id=actor_id,
        input_refs={**input_refs, "idempotency_key": idempotency_key},
    )
    claim = repo.claim_schedule_run(run, idempotency_key)
    if not claim["claimed"]:
        return {"status": "duplicate", "run_id": claim["run_id"], "duplicate": True}
    run_id = claim["run_id"]
    if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
        repo.update_run_status(
            project_id,
            run_id,
            RunStatus.UNAVAILABLE,
            error="durable scheduler unavailable because the knowledge schedules feature is disabled",
            output_refs={"failure": {"code": "scheduler_disabled", "retryable": True}},
        )
        return {"status": "unavailable", "run_id": run_id}
    if not is_celery_real():
        from app.tasks.knowledge_tasks import execute_knowledge_run

        result = execute_knowledge_run(project_id, run_id, repository=repo)
        return {**result, "execution": "synchronous"}
    if not is_celery_broker_available():
        repo.update_run_status(
            project_id,
            run_id,
            RunStatus.UNAVAILABLE,
            error="durable scheduler unavailable because the Celery broker is unreachable",
            output_refs={"failure": {"code": "scheduler_unavailable", "retryable": True}},
        )
        return {"status": "unavailable", "run_id": run_id}
    from app.tasks.growth_tasks import growth_execute

    task = growth_execute.apply_async(args=[project_id, run_id])
    repo.append_run_event(
        project_id=project_id,
        run_id=run_id,
        event_type="knowledge.run.execution_assigned",
        payload={
            "execution": "celery",
            "task_name": "knowledge.growth.execute",
            "task_id": str(task.id),
        },
    )
    return {"status": "queued", "run_id": run_id, "task_id": task.id}


def _guard(callback):
    try:
        return callback()
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


def _guard_state_transition(callback, fallback_message: str):
    try:
        return callback()
    except HTTPException:
        raise
    except KeyError as exc:
        raise _translate_error(exc) from exc
    except ValueError as exc:
        normalized = str(exc).lower()
        state_markers = (
            "state",
            "status",
            "accepted",
            "filed",
            "published",
            "deprecated",
        )
        if any(marker in normalized for marker in state_markers):
            raise _http_error(
                409,
                "growth_state_conflict",
                str(exc) or fallback_message,
            ) from exc
        raise _translate_error(exc) from exc


def _translate_error(exc: Exception) -> HTTPException:
    message = _safe_message(str(exc))
    normalized = message.lower()
    if isinstance(exc, KeyError) or "not found" in normalized:
        return _http_error(404, "growth_resource_not_found", message)
    if isinstance(exc, PermissionError):
        return _http_error(403, "growth_permission_denied", message)
    if isinstance(exc, ProfileRevisionConflict):
        return _http_error(409, "growth_revision_conflict", message)
    if "conflict" in normalized or "revision" in normalized or "already bound" in normalized:
        return _http_error(409, "growth_conflict", message)
    if "unavailable" in normalized or "not configured" in normalized or "disabled" in normalized:
        return _http_error(503, "growth_dependency_unavailable", message)
    if isinstance(exc, (ValueError, TypeError)):
        return _http_error(400, "growth_invalid_request", message)
    logger.exception("Unhandled growth API failure", exc_info=exc)
    return _http_error(500, "growth_internal_error", "knowledge growth operation failed")


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _safe_message(message)})


def _safe_message(message: str) -> str:
    root = str(settings.OBSIDIAN_VAULT_ROOT or "")
    value = message.replace(root, "<vault>") if root else message
    return str(redact_secrets(value))[:500]


def _actor(request: Request) -> str:
    return str(getattr(request.state, "principal_id", "") or getattr(request.state, "knowledge_role", "") or "unknown")


def _vault_root() -> Path:
    configured = str(settings.OBSIDIAN_VAULT_ROOT or "").strip()
    if not configured:
        raise _http_error(
            503,
            "growth_dependency_unavailable",
            "Obsidian Vault is not configured",
        )
    root = Path(configured).resolve()
    if not root.is_dir():
        raise _http_error(
            503,
            "growth_dependency_unavailable",
            "Obsidian Vault is unavailable",
        )
    return root


def _assert_output_immutable(before: dict[str, Any], after: dict[str, Any]) -> None:
    immutable_fields = (
        "id",
        "project_id",
        "content_hash",
        "vault_path",
        "idempotency_key",
    )
    if any(before.get(field) != after.get(field) for field in immutable_fields):
        raise _http_error(
            500,
            "growth_integrity_error",
            "output filing changed immutable output identity",
        )
    if after.get("status") != "filed":
        raise _http_error(
            500,
            "growth_integrity_error",
            "output filing did not persist the filed state",
        )


def _validate_metadata_size(value: dict[str, Any]) -> None:
    try:
        size = len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must be JSON serializable") from exc
    if size > MAX_METADATA_BYTES:
        raise ValueError("metadata exceeds the 65536-byte limit")


# Preserve the frozen project path and the existing frontend path inside the
# already knowledge-scoped middleware boundary.
router.include_router(project_router, prefix="/knowledge/projects")
router.include_router(project_router, prefix="/knowledge/growth", include_in_schema=False)
