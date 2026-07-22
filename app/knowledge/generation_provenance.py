"""Typed provenance and prompt-safety contracts for knowledge-backed generation."""

from __future__ import annotations

from enum import Enum
import html
import re
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SECRET_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_SECRET_ASSIGNMENT = re.compile(
    r"(?im)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential|authorization)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_UNTRUSTED_INSTRUCTION = re.compile(
    r"(?i)(?:\b(?:ignore|disregard|forget|override|bypass)\b[^\r\n.!?]*?"
    r"\b(?:instructions?|prompts?|polic(?:y|ies)|rules?)\b[.!?]?|"
    r"(?:忽略|无视|覆盖|绕过)[^\r\n。！？]*(?:指令|提示词|规则|策略)[。！？]?)"
)


class ReferenceKind(str, Enum):
    SOURCE = "source"
    PAGE = "page"
    METHOD_REVISION = "method_revision"
    OUTPUT = "output"
    EVALUATION = "evaluation"
    FEEDBACK = "feedback"
    DISTILLATION = "distillation"


class ClaimStatus(str, Enum):
    FACT = "fact"
    ASSUMPTION = "assumption"
    RESEARCH_GAP = "research_gap"
    CONTRADICTION = "contradiction"
    STYLE_GUIDANCE = "style_guidance"
    METHOD_GUIDANCE = "method_guidance"
    EVALUATOR_FINDING = "evaluator_finding"


class GenerationReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    project_id: str = Field(min_length=1)
    kind: ReferenceKind
    ref_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    eligible: bool = True
    locator: str = ""

    @field_validator("locator")
    @classmethod
    def redact_locator(cls, value: str) -> str:
        return str(redact_secrets(value))


class GenerationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    status: ClaimStatus
    references: tuple[GenerationReference, ...] = ()

    @field_validator("text")
    @classmethod
    def redact_claim_text(cls, value: str) -> str:
        return str(redact_secrets(value))

    @model_validator(mode="after")
    def validate_grounding(self) -> "GenerationClaim":
        if self.status == ClaimStatus.FACT.value:
            evidence = {
                ReferenceKind.SOURCE.value,
                ReferenceKind.PAGE.value,
            }
            if not any(ref.eligible and ref.kind in evidence for ref in self.references):
                raise ValueError("factual claims require an eligible source or published page reference")
        if self.status == ClaimStatus.CONTRADICTION.value:
            evidence_refs = {
                (ref.kind, ref.ref_id, ref.revision)
                for ref in self.references
                if ref.eligible and ref.kind in {ReferenceKind.SOURCE.value, ReferenceKind.PAGE.value}
            }
            if len(evidence_refs) < 2:
                raise ValueError("contradictions require two distinct eligible evidence references")
        return self


class GenerationProvenanceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_revision: int = Field(ge=0)
    rules_revision: str = Field(min_length=1)
    source_cutoff: str = Field(min_length=1)
    generator_revision: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    creation_run_id: str = ""
    claims: tuple[GenerationClaim, ...] = ()
    context_omissions: tuple[str, ...] = ()
    resolution_status: str = Field(default="unverified", pattern=r"^(unverified|verified)$")

    @model_validator(mode="after")
    def validate_scope_and_ids(self) -> "GenerationProvenanceManifest":
        claim_ids: set[str] = set()
        for claim in self.claims:
            if claim.claim_id in claim_ids:
                raise ValueError("claim IDs must be unique")
            claim_ids.add(claim.claim_id)
            if any(ref.project_id != self.project_id for ref in claim.references):
                raise ValueError("generation provenance contains a cross-project reference")
        return self

    def to_generation_metadata(self) -> dict[str, Any]:
        refs: dict[str, list[dict[str, str]]] = {
            "source": [],
            "page": [],
            "method_revision": [],
            "output": [],
            "evaluation": [],
            "feedback": [],
            "distillation": [],
        }
        seen: set[tuple[str, str, str]] = set()
        for claim in self.claims:
            for ref in claim.references:
                key = (str(ref.kind), ref.ref_id, ref.revision)
                if key in seen:
                    continue
                seen.add(key)
                refs[str(ref.kind)].append({"id": ref.ref_id, "revision": ref.revision})
        return {
            "knowledge_context_used": True,
            "context_id": self.context_id,
            "context_hash": self.context_hash,
            "profile_revision": self.profile_revision,
            "rules_revision": self.rules_revision,
            "source_cutoff": self.source_cutoff,
            "creation_run_id": self.creation_run_id,
            "generator_revision": self.generator_revision,
            "model_revision": self.model_revision,
            "provenance_resolution": self.resolution_status,
            "source_refs": refs["source"],
            "page_refs": refs["page"],
            "method_revision_ids": [item["id"] for item in refs["method_revision"]],
            "output_example_refs": refs["output"],
            "evaluation_refs": refs["evaluation"],
            "feedback_refs": refs["feedback"],
            "distillation_refs": refs["distillation"],
            "selected_refs": [
                {"kind": kind, **item}
                for kind in ("source", "page", "method_revision", "output", "evaluation", "feedback", "distillation")
                for item in refs[kind]
            ],
            "context_omissions": list(self.context_omissions),
            "evidence_coverage": self._evidence_coverage(),
            "assumptions": [claim.text for claim in self.claims if claim.status == ClaimStatus.ASSUMPTION.value],
            "research_gaps": [claim.text for claim in self.claims if claim.status == ClaimStatus.RESEARCH_GAP.value],
            "research_candidates": [
                {"claim_id": claim.claim_id, "query": claim.text, "status": "pending_capture"}
                for claim in self.claims if claim.status == ClaimStatus.RESEARCH_GAP.value
            ],
            "contradictions": [claim.text for claim in self.claims if claim.status == ClaimStatus.CONTRADICTION.value],
        }

    def _evidence_coverage(self) -> dict[str, Any]:
        factual = [claim for claim in self.claims if claim.status == ClaimStatus.FACT.value]
        covered = sum(
            1 for claim in factual
            if any(ref.eligible and ref.kind in {ReferenceKind.SOURCE.value, ReferenceKind.PAGE.value} for ref in claim.references)
        )
        return {
            "covered": covered,
            "total": len(factual),
            "coverage": covered / len(factual) if factual else None,
        }


class ProvenanceResolutionError(ValueError):
    """Raised when a declared generation reference does not resolve exactly."""


def validate_generation_manifest(manifest: GenerationProvenanceManifest, repository: Any) -> GenerationProvenanceManifest:
    """Resolve every declared reference against project-authoritative storage."""
    checked: set[tuple[str, str, str]] = set()
    for claim in manifest.claims:
        for ref in claim.references:
            key = (str(ref.kind), ref.ref_id, ref.revision)
            if key in checked:
                continue
            checked.add(key)
            if not ref.eligible:
                raise ProvenanceResolutionError(f"reference is explicitly ineligible: {ref.kind}:{ref.ref_id}")
            if ref.kind == ReferenceKind.SOURCE.value:
                source = repository.get_source(manifest.project_id, ref.ref_id)
                if not source or source.get("status") not in {"eligible", "processed"}:
                    raise ProvenanceResolutionError(f"eligible source not found: {ref.ref_id}")
                _require_revision(ref, source, ("content_hash",))
            elif ref.kind == ReferenceKind.PAGE.value:
                page = repository.get_page(manifest.project_id, ref.ref_id)
                if not page or page.get("status") != "published":
                    raise ProvenanceResolutionError(f"published page not found: {ref.ref_id}")
                revisions = repository.list_page_revisions(manifest.project_id, ref.ref_id)
                if not any(ref.revision in {str(item.get("id")), str(item.get("content_hash")), str(item.get("version"))} for item in revisions):
                    raise ProvenanceResolutionError(f"page revision does not resolve exactly: {ref.ref_id}@{ref.revision}")
            elif ref.kind == ReferenceKind.METHOD_REVISION.value:
                revision = repository.get_method_revision(manifest.project_id, ref.ref_id)
                if not revision or revision.get("status") not in {"approved", "published"}:
                    raise ProvenanceResolutionError(f"approved method revision not found: {ref.ref_id}")
                _require_revision(ref, revision, ("id", "version"))
            elif ref.kind == ReferenceKind.OUTPUT.value:
                output = repository.get_output(manifest.project_id, ref.ref_id)
                if not output or output.get("status") not in {"accepted", "filed"}:
                    raise ProvenanceResolutionError(f"accepted output example not found: {ref.ref_id}")
                _require_revision(ref, output, ("content_hash",))
            elif ref.kind == ReferenceKind.EVALUATION.value:
                evaluation = next(
                    (item for item in repository.list_output_evaluations(manifest.project_id, limit=500) if item.get("id") == ref.ref_id),
                    None,
                )
                if not evaluation:
                    raise ProvenanceResolutionError(f"evaluation not found: {ref.ref_id}")
                _require_revision(ref, evaluation, ("id", "evaluator_revision", "created_at"))
            elif ref.kind == ReferenceKind.FEEDBACK.value:
                feedback = repository.get_feedback(manifest.project_id, ref.ref_id)
                if not feedback:
                    raise ProvenanceResolutionError(f"feedback not found: {ref.ref_id}")
                _require_revision(ref, feedback, ("id", "created_at", "processed_at"))
            elif ref.kind == ReferenceKind.DISTILLATION.value:
                distillation = next(
                    (item for item in repository.list_growth_distillations(manifest.project_id, limit=500) if item.get("id") == ref.ref_id),
                    None,
                )
                if not distillation:
                    raise ProvenanceResolutionError(f"distillation not found: {ref.ref_id}")
                _require_revision(ref, distillation, ("input_hash", "id", "created_at"))
    return manifest.model_copy(update={"resolution_status": "verified"})


def _require_revision(ref: GenerationReference, record: dict[str, Any], fields: tuple[str, ...]) -> None:
    values = {str(record.get(field)) for field in fields if record.get(field) not in {None, ""}}
    if ref.revision not in values:
        raise ProvenanceResolutionError(f"reference revision does not resolve exactly: {ref.kind}:{ref.ref_id}@{ref.revision}")

def redact_secrets(value: Any) -> Any:
    """Redact common credential forms without mutating the supplied structure."""
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if re.search(r"(?i)(api[_-]?key|token|password|secret|credential|authorization)", str(key)):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_secrets(item)
        return result
    if isinstance(value, (list, tuple)):
        redacted = [redact_secrets(item) for item in value]
        return tuple(redacted) if isinstance(value, tuple) else redacted
    if not isinstance(value, str):
        return value
    text = _SECRET_VALUE.sub("[REDACTED]", value)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


def sanitize_untrusted_text(text: str, *, data_kind: str, ref_id: str) -> str:
    """Neutralize obvious prompt injection and fence retrieved material as data."""
    cleaned = neutralize_untrusted_instructions(text)
    kind = html.escape(data_kind, quote=True)
    reference = html.escape(ref_id, quote=True)
    return f'<untrusted-data kind="{kind}" ref="{reference}">\n{cleaned}\n</untrusted-data>'


def neutralize_untrusted_instructions(text: str) -> str:
    cleaned = str(redact_secrets(text or ""))
    return _UNTRUSTED_INSTRUCTION.sub("[UNTRUSTED_INSTRUCTION_REDACTED]", cleaned)


def build_generation_manifest(
    *,
    project_id: str,
    context_id: str,
    context_hash: str,
    profile_revision: int,
    rules_revision: str,
    source_cutoff: str,
    generator_revision: str,
    model_revision: str,
    claims: Iterable[GenerationClaim] = (),
    creation_run_id: str = "",
    context_omissions: Iterable[str] = (),
    repository: Any | None = None,
) -> GenerationProvenanceManifest:
    manifest = GenerationProvenanceManifest(
        project_id=project_id,
        context_id=context_id,
        context_hash=context_hash,
        profile_revision=profile_revision,
        rules_revision=rules_revision,
        source_cutoff=source_cutoff,
        generator_revision=generator_revision,
        model_revision=model_revision,
        creation_run_id=creation_run_id,
        claims=tuple(claims),
        context_omissions=tuple(dict.fromkeys(str(item) for item in context_omissions if str(item))),
    )
    return validate_generation_manifest(manifest, repository) if repository is not None else manifest


def legacy_generation_metadata() -> dict[str, Any]:
    """Explicit additive metadata for callers that have no configured growth context."""
    return {
        "knowledge_context_used": False,
        "context_id": "",
        "context_hash": "",
        "source_refs": [],
        "page_refs": [],
        "method_revision_ids": [],
        "assumptions": [],
        "research_gaps": [],
        "context_omissions": ["growth_context_unavailable"],
    }
