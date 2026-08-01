from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.prd_to_sop import (
    ProjectSopGenerationError,
    ProjectSopGenerationRequest,
    ProjectSopGenerationService,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.promptops import PromptOpsError


class RecordingPromptOps:
    def __init__(self, output: dict | None = None, error: Exception | None = None) -> None:
        self.output = output or {}
        self.error = error
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(
            run_id="prompt-test-001",
            provider="deepseek",
            model="deepseek-v4-pro",
            prompt_fingerprint="a" * 64,
            input_fingerprint="b" * 64,
            attempt_count=1,
            retry_count=0,
            output=self.output,
        )


def _source(
    repo: GrowthRepository,
    project_id: str,
    source_id: str,
    content: str,
    *,
    evidence_role: str = "",
) -> dict:
    return repo.create_source(
        SourceRecord(
            id=source_id,
            project_id=project_id,
            source_type="user_authored_project_document",
            origin=f"{source_id}.md",
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            raw_content=content,
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            metadata={"evidence_role": evidence_role} if evidence_role else {},
        )
    )


def _setup(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "prd-to-sop.db"))
    repo.configure_vault("project-a", "projects/project-a", "test")
    prd = _source(
        repo,
        "project-a",
        "prd-a",
        "The project must review every generated SOP before execution.",
        evidence_role="project_prd",
    )
    support = _source(repo, "project-a", "support-a", "Reports require traceable evidence references.")
    repo.record_publication(
        project_id="project-a",
        contents={
            "AGENTS.md": "---\nproject_id: project-a\nrevision: test-r1\n---\nUse approved evidence only.\n",
            "wiki/control.md": "---\ntitle: Control\nkind: decision\n---\nEvidence is required [source:support-a].\n",
        },
        source_ids=[support["id"]],
    )
    page = next(item for item in repo.list_pages("project-a") if item["path"] == "wiki/control.md")
    return repo, root, prd, page


def _draft(prd_id: str, page_id: str, supporting_source_ids: tuple[str, ...] = ()) -> dict:
    return {
        "title": "Evidence-led SOP delivery",
        "purpose": "Convert the admitted project PRD into a reviewed and traceable operating procedure.",
        "phases": [{
            "name": "Scope the request",
            "objective": "Bind the SOP to the admitted PRD and review gate.",
            "owner": "Project operator",
            "inputs": ["Admitted PRD"],
            "outputs": ["Scoped SOP draft"],
            "steps": ["Read the PRD", "Record assumptions before execution"],
            "quality_gates": ["PRD source remains cited"],
        }],
        "assumptions": ["The project operator will review the registered draft."],
        "risks": ["Missing business constraints remain unresolved."],
        "open_questions": ["Which execution owner accepts the final SOP?"],
        "source_refs": [prd_id, *supporting_source_ids],
        "page_refs": [page_id],
        "evidence_claims": [{
            "claim_id": "review-gate",
            "text": "The project requires review before execution.",
            "status": "fact",
            "source_refs": [prd_id],
            "page_refs": [],
        }],
    }


def test_project_sop_generation_registers_pending_output_with_exact_lineage_and_idempotency(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    promptops = RecordingPromptOps(_draft(prd["id"], page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key="prd-to-sop-test-1",
    )
    try:
        first = service.generate(project_id="project-a", request=request, actor_id="tester")
        output = first["output"]
        run = first["run"]

        assert first["idempotent"] is False
        assert output["status"] == "registered"
        assert output["source_refs"] == [prd["id"]]
        assert output["page_refs"] == [page["id"]]
        assert run["status"] == "completed"
        assert run["input_refs"]["prd_source_id"] == prd["id"]
        assert run["input_refs"]["context_revision"] == output["context_revision"]
        assert output["metadata"]["generation_provenance"]["provenance_resolution"] == "verified"
        assert output["metadata"]["generation_provenance"]["assumptions"] == [
            "The project operator will review the registered draft."
        ]
        assert output["metadata"]["generation_provenance"]["research_gaps"] == [
            "Which execution owner accepts the final SOP?"
        ]
        assert output["metadata"]["generation_risks"] == ["Missing business constraints remain unresolved."]

        materialized = OutputRegistry(repo, root).read_content("project-a", output["id"])
        assert "bsc_output_contract: project-prd-to-sop-v1" in materialized["content"]
        assert "registered_pending_evaluation" in materialized["content"]
        assert "Evidence-led SOP delivery" in materialized["content"]

        edges = {(edge["edge_type"], edge["from_id"], edge["to_id"]) for edge in repo.list_lineage("project-a")}
        assert ("output_used_source", prd["id"], output["id"]) in edges
        assert ("output_used_page", page["id"], output["id"]) in edges
        assert ("output_produced_by_run", run["id"], output["id"]) in edges

        repeated = service.generate(project_id="project-a", request=request, actor_id="tester")
        assert repeated["idempotent"] is True
        assert repeated["output"]["id"] == output["id"]
        assert len(promptops.requests) == 1
    finally:
        repo.close()


def test_project_sop_generation_includes_selected_admitted_supporting_sources_in_context_and_lineage(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    support = repo.get_source("project-a", "support-a")
    assert support is not None
    draft = _draft(prd["id"], page["id"])
    draft["source_refs"] = [prd["id"], support["id"]]
    draft["evidence_claims"][0]["source_refs"] = [prd["id"], support["id"]]
    promptops = RecordingPromptOps(draft)
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=[support["id"]],
        goal="Deliver an evidence-led SOP for the current project request.",
        audience="project operators",
        idempotency_key="prd-to-sop-supporting-source",
    )
    try:
        result = service.generate(project_id="project-a", request=request, actor_id="tester")
        run = result["run"]
        output = result["output"]

        assert run["input_refs"]["supporting_source_ids"] == [support["id"]]
        assert run["input_refs"]["supporting_source_hashes"] == {support["id"]: support["content_hash"]}
        assert output["metadata"]["generation_provenance"]["supporting_source_ids"] == [support["id"]]
        prompt = promptops.requests[0]
        assert support["id"] in prompt.user_prompt
        assert "Reports require traceable evidence references." in prompt.user_prompt
        edges = {(edge["edge_type"], edge["from_id"], edge["to_id"]) for edge in repo.list_lineage("project-a")}
        assert ("output_used_source", support["id"], output["id"]) in edges
    finally:
        repo.close()


def test_project_sop_generation_normalizes_string_phase_io_without_relaxing_source_lineage(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    support = repo.get_source("project-a", "support-a")
    assert support is not None
    draft = _draft(prd["id"], page["id"], (support["id"],))
    draft["source_refs"] = [prd["id"], support["id"]]
    draft["evidence_claims"][0]["source_refs"] = [prd["id"], support["id"]]
    draft["phases"][0]["inputs"] = "Selected PRD and supporting evidence"
    draft["phases"][0]["outputs"] = "Reviewable project SOP"
    promptops = RecordingPromptOps(draft)
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=[support["id"]],
        goal="Create a project-specific SOP from the admitted evidence set.",
        audience="project operators",
        idempotency_key="string-phase-io-compatibility",
    )
    try:
        result = service.generate(project_id="project-a", request=request, actor_id="tester")
        output = result["output"]
        materialized = OutputRegistry(repo, root).read_content("project-a", output["id"])

        assert result["run"]["status"] == "completed"
        assert output["source_refs"] == [prd["id"], support["id"]]
        assert output["metadata"]["generation_provenance"]["supporting_source_ids"] == [support["id"]]
        assert "- Selected PRD and supporting evidence" in materialized["content"]
        assert "- Reviewable project SOP" in materialized["content"]
        edges = {(edge["edge_type"], edge["from_id"], edge["to_id"]) for edge in repo.list_lineage("project-a")}
        assert ("output_used_source", prd["id"], output["id"]) in edges
        assert ("output_used_source", support["id"], output["id"]) in edges
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("supporting_source_ids", "category"),
    [(["prd-a"], "supporting_source_duplicates_prd"), (["missing-source"], "supporting_source_not_found")],
)
def test_project_sop_generation_rejects_invalid_supporting_sources_before_model_invocation(tmp_path, supporting_source_ids, category):
    repo, root, prd, page = _setup(tmp_path)
    promptops = RecordingPromptOps(_draft(prd["id"], page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=supporting_source_ids,
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key=f"invalid-support-{category}",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == category
        assert promptops.requests == []
    finally:
        repo.close()


def test_project_sop_generation_rejects_cross_project_supporting_source_before_model_invocation(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    foreign = _source(repo, "project-b", "support-b", "Foreign evidence must remain isolated.")
    promptops = RecordingPromptOps(_draft(prd["id"], page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=[foreign["id"]],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key="foreign-supporting-source",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "supporting_source_not_found"
        assert promptops.requests == []
    finally:
        repo.close()


def test_project_sop_generation_requires_and_records_selected_supporting_sources(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    support = repo.get_source("project-a", "support-a")
    assert support is not None
    promptops = RecordingPromptOps(_draft(prd["id"], page["id"], (support["id"],)))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=[support["id"]],
        goal="Create an evidence-specific SOP for the current project delivery.",
        audience="project operators",
        idempotency_key="supporting-source-success",
    )
    try:
        result = service.generate(project_id="project-a", request=request, actor_id="tester")

        assert result["output"]["source_refs"] == [prd["id"], support["id"]]
        assert result["run"]["input_refs"]["supporting_source_ids"] == [support["id"]]
        assert json.loads(promptops.requests[0].user_prompt)["request"]["required_supporting_source_ids"] == [support["id"]]
    finally:
        repo.close()


def test_project_sop_generation_rejects_a_draft_that_omits_selected_supporting_source(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    promptops = RecordingPromptOps(_draft(prd["id"], page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        supporting_source_ids=["support-a"],
        goal="Create an evidence-specific SOP for the current project delivery.",
        audience="project operators",
        idempotency_key="supporting-source-omitted",
    )
    try:
        with pytest.raises(ProjectSopGenerationError, match="every explicitly selected source") as error:
            service.generate(project_id="project-a", request=request, actor_id="tester")
        assert error.value.category == "output_contract_invalid"
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_project_sop_generation_rejects_cross_project_prd_before_model_invocation(tmp_path):
    repo, root, _prd, page = _setup(tmp_path)
    foreign = _source(repo, "project-b", "prd-b", "Foreign project evidence must remain isolated.")
    promptops = RecordingPromptOps(_draft("prd-b", page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=foreign["id"],
        goal="Deliver a governed SOP for this project.",
        audience="project operators",
        idempotency_key="foreign-prd",
    )
    try:
        with pytest.raises(ProjectSopGenerationError, match="not found") as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "prd_source_not_found"
        assert promptops.requests == []
        assert repo.list_runs("project-a") == []
    finally:
        repo.close()


def test_project_sop_generation_rejects_an_admitted_source_without_prd_designation(tmp_path):
    repo, root, _prd, page = _setup(tmp_path)
    non_prd = _source(repo, "project-a", "research-a", "Research evidence is not a project PRD.")
    promptops = RecordingPromptOps(_draft(non_prd["id"], page["id"]))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=non_prd["id"],
        goal="Deliver a governed SOP for this project.",
        audience="project operators",
        idempotency_key="non-prd-source",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "prd_source_not_designated"
        assert promptops.requests == []
        assert repo.list_runs("project-a") == []
    finally:
        repo.close()


def test_invalid_model_reference_fails_run_without_registering_output(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    invalid = _draft(prd["id"], page["id"])
    invalid["source_refs"] = ["unknown-source"]
    promptops = RecordingPromptOps(invalid)
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key="invalid-reference",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "output_contract_invalid"
        run = repo.list_runs("project-a")[0]
        assert run["status"] == "failed"
        assert run["output_refs"] == {"failure_category": "output_contract_invalid"}
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_provider_failure_leaves_a_durable_failed_run_and_no_output(tmp_path):
    repo, root, prd, _page = _setup(tmp_path)
    promptops = RecordingPromptOps(error=PromptOpsError("payment_required"))
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key="provider-failure",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "payment_required"
        run = repo.list_runs("project-a")[0]
        assert run["status"] == "failed"
        assert run["output_refs"] == {"failure_category": "payment_required"}
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_schema_failure_records_only_contract_paths_not_model_content(tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    invalid = _draft(prd["id"], page["id"])
    invalid["assumptions"] = []
    invalid["purpose"] = "secret project wording must not reach the run ledger"
    service = ProjectSopGenerationService(repo, str(root), promptops=RecordingPromptOps(invalid))
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key="schema-diagnostics",
    )

    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)

        assert error.value.category == "output_contract_invalid"
        run = repo.list_runs("project-a")[0]
        assert "assumptions:too_short" in run["error"]
        assert "secret project wording" not in run["error"]
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


@pytest.mark.parametrize("field", ["assumptions", "risks", "open_questions"])
def test_missing_declared_uncertainty_fails_the_output_contract(field, tmp_path):
    repo, root, prd, page = _setup(tmp_path)
    invalid = _draft(prd["id"], page["id"])
    invalid[field] = []
    promptops = RecordingPromptOps(invalid)
    service = ProjectSopGenerationService(repo, str(root), promptops=promptops)
    request = ProjectSopGenerationRequest(
        prd_source_id=prd["id"],
        goal="Deliver a governed SOP for the current project request.",
        audience="project operators",
        idempotency_key=f"missing-{field}",
    )
    try:
        with pytest.raises(ProjectSopGenerationError) as error:
            service.generate(project_id="project-a", request=request)
        assert error.value.category == "output_contract_invalid"
        assert repo.list_runs("project-a")[0]["status"] == "failed"
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()
