"""Project-scoped PRD-to-SOP generation with durable A/B/C/D lineage."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
import yaml

from app.core.config import settings
from app.knowledge.generation_provenance import (
    ClaimStatus,
    GenerationClaim,
    GenerationReference,
    ReferenceKind,
    build_generation_manifest,
    redact_secrets,
)
from app.knowledge.growth_context import GrowthContextBuilder, GrowthContextPack, GrowthContextService
from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.source_triage import source_admission_reason
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.promptops import PromptOps, PromptOpsError, PromptRequest, PromptTask


PRD_TO_SOP_RUN_TYPE = "prd_to_sop"
PRD_TO_SOP_REVISION = "project-prd-to-sop-v1"
class ProjectSopGenerationError(ValueError):
    """A stable, non-secret failure category for the growth API and run ledger."""

    def __init__(self, category: str, message: str) -> None:
        self.category = category
        super().__init__(message)


class ProjectSopGenerationRequest(BaseModel):
    """Explicit operator intent for one governed D-layer SOP draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prd_source_id: str = Field(min_length=1, max_length=128)
    supporting_source_ids: list[str] = Field(default_factory=list, max_length=12)
    goal: str = Field(min_length=8, max_length=4_000)
    audience: str = Field(min_length=2, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=200)
    channel: str = Field(default="knowledge_workspace", min_length=1, max_length=100)

    @field_validator("prd_source_id", "goal", "audience", "idempotency_key", "channel")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("request fields must not be blank")
        return normalized

    @field_validator("supporting_source_ids")
    @classmethod
    def normalize_supporting_source_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("supporting_source_ids must contain non-empty source IDs up to 128 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("supporting_source_ids must not contain duplicates")
        return normalized


class SopPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=300)
    objective: str = Field(min_length=4, max_length=2_000)
    owner: str = Field(min_length=1, max_length=300)
    inputs: list[str] = Field(default_factory=list, max_length=30)
    outputs: list[str] = Field(default_factory=list, max_length=30)
    steps: list[str] = Field(min_length=1, max_length=30)
    quality_gates: list[str] = Field(default_factory=list, max_length=20)


class SopEvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2_000)
    status: Literal["fact", "assumption", "research_gap"]
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    page_refs: list[str] = Field(default_factory=list, max_length=100)


class ProjectSopDraft(BaseModel):
    """The only model response accepted by the PRD-to-SOP writer."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=500)
    purpose: str = Field(min_length=8, max_length=4_000)
    phases: list[SopPhase] = Field(min_length=1, max_length=20)
    assumptions: list[str] = Field(min_length=1, max_length=40)
    risks: list[str] = Field(min_length=1, max_length=40)
    open_questions: list[str] = Field(min_length=1, max_length=40)
    source_refs: list[str] = Field(min_length=1, max_length=200)
    page_refs: list[str] = Field(default_factory=list, max_length=200)
    evidence_claims: list[SopEvidenceClaim] = Field(default_factory=list, max_length=100)


class ProjectSopGenerationService:
    """Turn admitted PRD evidence into a reviewable, not-yet-accepted SOP output."""

    def __init__(
        self,
        repository: GrowthRepository,
        vault_root: str,
        *,
        promptops: PromptOps | None = None,
        context_service: GrowthContextService | None = None,
    ) -> None:
        self.repository = repository
        self.vault_root = vault_root
        self.promptops = promptops or PromptOps()
        # PRDs are intentionally included alongside the governed B/C/D context.
        # This is local to the task and does not expand generic chat contexts.
        self.context_service = context_service or GrowthContextService(
            repository,
            vault_root,
            # Chinese PRDs use materially more tokens per character than the
            # generic builder estimate. Keep enough of the active evidence
            # set for a grounded SOP while reserving the model's completion
            # budget instead of repeatedly truncating before JSON begins.
            builder=GrowthContextBuilder(max_characters=16_000),
        )

    def generate(
        self,
        *,
        project_id: str,
        request: ProjectSopGenerationRequest,
        actor_id: str = "",
        trigger: str = "http",
    ) -> dict[str, Any]:
        prd_source = self._admitted_prd(project_id, request.prd_source_id)
        if prd_source["id"] in request.supporting_source_ids:
            raise ProjectSopGenerationError(
                "supporting_source_duplicates_prd",
                "the project PRD must not be repeated as a supporting source",
            )
        supporting_sources = tuple(
            self._admitted_supporting_source(project_id, source_id)
            for source_id in request.supporting_source_ids
        )
        required_source_ids = tuple([str(prd_source["id"]), *[str(source["id"]) for source in supporting_sources]])
        request_fingerprint = self._request_fingerprint(project_id, request, prd_source, supporting_sources)
        run_id = self._run_id(project_id, request.idempotency_key)
        existing = self.repository.get_run(project_id, run_id)
        if existing:
            return self._resolve_existing(existing, request_fingerprint)

        run = KnowledgeRun(
            id=run_id,
            project_id=project_id,
            run_type=PRD_TO_SOP_RUN_TYPE,
            trigger=trigger,
            actor_id=actor_id,
            status=RunStatus.QUEUED,
            input_refs={
                "request_fingerprint": request_fingerprint,
                "idempotency_key": request.idempotency_key,
                "prd_source_id": prd_source["id"],
                "prd_content_hash": prd_source["content_hash"],
                "supporting_source_ids": list(request.supporting_source_ids),
                "supporting_source_hashes": {
                    str(source["id"]): str(source["content_hash"])
                    for source in supporting_sources
                },
                "goal_fingerprint": self._fingerprint(request.goal),
                "audience_fingerprint": self._fingerprint(request.audience),
                "channel": request.channel,
                "generator_revision": PRD_TO_SOP_REVISION,
            },
        )
        try:
            self.repository.create_run(run)
        except Exception as exc:
            existing = self.repository.get_run(project_id, run_id)
            if existing:
                return self._resolve_existing(existing, request_fingerprint)
            raise ProjectSopGenerationError("run_creation_failed", "could not create the PRD-to-SOP run") from exc

        if not self.repository.claim_run_execution(project_id=project_id, run_id=run_id):
            current = self.repository.get_run(project_id, run_id)
            if current:
                return self._resolve_existing(current, request_fingerprint)
            raise ProjectSopGenerationError("run_claim_failed", "could not claim the PRD-to-SOP run")

        try:
            source_cutoff = datetime.now(timezone.utc).isoformat()
            context = self.context_service.build_context(
                project_id=project_id,
                task=(
                    "Generate a project-specific SOP from an admitted PRD. "
                    f"Goal: {request.goal}\nAudience: {request.audience}\n"
                    "Preserve assumptions and unresolved risks."
                ),
                source_cutoff=source_cutoff,
                creation_run_id=run_id,
                required_source_ids=required_source_ids,
            )
            allowed_source_ids = tuple(dict.fromkeys(context.source_ids))
            allowed_page_ids = tuple(dict.fromkeys(context.page_ids))
            missing_required_sources = set(required_source_ids) - set(allowed_source_ids)
            if missing_required_sources:
                raise ProjectSopGenerationError(
                    "required_source_omitted_from_context",
                    "an explicitly selected source did not fit in the governed context; no SOP was generated",
                )

            self.repository.update_run_input_refs(
                project_id,
                run_id,
                {
                    **run.input_refs,
                    "context_revision": context.revision,
                    "context_hash": context.context_hash,
                    "context_source_ids": list(allowed_source_ids),
                    "context_page_ids": list(allowed_page_ids),
                    "context_method_revision_ids": list(context.method_revision_ids),
                    "context_weekly_distillation_ids": list(
                        self._context_ids(context, "distillation:")
                    ),
                    "source_cutoff": source_cutoff,
                },
            )
            self.repository.append_run_event(
                project_id=project_id,
                run_id=run_id,
                event_type="knowledge.prd_to_sop.context_built",
                payload={
                    "context_revision": context.revision,
                    "source_count": len(allowed_source_ids),
                    "page_count": len(allowed_page_ids),
                    "method_count": len(context.method_revision_ids),
                },
            )

            prompt_run = self.promptops.run_structured(
                self._prompt_request(
                    project_id=project_id,
                    request=request,
                    context=context,
                    allowed_source_ids=allowed_source_ids,
                    allowed_page_ids=allowed_page_ids,
                )
            )
            draft = self._validate_draft(
                prompt_run.output,
                required_source_ids=required_source_ids,
                allowed_source_ids=allowed_source_ids,
                allowed_page_ids=allowed_page_ids,
            )
            manifest = self._manifest(
                project_id=project_id,
                draft=draft,
                context=context,
                source_cutoff=source_cutoff,
                prompt_model=str(prompt_run.model),
                run_id=run_id,
            )
            content = self._render_markdown(
                project_id=project_id,
                request=request,
                draft=draft,
                context=context,
                run_id=run_id,
                prompt_run_id=str(prompt_run.run_id),
            ).encode("utf-8")
            output = OutputAsset(
                project_id=project_id,
                kind="project_sop",
                title=draft.title,
                mime_type="text/markdown",
                content_hash=hashlib.sha256(content).hexdigest(),
                vault_path=f"outputs/{datetime.now(timezone.utc).strftime('%Y')}/project-sop.md",
                run_id=run_id,
                method_revision_id=context.method_revision_ids[0] if context.method_revision_ids else "",
                context_revision=context.revision,
                source_refs=draft.source_refs,
                page_refs=draft.page_refs,
                idempotency_key=f"prd-to-sop:{request.idempotency_key}",
                metadata={
                    "goal": request.goal,
                    "audience": request.audience,
                    "channel": request.channel,
                    "generator": "project_sop_generation_service",
                    "provider": str(prompt_run.provider),
                    "model": str(prompt_run.model),
                    "prompt_revision": PRD_TO_SOP_REVISION,
                    "origin": "bsc_system_generated",
                    "prd_source_id": prd_source["id"],
                    "prd_content_hash": prd_source["content_hash"],
                    "supporting_source_ids": list(request.supporting_source_ids),
                    "prompt_run_id": str(prompt_run.run_id),
                    "prompt_fingerprint": str(prompt_run.prompt_fingerprint),
                    "input_fingerprint": str(prompt_run.input_fingerprint),
                    "prompt_attempt_count": int(prompt_run.attempt_count),
                    "prompt_retry_count": int(prompt_run.retry_count),
                    "output_contract": PRD_TO_SOP_REVISION,
                    "generation_risks": draft.risks,
                    "generation_provenance": {
                        **manifest.to_generation_metadata(),
                        "supporting_source_ids": list(request.supporting_source_ids),
                    },
                },
            )
            registered = OutputRegistry(self.repository, self.vault_root).register_content(output, content)
            completed = self.repository.update_run_status(
                project_id,
                run_id,
                RunStatus.COMPLETED,
                output_refs={
                    "output_id": registered["id"],
                    "output_status": registered["status"],
                    "output_vault_path": registered["vault_path"],
                    "context_revision": context.revision,
                    "prompt_run_id": str(prompt_run.run_id),
                    "provider": str(prompt_run.provider),
                    "model": str(prompt_run.model),
                },
            )
            return {"run": completed, "output": registered, "idempotent": False}
        except ProjectSopGenerationError as exc:
            self._fail_run(project_id, run_id, exc.category, str(exc))
            raise
        except PromptOpsError as exc:
            self._fail_run(project_id, run_id, exc.category, "the configured model provider did not return a usable SOP")
            raise ProjectSopGenerationError(exc.category, "the configured model provider did not return a usable SOP") from exc
        except Exception as exc:
            self._fail_run(project_id, run_id, "prd_to_sop_failed", str(exc))
            raise ProjectSopGenerationError("prd_to_sop_failed", "the PRD-to-SOP run failed before output registration") from exc

    def _admitted_prd(self, project_id: str, source_id: str) -> dict[str, Any]:
        source = self.repository.get_source(project_id, source_id)
        if not source:
            raise ProjectSopGenerationError("prd_source_not_found", "PRD source not found in the requested project")
        if source.get("status") not in {"eligible", "processed"}:
            raise ProjectSopGenerationError("prd_source_not_admitted", "PRD source must be eligible or processed before generation")
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        evidence_role = str(metadata.get("evidence_role") or "").strip().lower()
        if evidence_role not in {"project_prd", "prd"}:
            raise ProjectSopGenerationError(
                "prd_source_not_designated",
                "selected source is not designated as a project PRD",
            )
        reason = source_admission_reason(self.repository, project_id, source)
        if reason:
            raise ProjectSopGenerationError("prd_source_not_admitted", f"PRD source is not admitted: {reason}")
        return source

    def _admitted_supporting_source(self, project_id: str, source_id: str) -> dict[str, Any]:
        source = self.repository.get_source(project_id, source_id)
        if not source:
            raise ProjectSopGenerationError(
                "supporting_source_not_found",
                "supporting source was not found in the requested project",
            )
        if source.get("status") not in {"eligible", "processed"}:
            raise ProjectSopGenerationError(
                "supporting_source_not_admitted",
                "supporting source must be eligible or processed before generation",
            )
        reason = source_admission_reason(self.repository, project_id, source)
        if reason:
            raise ProjectSopGenerationError(
                "supporting_source_not_admitted",
                f"supporting source is not admitted: {reason}",
            )
        return source

    def _resolve_existing(self, run: dict[str, Any], request_fingerprint: str) -> dict[str, Any]:
        input_refs = run.get("input_refs") or {}
        if input_refs.get("request_fingerprint") != request_fingerprint:
            raise ProjectSopGenerationError(
                "idempotency_conflict",
                "the idempotency key was already used with a different PRD-to-SOP request",
            )
        status = str(run.get("status") or "")
        if status == RunStatus.COMPLETED.value:
            output_id = str((run.get("output_refs") or {}).get("output_id") or "")
            output = self.repository.get_output(str(run.get("project_id") or ""), output_id) if output_id else None
            if output:
                return {"run": run, "output": output, "idempotent": True}
            raise ProjectSopGenerationError("completed_output_missing", "completed SOP run is missing its registered output")
        if status in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise ProjectSopGenerationError("generation_in_progress", "this PRD-to-SOP request is already running")
        raise ProjectSopGenerationError("previous_generation_failed", "the previous PRD-to-SOP run failed; use a new idempotency key after correction")

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _request_fingerprint(
        self,
        project_id: str,
        request: ProjectSopGenerationRequest,
        prd_source: dict[str, Any],
        supporting_sources: tuple[dict[str, Any], ...],
    ) -> str:
        return self._fingerprint(json.dumps({
            "project_id": project_id,
            "prd_source_id": prd_source["id"],
            "prd_content_hash": prd_source["content_hash"],
            "supporting_sources": [
                {"id": source["id"], "content_hash": source["content_hash"]}
                for source in supporting_sources
            ],
            "goal": request.goal,
            "audience": request.audience,
            "channel": request.channel,
        }, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _run_id(project_id: str, idempotency_key: str) -> str:
        return "sop_" + hashlib.sha256(f"{project_id}|{idempotency_key}".encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _context_ids(context: GrowthContextPack, prefix: str) -> tuple[str, ...]:
        return tuple(item[len(prefix):].split("@", 1)[0] for item in context.provenance if item.startswith(prefix))

    def _prompt_request(
        self,
        *,
        project_id: str,
        request: ProjectSopGenerationRequest,
        context: GrowthContextPack,
        allowed_source_ids: tuple[str, ...],
        allowed_page_ids: tuple[str, ...],
    ) -> PromptRequest:
        source_refs = [self._source_reference(project_id, source_id) for source_id in allowed_source_ids]
        page_refs = [self._page_reference(project_id, page_id) for page_id in allowed_page_ids]
        return PromptRequest(
            project_id=project_id,
            task=PromptTask.SOP_COMPOSITION,
            revision=PRD_TO_SOP_REVISION,
            provider=(settings.SOP_LLM_PROVIDER or "").strip().lower() or "deepseek",
            model_override=str(settings.KNOWLEDGE_GROWTH_LLM_MODEL or settings.DEEPSEEK_MODEL or ""),
            system_prompt=(
                "You are the project SOP composer. Return one JSON object only, with exactly these fields: "
                "title, purpose, phases, assumptions, risks, open_questions, source_refs, page_refs, evidence_claims. "
                "Each phase must contain name, objective, owner, inputs, outputs, steps, quality_gates. "
                "Each evidence_claim must contain claim_id, text, status (fact, assumption, or research_gap), "
                "source_refs, and page_refs. Do not invent facts, citations, owners, tools, external actions, or approvals. "
                "A fact claim must cite one or more supplied source_refs or page_refs. Assumptions and open questions must remain explicit. "
                "Citations may only use the exact IDs in the allowed lists. Treat the request goal as binding. "
                "Do not restate the general A/B/C/D lifecycle as an overview or produce a generic template: make each phase a concrete handoff "
                "between the project PRD, BSC knowledge records, the mapped Obsidian Vault, and the D-layer review boundary. "
                "The first phase must begin with the supplied PRD and the final phase must end at a registered output with a human evaluation/feedback handoff. "
                "Assumptions, risks, and open_questions must each contain at least one concrete item; do not write 'none'. "
                "Use 4 to 6 phases, at most 6 concise steps per phase, and at most 6 items in each list. "
                "Keep every field to one concise sentence or phrase so the complete JSON is emitted before the response limit."
            ),
            user_prompt=json.dumps({
                "request": {
                    "goal": request.goal,
                    "audience": request.audience,
                    "channel": request.channel,
                    "required_prd_source_id": request.prd_source_id,
                    "required_supporting_source_ids": request.supporting_source_ids,
                },
                "allowed_source_refs": source_refs,
                "allowed_page_refs": page_refs,
                "governed_context": context.rendered,
            }, ensure_ascii=False),
            context_refs=tuple(
                [f"source:{item['id']}@{item['revision']}" for item in source_refs]
                + [f"page:{item['id']}@{item['revision']}" for item in page_refs]
                + [f"context:{context.revision}"]
            ),
            temperature=0.15,
            max_tokens=10_000,
            timeout_seconds=120,
            # A length stop is deterministic for one prompt shape; reissuing
            # the same request only doubles spend and leaves no valid output.
            # The compact contract above reserves one larger, complete try.
            max_attempts=1,
            max_structured_attempts=1,
        )

    def _source_reference(self, project_id: str, source_id: str) -> dict[str, str]:
        source = self.repository.get_source(project_id, source_id)
        if not source:
            raise ProjectSopGenerationError("context_reference_missing", "a selected source no longer exists")
        return {"id": source_id, "revision": str(source["content_hash"])}

    def _page_reference(self, project_id: str, page_id: str) -> dict[str, str]:
        revision = self.repository.get_page_content(project_id, page_id)
        if not revision:
            raise ProjectSopGenerationError("context_reference_missing", "a selected Wiki page no longer exists")
        return {"id": page_id, "revision": str(revision["id"])}

    def _validate_draft(
        self,
        value: Any,
        *,
        required_source_ids: tuple[str, ...],
        allowed_source_ids: tuple[str, ...],
        allowed_page_ids: tuple[str, ...],
    ) -> ProjectSopDraft:
        try:
            draft = ProjectSopDraft.model_validate(value)
        except ValidationError as exc:
            # Preserve only contract paths and error codes. Model output can
            # contain project content, so it must never be copied into the run
            # ledger merely to explain a validation failure.
            diagnostics = self._schema_diagnostics(exc)
            raise ProjectSopGenerationError(
                "output_contract_invalid",
                f"model output did not match the project SOP contract ({diagnostics})",
            ) from exc
        except Exception as exc:
            raise ProjectSopGenerationError("output_contract_invalid", "model output did not match the project SOP contract") from exc
        source_refs = self._unique_refs(draft.source_refs)
        page_refs = self._unique_refs(draft.page_refs)
        missing_required_sources = set(required_source_ids) - set(source_refs)
        if missing_required_sources:
            raise ProjectSopGenerationError(
                "output_contract_invalid",
                "model output did not cite every explicitly selected source",
            )
        if not set(source_refs).issubset(set(allowed_source_ids)) or not set(page_refs).issubset(set(allowed_page_ids)):
            raise ProjectSopGenerationError("output_contract_invalid", "model output cited a source or page outside the governed context")
        normalized_claims: list[SopEvidenceClaim] = []
        for claim in draft.evidence_claims:
            claim_sources = self._unique_refs(claim.source_refs)
            claim_pages = self._unique_refs(claim.page_refs)
            if not set(claim_sources).issubset(set(source_refs)) or not set(claim_pages).issubset(set(page_refs)):
                raise ProjectSopGenerationError("output_contract_invalid", "an evidence claim cited a reference outside the declared SOP evidence")
            normalized_claims.append(claim.model_copy(update={"source_refs": claim_sources, "page_refs": claim_pages}))
        return draft.model_copy(update={"source_refs": source_refs, "page_refs": page_refs, "evidence_claims": normalized_claims})

    @staticmethod
    def _unique_refs(values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if len(normalized) != len(values):
            raise ProjectSopGenerationError("output_contract_invalid", "model output contained blank or duplicate evidence references")
        return normalized

    @staticmethod
    def _schema_diagnostics(error: ValidationError) -> str:
        """Return bounded, content-free validation hints for an operator retry."""
        hints: list[str] = []
        for issue in error.errors():
            location = ".".join(str(part) for part in issue.get("loc", ())) or "root"
            kind = str(issue.get("type") or "invalid")
            hint = f"{location}:{kind}"
            if hint not in hints:
                hints.append(hint)
            if len(hints) == 6:
                break
        return ", ".join(hints) or "unknown_schema_error"

    def _manifest(
        self,
        *,
        project_id: str,
        draft: ProjectSopDraft,
        context: GrowthContextPack,
        source_cutoff: str,
        prompt_model: str,
        run_id: str,
    ) -> Any:
        claims: list[GenerationClaim] = []
        for index, assumption in enumerate(draft.assumptions, start=1):
            claims.append(GenerationClaim(
                claim_id=f"declared-assumption-{index}",
                text=assumption,
                status=ClaimStatus.ASSUMPTION,
            ))
        for index, question in enumerate(draft.open_questions, start=1):
            claims.append(GenerationClaim(
                claim_id=f"declared-open-question-{index}",
                text=question,
                status=ClaimStatus.RESEARCH_GAP,
            ))
        for claim in draft.evidence_claims:
            refs = tuple(
                [GenerationReference(
                    project_id=project_id,
                    kind=ReferenceKind.SOURCE,
                    ref_id=source_id,
                    revision=self._source_reference(project_id, source_id)["revision"],
                ) for source_id in claim.source_refs]
                + [GenerationReference(
                    project_id=project_id,
                    kind=ReferenceKind.PAGE,
                    ref_id=page_id,
                    revision=self._page_reference(project_id, page_id)["revision"],
                ) for page_id in claim.page_refs]
            )
            claims.append(GenerationClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                status=ClaimStatus(claim.status),
                references=refs,
            ))
        try:
            return build_generation_manifest(
                project_id=project_id,
                context_id=context.revision,
                context_hash=context.context_hash,
                profile_revision=context.profile_revision,
                rules_revision=context.rules_revision,
                source_cutoff=source_cutoff,
                generator_revision=PRD_TO_SOP_REVISION,
                model_revision=prompt_model,
                claims=claims,
                creation_run_id=run_id,
                context_omissions=context.omitted_refs,
                repository=self.repository,
            )
        except Exception as exc:
            raise ProjectSopGenerationError("provenance_invalid", "model claim provenance did not resolve in this project") from exc

    def _render_markdown(
        self,
        *,
        project_id: str,
        request: ProjectSopGenerationRequest,
        draft: ProjectSopDraft,
        context: GrowthContextPack,
        run_id: str,
        prompt_run_id: str,
    ) -> str:
        frontmatter = yaml.safe_dump(redact_secrets({
            "bsc_output_contract": PRD_TO_SOP_REVISION,
            "project_id": project_id,
            "run_id": run_id,
            "prompt_run_id": prompt_run_id,
            "prd_source_id": request.prd_source_id,
            "context_revision": context.revision,
            "source_refs": draft.source_refs,
            "page_refs": draft.page_refs,
            "status": "registered_pending_evaluation",
        }), allow_unicode=True, sort_keys=False).strip()
        lines = [f"---\n{frontmatter}\n---", "", f"# {draft.title}", "", "## Purpose", draft.purpose, "", "## Delivery Intent", f"- Goal: {request.goal}", f"- Audience: {request.audience}", f"- Channel: {request.channel}", "", "## Phases"]
        for index, phase in enumerate(draft.phases, start=1):
            lines.extend([f"### {index}. {phase.name}", f"**Objective:** {phase.objective}", f"**Owner:** {phase.owner}", "", "**Inputs**"])
            lines.extend([f"- {item}" for item in phase.inputs] or ["- None declared"])
            lines.append("**Steps**")
            lines.extend([f"{step_index}. {item}" for step_index, item in enumerate(phase.steps, start=1)])
            lines.append("**Outputs**")
            lines.extend([f"- {item}" for item in phase.outputs] or ["- None declared"])
            lines.append("**Quality gates**")
            lines.extend([f"- {item}" for item in phase.quality_gates] or ["- None declared"])
            lines.append("")
        lines.extend(["## Assumptions", *([f"- {item}" for item in draft.assumptions] or ["- None declared"]), "", "## Risks", *([f"- {item}" for item in draft.risks] or ["- None declared"]), "", "## Open Questions", *([f"- {item}" for item in draft.open_questions] or ["- None declared"]), "", "## Evidence References"])
        lines.extend([f"- Source: `{item}`" for item in draft.source_refs])
        lines.extend([f"- Wiki page: `{item}`" for item in draft.page_refs])
        return str(redact_secrets("\n".join(lines).strip() + "\n"))

    def _fail_run(self, project_id: str, run_id: str, category: str, message: str) -> None:
        safe_message = str(redact_secrets(message))[:1_800]
        self.repository.update_run_status(
            project_id,
            run_id,
            RunStatus.FAILED,
            error=f"{category}: {safe_message}",
            output_refs={"failure_category": category},
        )
