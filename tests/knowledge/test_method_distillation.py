import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.growth_contracts import CandidateEvidenceAnchor, KnowledgeCandidate, KnowledgeCandidateStatus
from app.core.config import settings
from app.knowledge.method_distillation import (
    METHOD_DISTILLATION_MAX_TOKENS,
    METHOD_DISTILLATION_RECOVERY_TIMEOUT_SECONDS,
    METHOD_DISTILLATION_TIMEOUT_SECONDS,
    MAX_METHOD_CANDIDATES,
    MethodDistillationError,
    PromptOpsDistillationProvider,
    SOURCE_METHOD_DISTILLATION_RUN_TYPE,
    SourceMethodDistillationService,
    claim_source_method_distillation_run,
    recover_abandoned_source_method_distillations,
)
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceRecord, SourceStatus


SOURCE_TEXT = """Evidence starts from source facts, and tests constrain claims.
Compare customer interviews before changing a sales funnel.
Negative triggers prevent a method from taking over unrelated work.
Observed failure modes must remain visible in every reusable process.
"""


class FakeDistillationProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def distill(self, *, project_id, source):
        self.calls += 1
        assert project_id == "project-a"
        assert source["id"] == "source-a"
        return self.response, {"run_id": "prompt-1", "provider": "test", "model": "test-model"}


def _body(title):
    return f"""# {title}

## R
Evidence starts from source facts, and tests constrain claims.

## I
Use a constrained, evidence-first decision process. Do not turn one observation into a reusable rule without checking its boundary and competing explanations.

## A1
The source connects interview comparison to a sales-funnel change and records a concrete review condition before acting.

## A2
Use this only when the task language identifies a deliberate evidence comparison, not a generic request for more text.

## E
1. Collect the stated evidence. 2. Compare it with a competing explanation. 3. Stop when a negative signal applies.

## B
Do not use for a quick social post. The source warns that unsupported claims and hidden failure modes make a method unsafe.
"""


def _candidate(slug, name, *, positive, negative, sibling):
    return {
        "slug": slug,
        "name": name,
        "body": _body(name),
        "manifest": {
            "applicability": positive,
            "exclusions": negative,
            "inputs": [{"name": "task"}],
            "outputs": [{"name": "decision"}],
            "steps": ["Inspect evidence", "Test boundary", "Produce a constrained action"],
            "evidence_rules": ["Cite immutable source anchors"],
            "failure_handling": ["Stop when negative trigger is present"],
            "eval_cases": [
                {"id": f"{slug}-positive-1", "type": "should_trigger", "prompt": positive[0], "expected_method": slug},
                {"id": f"{slug}-positive-2", "type": "should_trigger", "prompt": f"Need {positive[0]} now", "expected_method": slug},
                {"id": f"{slug}-positive-3", "type": "should_trigger", "prompt": f"Review {positive[1]}", "expected_method": slug},
                {"id": f"{slug}-negative-1", "type": "should_not_trigger", "prompt": negative[0], "expected_method": ""},
                {"id": f"{slug}-negative-2", "type": "should_not_trigger", "prompt": sibling["prompt"], "expected_method": sibling["slug"]},
                {"id": f"{slug}-edge", "type": "edge_case", "prompt": f"{positive[0]} but {negative[0]}", "expected_method": ""},
            ],
            "distillation": {
                "source_kind": "interview",
                "candidate_type": "framework",
                "evidence": [
                    {"source_id": "source-a", "anchor": "line-1", "quote": "Evidence starts from source facts, and tests constrain claims."},
                    {"source_id": "source-a", "anchor": "line-2", "quote": "Compare customer interviews before changing a sales funnel."},
                ],
                "critical_review": {
                    "author_assumptions": ["The source has enough context to compare interviews."],
                    "failure_modes": ["A single interview may overfit the decision."],
                    "validity_limits": ["Not for unsourced real-time decisions."],
                },
                "non_triviality": "It requires explicit disconfirming evidence before a reusable change is proposed, rather than merely collecting opinions.",
                "trigger_contract": {"positive_signals": positive, "negative_signals": negative},
            },
        },
    }


def _response():
    return {"candidates": [
        _candidate(
            "evidence-comparison",
            "Evidence comparison",
            positive=["customer interview comparison", "evidence comparison"],
            negative=["quick social post"],
            sibling={"slug": "sales-funnel-review", "prompt": "sales funnel review"},
        ),
        _candidate(
            "sales-funnel-review",
            "Sales funnel review",
            positive=["sales funnel review", "conversion change"],
            negative=["quick social post"],
            sibling={"slug": "evidence-comparison", "prompt": "customer interview comparison"},
        ),
    ]}


def _source(repo, *, classification="internal"):
    return repo.create_source(SourceRecord(
        id="source-a",
        project_id="project-a",
        source_type="meeting_notes",
        origin="obsidian://project-a/interviews",
        content_hash=hashlib.sha256(SOURCE_TEXT.encode()).hexdigest(),
        raw_content=SOURCE_TEXT,
        trust_level="reviewed",
        status=SourceStatus.ELIGIBLE,
        metadata={"data_classification": classification},
    ))


def _accepted_candidate(repo, source, *, candidate_id="cangjie-framework-a"):
    extraction_run = repo.create_run(KnowledgeRun(
        id=f"{candidate_id}-run",
        project_id="project-a",
        run_type="cangjie_candidate_extraction",
        trigger="test",
        status=RunStatus.COMPLETED,
        actor_id="owner",
    ))
    candidate = repo.save_candidate(KnowledgeCandidate(
        id=candidate_id,
        project_id="project-a",
        source_id=source["id"],
        source_content_hash=source["content_hash"],
        extraction_run_id=extraction_run["id"],
        candidate_type="framework",
        title="Evidence-first comparison",
        claim="Compare independent interview evidence before changing a decision path.",
        explanation="Retain the method only when the source describes both evidence and a bounded decision.",
        evidence=[CandidateEvidenceAnchor(
            source_id=source["id"],
            content_hash=source["content_hash"],
            anchor="interview-comparison",
            quote="Compare customer interviews before changing a sales funnel.",
        )],
        fingerprint=hashlib.sha256(candidate_id.encode()).hexdigest(),
    ))
    return repo.review_candidate(
        "project-a",
        candidate["id"],
        decision=KnowledgeCandidateStatus.ACCEPTED,
        actor_id="owner",
        review_note="Approved as a focused method-selection signal.",
    )


def test_source_distillation_creates_lineaged_candidates_then_publishes_only_after_real_gate(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "distillation.db"))
    vault = tmp_path / "vault"
    vault.mkdir()
    repo.configure_vault("project-a", "projects/project-a", "owner")
    _source(repo)
    provider = FakeDistillationProvider(_response())
    try:
        result = SourceMethodDistillationService(repo, provider=provider).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )
        assert provider.calls == 1
        assert len(result["proposals"]) == 2
        proposal = next(item for item in result["proposals"] if item["manifest"]["task_family"] == "evidence-comparison")
        assert proposal["source_output_ids"] == []
        assert proposal["manifest"]["distillation"]["contract_revision"] == "ria-tvpp-v1"
        assert proposal["manifest"]["distillation"]["evidence"][0]["content_hash"] == hashlib.sha256(SOURCE_TEXT.encode()).hexdigest()
        edges = repo.list_lineage("project-a")
        assert any(edge["edge_type"] == "source_distills_method_proposal" and edge["to_id"] == proposal["id"] for edge in edges)

        evaluation = MethodEvaluator(repo).evaluate(proposal)
        assert evaluation["eligible"] is True
        assert evaluation["v1_evidence_diversity"]["anchors"] == 2
        assert all(item["passed"] for item in evaluation["v2_transfer_and_routing"]["cases"])

        method = MethodGate(repo, MethodRegistry(repo, vault)).publish_prompt_method(
            project_id="project-a",
            proposal_id=proposal["id"],
            actor_id="owner",
            actor_role="project_admin",
            project_policy_allows=True,
        )
        assert method["status"] == "published"
        assert (vault / "projects" / "project-a" / "methods" / "evidence-comparison" / "SKILL.md").is_file()
        run = repo.get_run("project-a", result["run_id"])
        assert run["status"] == "completed"
    finally:
        repo.close()


def test_accepted_cangjie_candidate_guides_a_review_only_method_proposal(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "candidate-selection.db"))
    source = _source(repo)
    accepted = _accepted_candidate(repo, source)

    class CandidateAwareProvider(FakeDistillationProvider):
        def distill(self, *, project_id, source):
            self.calls += 1
            self.selection = source["accepted_candidates"]
            assert self.selection[0]["id"] == accepted["id"]
            assert self.selection[0]["candidate_type"] == "framework"
            return self.response, {"run_id": "prompt-candidate", "provider": "test", "model": "test-model"}

    provider = CandidateAwareProvider(_response())
    try:
        result = SourceMethodDistillationService(repo, provider=provider).distill(
            project_id="project-a",
            source_id=source["id"],
            actor_id="owner",
            candidate_ids=[accepted["id"]],
        )

        assert provider.calls == 1
        assert provider.selection[0]["id"] == accepted["id"]
        run = repo.get_run("project-a", result["run_id"])
        assert run["input_refs"]["candidate_ids"] == [accepted["id"]]
        assert len(run["input_refs"]["candidate_selection_hash"]) == 64
        proposal = result["proposals"][0]
        selection = proposal["manifest"]["distillation"]["candidate_selection"]
        assert selection["candidate_ids"] == [accepted["id"]]
        assert selection["candidate_types"] == ["framework"]
        assert "claim" not in selection
        edges = repo.list_lineage("project-a")
        assert any(
            edge["edge_type"] == "candidate_guides_method_proposal"
            and edge["from_id"] == accepted["id"]
            and edge["to_id"] == proposal["id"]
            for edge in edges
        )
        assert repo.list_methods("project-a") == []
    finally:
        repo.close()


def test_source_distillation_refuses_unaccepted_or_duplicate_candidate_selection(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "candidate-selection-rejection.db"))
    source = _source(repo)
    extraction_run = repo.create_run(KnowledgeRun(
        id="pending-candidate-run",
        project_id="project-a",
        run_type="cangjie_candidate_extraction",
        trigger="test",
        status=RunStatus.COMPLETED,
        actor_id="owner",
    ))
    pending = repo.save_candidate(KnowledgeCandidate(
        id="pending-candidate",
        project_id="project-a",
        source_id=source["id"],
        source_content_hash=source["content_hash"],
        extraction_run_id=extraction_run["id"],
        candidate_type="principle",
        title="Evidence before action",
        claim="Require independent evidence before applying a reusable decision rule.",
        evidence=[CandidateEvidenceAnchor(
            source_id=source["id"],
            content_hash=source["content_hash"],
            anchor="source-fact",
            quote="Evidence starts from source facts, and tests constrain claims.",
        )],
        fingerprint=hashlib.sha256(b"pending-candidate").hexdigest(),
    ))
    service = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(_response()))
    try:
        with pytest.raises(MethodDistillationError, match="must be accepted"):
            service.submit(
                project_id="project-a",
                source_id=source["id"],
                actor_id="owner",
                candidate_ids=[pending["id"]],
            )
        accepted = _accepted_candidate(repo, source)
        with pytest.raises(MethodDistillationError, match="duplicate ids"):
            service.submit(
                project_id="project-a",
                source_id=source["id"],
                actor_id="owner",
                candidate_ids=[accepted["id"], accepted["id"]],
            )
    finally:
        repo.close()


def test_source_distillation_submit_then_detached_execution_survives_the_http_submission_boundary(tmp_path):
    from app.core import celery_app as celery_module
    from app.tasks.method_distillation_tasks import execute_source_method_distillation

    original_celery_app = celery_module._celery_app
    repo = GrowthRepository(db_path=str(tmp_path / "detached-distillation.db"))
    vault = tmp_path / "vault"
    vault.mkdir()
    repo.configure_vault("project-a", "projects/project-a", "owner")
    _source(repo)
    service = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(_response()))
    try:
        submitted = service.submit(project_id="project-a", source_id="source-a", actor_id="owner", trigger="http")

        assert submitted["status"] == "queued"
        assert repo.list_method_proposals("project-a") == []
        result = execute_source_method_distillation(
            "project-a",
            submitted["id"],
            repository=repo,
            service_factory=lambda _repository: service,
        )

        assert result["run_id"] == submitted["id"]
        assert len(result["proposals"]) == 2
        persisted = repo.get_run("project-a", submitted["id"])
        assert persisted["status"] == "completed"
        assert repo.list_methods("project-a") == []
        events = repo.list_run_events(project_id="project-a", run_id=submitted["id"])
        assert [event["event_type"] for event in events] == [
            "knowledge.run.queued",
            "knowledge.method_distillation.started",
            "knowledge.method_distillation.proposed",
            "knowledge.run.completed",
        ]

        duplicate = execute_source_method_distillation("project-a", submitted["id"], repository=repo)
        assert duplicate == {"status": "completed", "run_id": submitted["id"], "duplicate": True}
        assert repo.list_method_proposals("project-a")
    finally:
        repo.close()
        celery_module._celery_app = original_celery_app


def test_source_distillation_claim_is_atomic_and_never_runs_the_same_submission_twice(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "claim-distillation.db"))
    _source(repo)
    service = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(_response()))
    try:
        submitted = service.submit(project_id="project-a", source_id="source-a", actor_id="owner")

        assert claim_source_method_distillation_run(repo, project_id="project-a", run_id=submitted["id"]) is True
        assert claim_source_method_distillation_run(repo, project_id="project-a", run_id=submitted["id"]) is False
        assert repo.get_run("project-a", submitted["id"])["status"] == "running"
    finally:
        repo.close()


def test_sqlite_method_submission_stays_in_process_when_celery_broker_is_available(monkeypatch, tmp_path):
    """Do not enqueue a SQLite ledger to a Celery worker with another database."""
    from app.tasks import method_distillation_tasks

    repo = GrowthRepository(db_path=str(tmp_path / "sqlite-method-dispatch.db"))
    run = repo.create_run(
        KnowledgeRun(project_id="project-a", run_type=SOURCE_METHOD_DISTILLATION_RUN_TYPE, trigger="test")
    )
    execution_calls: list[tuple[str, str, GrowthRepository | None]] = []
    celery_calls: list[list[str]] = []

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    def execute(project_id, run_id, *, repository=None, **_kwargs):
        execution_calls.append((project_id, run_id, repository))
        return {"status": "completed", "run_id": run_id}

    try:
        monkeypatch.setattr(method_distillation_tasks, "is_celery_real", lambda: True)
        monkeypatch.setattr(method_distillation_tasks, "is_celery_broker_available", lambda: True)
        monkeypatch.setattr(method_distillation_tasks, "Thread", ImmediateThread)
        monkeypatch.setattr(method_distillation_tasks, "execute_source_method_distillation", execute)
        monkeypatch.setattr(
            method_distillation_tasks.source_method_distillation_execute,
            "apply_async",
            lambda args: celery_calls.append(args),
        )

        assignment = method_distillation_tasks.dispatch_source_method_distillation(
            "project-a", run["id"], repository=repo
        )

        assert assignment == {"execution": "in_process", "task_id": f"in-process:{run['id']}"}
        assert celery_calls == []
        assert execution_calls == [("project-a", run["id"], repo)]
        assert repo.list_run_events(project_id="project-a", run_id=run["id"])[-1]["payload"] == assignment
    finally:
        repo.close()


def test_source_distillation_never_sends_private_raw_material_to_provider(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "private.db"))
    _source(repo, classification="private")
    provider = FakeDistillationProvider(_response())
    try:
        with pytest.raises(MethodDistillationError, match="sanitized derivative"):
            SourceMethodDistillationService(repo, provider=provider).distill(
                project_id="project-a", source_id="source-a", actor_id="owner"
            )
        assert provider.calls == 0
        assert repo.list_method_proposals("project-a") == []
    finally:
        repo.close()


def test_source_distillation_rejects_unresolvable_evidence_quote_before_a_proposal_is_saved(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "bad-quote.db"))
    _source(repo)
    response = _response()
    response["candidates"][0]["manifest"]["distillation"]["evidence"][0]["quote"] = "fabricated source quotation"
    try:
        with pytest.raises(MethodDistillationError, match="does not resolve"):
            SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
                project_id="project-a", source_id="source-a", actor_id="owner"
            )
        assert repo.list_method_proposals("project-a") == []
    finally:
        repo.close()


def test_source_distillation_rejects_an_incomplete_trigger_contract_before_a_proposal_is_saved(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "bad-route.db"))
    _source(repo)
    response = _response()
    response["candidates"][0]["manifest"]["distillation"]["trigger_contract"]["positive_signals"] = ["customer interview comparison"]
    try:
        with pytest.raises(MethodDistillationError, match="trigger contract requires at least two positive"):
            SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
                project_id="project-a", source_id="source-a", actor_id="owner"
            )
        assert repo.list_method_proposals("project-a") == []
    finally:
        repo.close()


def test_source_distillation_replaces_shaped_but_self_contradictory_routing_cases(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "mismatched-route-cases.db"))
    _source(repo)
    response = _response()
    candidate = response["candidates"][0]
    candidate["manifest"]["eval_cases"] = [
        {"id": "wrong-positive-1", "type": "should_trigger", "prompt": "unrelated prompt", "expected_method": candidate["slug"]},
        {"id": "wrong-positive-2", "type": "should_trigger", "prompt": "still unrelated", "expected_method": candidate["slug"]},
        {"id": "wrong-positive-3", "type": "should_trigger", "prompt": "also unrelated", "expected_method": candidate["slug"]},
        {"id": "wrong-negative-1", "type": "should_not_trigger", "prompt": "customer interview comparison", "expected_method": ""},
        {"id": "wrong-negative-2", "type": "should_not_trigger", "prompt": "evidence comparison", "expected_method": ""},
        {"id": "wrong-edge", "type": "edge_case", "prompt": "customer interview comparison", "expected_method": ""},
    ]
    response["candidates"] = [candidate]
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        cases = proposal["manifest"]["eval_cases"]
        assert "eval_cases" in proposal["manifest"]["distillation"]["derived_execution_contract_fields"]
        assert cases[0]["prompt"] == "customer interview comparison"
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
    finally:
        repo.close()


def test_source_distillation_replaces_model_method_names_with_slug_bound_routing_cases(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "named-route-cases.db"))
    _source(repo)
    response = _response()
    candidate = response["candidates"][0]
    for item in candidate["manifest"]["eval_cases"]:
        if item["expected_method"]:
            item["expected_method"] = candidate["name"]
    response["candidates"] = [candidate]
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        cases = proposal["manifest"]["eval_cases"]
        assert "eval_cases" in proposal["manifest"]["distillation"]["derived_execution_contract_fields"]
        assert cases[0]["expected_method"] == "evidence-comparison"
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
    finally:
        repo.close()


def test_source_distillation_allows_one_evidence_backed_method_without_inventing_a_sibling(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "one-candidate.db"))
    _source(repo)
    response = deepcopy(_response())
    response["candidates"] = response["candidates"][:1]
    response["candidates"][0]["manifest"]["eval_cases"][4] = {
        "id": "evidence-comparison-negative-2",
        "type": "should_not_trigger",
        "prompt": "book a lunch meeting",
        "expected_method": "",
    }
    try:
        result = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )
        assert len(result["proposals"]) == 1
        evaluation = MethodEvaluator(repo).evaluate(result["proposals"][0])
        assert evaluation["eligible"] is True
        assert all(item["passed"] for item in evaluation["v2_transfer_and_routing"]["cases"])
    finally:
        repo.close()


def test_source_distillation_completes_one_valid_model_anchor_with_a_related_verbatim_source_anchor(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "evidence-fallback.db"))
    _source(repo)
    response = deepcopy(_response())
    response["candidates"] = response["candidates"][:1]
    response["candidates"][0]["manifest"]["eval_cases"][4] = {
        "id": "evidence-comparison-negative-2",
        "type": "should_not_trigger",
        "prompt": "book a lunch meeting",
        "expected_method": "",
    }
    response["candidates"][0]["manifest"]["distillation"]["evidence"] = response["candidates"][0]["manifest"]["distillation"]["evidence"][:1]
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        evidence = proposal["manifest"]["distillation"]["evidence"]
        assert len(evidence) == 2
        assert proposal["manifest"]["distillation"]["evidence_selection"] == "model_plus_source_fallback"
        assert all(item["quote"] in SOURCE_TEXT for item in evidence)
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
    finally:
        repo.close()


def test_source_distillation_marks_zero_model_citations_for_manual_review_but_keeps_verbatim_source_evidence(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "source-derived-evidence.db"))
    _source(repo)
    response = deepcopy(_response())
    response["candidates"] = response["candidates"][:1]
    response["candidates"][0]["manifest"]["eval_cases"][4] = {
        "id": "evidence-comparison-negative-2",
        "type": "should_not_trigger",
        "prompt": "book a lunch meeting",
        "expected_method": "",
    }
    del response["candidates"][0]["manifest"]["distillation"]["evidence"]
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        contract = proposal["manifest"]["distillation"]
        assert len(contract["evidence"]) == 2
        assert contract["evidence_selection"] == "source_derived_no_model_citation"
        assert contract["manual_citation_review_required"] is True
        assert all(item["quote"] in SOURCE_TEXT for item in contract["evidence"])
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
        assert repo.list_methods("project-a") == []
    finally:
        repo.close()


def test_source_distillation_derives_routing_cases_from_real_trigger_contract_when_model_omits_them(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "derived-routing.db"))
    _source(repo)
    response = deepcopy(_response())
    response["candidates"] = response["candidates"][:1]
    response["candidates"][0]["manifest"]["eval_cases"] = []
    response["candidates"][0]["manifest"]["distillation"]["evidence"] = response["candidates"][0]["manifest"]["distillation"]["evidence"][:1]
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        contract = proposal["manifest"]["distillation"]
        assert "eval_cases" in contract["derived_execution_contract_fields"]
        assert len(proposal["manifest"]["eval_cases"]) == 6
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
    finally:
        repo.close()


def test_source_distillation_derives_missing_critical_review_boundaries_from_the_ria_body(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "derived-boundaries.db"))
    _source(repo)
    response = deepcopy(_response())
    response["candidates"] = response["candidates"][:1]
    response["candidates"][0]["manifest"]["eval_cases"][4] = {
        "id": "evidence-comparison-negative-2",
        "type": "should_not_trigger",
        "prompt": "book a lunch meeting",
        "expected_method": "",
    }
    response["candidates"][0]["manifest"]["distillation"]["evidence"] = response["candidates"][0]["manifest"]["distillation"]["evidence"][:1]
    response["candidates"][0]["manifest"]["distillation"]["critical_review"] = {"author_assumptions": []}
    try:
        proposal = SourceMethodDistillationService(repo, provider=FakeDistillationProvider(response)).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )["proposals"][0]
        contract = proposal["manifest"]["distillation"]
        assert contract["derived_critical_review_fields"] == ["failure_modes", "validity_limits"]
        assert contract["critical_review"]["failure_modes"]
        assert contract["critical_review"]["validity_limits"]
        assert MethodEvaluator(repo).evaluate(proposal)["eligible"] is True
    finally:
        repo.close()


def test_source_distillation_regenerates_once_for_a_real_provider_when_contract_validation_fails(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "retry.db"))
    repo.configure_vault("project-a", "projects/project-a", "owner")
    _source(repo)

    class RetryableProvider:
        def __init__(self):
            self.calls = 0
            self.retry_calls = 0
            self.retry_error = ""

        def distill(self, *, project_id, source):
            self.calls += 1
            invalid = deepcopy(_response())
            del invalid["candidates"][0]["manifest"]["distillation"]["critical_review"]
            return invalid, {"run_id": "prompt-initial", "provider": "test", "model": "test-model"}

        def retry_distill(self, *, project_id, source, validation_error):
            self.retry_calls += 1
            self.retry_error = validation_error
            return _response(), {"run_id": "prompt-retry", "provider": "test", "model": "test-model"}

    provider = RetryableProvider()
    try:
        result = SourceMethodDistillationService(repo, provider=provider).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )
        assert provider.calls == 1
        assert provider.retry_calls == 1
        assert provider.retry_error == "distillation contract requires critical_review"
        assert len(result["proposals"]) == 2
        assert result["provider"]["attempt_count"] == "2"
        assert result["provider"]["initial_prompt_run_id"] == "prompt-initial"
        assert repo.get_run("project-a", result["run_id"])["status"] == "completed"
        assert repo.list_methods("project-a") == []
    finally:
        repo.close()


def test_source_distillation_retries_a_structured_provider_failure_once(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "provider-retry.db"))
    repo.configure_vault("project-a", "projects/project-a", "owner")
    _source(repo)

    class ProviderWithStructuredFailure:
        def __init__(self):
            self.calls = 0
            self.retry_calls = 0

        def distill(self, *, project_id, source):
            self.calls += 1
            raise MethodDistillationError("source distillation model call failed: structured_response_invalid")

        def retry_distill(self, *, project_id, source, validation_error):
            self.retry_calls += 1
            assert validation_error.endswith("structured_response_invalid")
            return _response(), {"run_id": "prompt-retry", "provider": "test", "model": "test-model"}

    provider = ProviderWithStructuredFailure()
    try:
        result = SourceMethodDistillationService(repo, provider=provider).distill(
            project_id="project-a", source_id="source-a", actor_id="owner"
        )
        assert provider.calls == 1
        assert provider.retry_calls == 1
        assert result["provider"]["attempt_count"] == "2"
        events = repo.list_run_events(project_id="project-a", run_id=result["run_id"])
        assert any(event["event_type"] == "knowledge.method_distillation.retrying" for event in events)
    finally:
        repo.close()


def test_source_distillation_recovery_marks_only_stale_direct_model_calls_failed(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "recovery.db"))
    stale = repo.create_run(
        KnowledgeRun(
            id="stale-method-distillation",
            project_id="project-a",
            run_type="source_method_distillation",
            trigger="manual",
            status=RunStatus.RUNNING,
        )
    )
    recent = repo.create_run(
        KnowledgeRun(
            id="recent-method-distillation",
            project_id="project-a",
            run_type="source_method_distillation",
            trigger="manual",
            status=RunStatus.RUNNING,
        )
    )
    try:
        stale_at = (datetime.now(timezone.utc) - timedelta(seconds=METHOD_DISTILLATION_RECOVERY_TIMEOUT_SECONDS + 1)).isoformat()
        repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", (stale_at, stale["id"]))
        repo._commit()

        recovered = recover_abandoned_source_method_distillations(repo)

        assert recovered == [stale["id"]]
        stale_run = repo.get_run("project-a", stale["id"])
        assert stale_run["status"] == "failed"
        assert stale_run["output_refs"]["failure"]["code"] == "abandoned_source_method_distillation"
        assert repo.get_run("project-a", recent["id"])["status"] == "running"
        events = repo.list_run_events(project_id="project-a", run_id=stale["id"])
        assert any(event["event_type"] == "knowledge.method_distillation.recovered" for event in events)
    finally:
        repo.close()


def test_promptops_source_distillation_uses_a_bounded_candidate_and_timeout_contract(monkeypatch):
    requests = []

    class RecordingPromptOps:
        def run_structured(self, request):
            requests.append(request)
            return SimpleNamespace(output={"candidates": []}, run_id="prompt-bounded", provider="test", model="test-model")

    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_LLM_PROVIDER", "deepseek")
    raw, provenance = PromptOpsDistillationProvider(RecordingPromptOps()).distill(
        project_id="project-a",
        source={"id": "source-a", "project_id": "project-a", "content_hash": "a" * 64, "source_type": "meeting_notes", "origin": "test", "raw_content": SOURCE_TEXT},
    )

    assert raw == {"candidates": []}
    assert provenance["run_id"] == "prompt-bounded"
    assert requests[0].max_tokens == METHOD_DISTILLATION_MAX_TOKENS
    assert requests[0].timeout_seconds == METHOD_DISTILLATION_TIMEOUT_SECONDS
    assert f"at most {MAX_METHOD_CANDIDATES}" in requests[0].system_prompt
    assert "MANDATORY_NON_EMPTY_MANIFEST_KEYS" in requests[0].system_prompt
    assert "byte-for-byte from SOURCE_DATA" in requests[0].system_prompt

    PromptOpsDistillationProvider(RecordingPromptOps()).retry_distill(
        project_id="project-a",
        source={"id": "source-a", "project_id": "project-a", "content_hash": "a" * 64, "source_type": "meeting_notes", "origin": "test", "raw_content": SOURCE_TEXT},
        validation_error="distillation contract requires critical_review",
    )
    assert "distillation contract requires critical_review" in requests[1].system_prompt
    assert "critical_review with author_assumptions" in requests[1].system_prompt
    assert "MANDATORY_NON_EMPTY_MANIFEST_KEYS" in requests[1].system_prompt
