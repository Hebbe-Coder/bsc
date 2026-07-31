from __future__ import annotations

from hashlib import sha256
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


def _source(repo: GrowthRepository, project_id: str, source_id: str, content: str) -> dict:
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
        )
    )


def _setup(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "prd-to-sop.db"))
    repo.configure_vault("project-a", "projects/project-a", "test")
    prd = _source(repo, "project-a", "prd-a", "The project must review every generated SOP before execution.")
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


def _draft(prd_id: str, page_id: str) -> dict:
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
        "source_refs": [prd_id],
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
