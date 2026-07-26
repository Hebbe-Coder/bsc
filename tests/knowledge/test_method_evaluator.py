from app.knowledge.growth_contracts import FeedbackType, MethodAsset, MethodProposal, MethodRevision, MethodStatus, OutputAsset, OutputEvaluation, OutputFeedback
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_routing import MethodRouter


def _manifest(**overrides):
    return {
        "task_family": "weekly-report", "prompt_only": True, "applicability": ["weekly reporting"], "exclusions": [],
        "inputs": [{"name": "evidence"}], "outputs": [{"name": "report"}], "steps": ["Review evidence"],
        "evidence_rules": ["cite sources"], "failure_handling": ["stop on missing evidence"],
        "trigger_contract": {"positive_signals": ["weekly reporting"], "negative_signals": ["quick social post"]},
        "eval_cases": [
            {"id": "case-positive-1", "type": "should_trigger", "prompt": "weekly reporting", "expected_method": "weekly-report"},
            {"id": "case-positive-2", "type": "should_trigger", "prompt": "Need weekly reporting now", "expected_method": "weekly-report"},
            {"id": "case-positive-3", "type": "should_trigger", "prompt": "Prepare the weekly reporting review", "expected_method": "weekly-report"},
            {"id": "case-negative-1", "type": "should_not_trigger", "prompt": "quick social post", "expected_method": ""},
            {"id": "case-negative-2", "type": "should_not_trigger", "prompt": "quick social post for a sale", "expected_method": ""},
            {"id": "case-edge", "type": "edge_case", "prompt": "weekly reporting but quick social post", "expected_method": ""},
        ],
        **overrides,
    }


def _proposal_with_outputs(
    repo,
    qualities=(90, 88, 87),
    groundedness=(0.95, 0.92, 0.91),
    statuses=("accepted", "accepted", "accepted"),
):
    ids = []
    for index, (quality, grounding, status) in enumerate(zip(qualities, groundedness, statuses), 1):
        output_id = f"output-{index}"
        ids.append(output_id)
        repo.register_output(OutputAsset(id=output_id, project_id="project-a", kind="report", content_hash=(str(index) * 64),
                                         vault_path=f"outputs/2026/{output_id}/report.md", idempotency_key=output_id,
                                         run_id=f"run-{index}", status=status))
        repo.save_output_evaluation(OutputEvaluation(id=f"eval-{index}", project_id="project-a", output_id=output_id,
                                                      groundedness=grounding, task_fit=quality / 100, usefulness=quality / 100,
                                                      coherence=quality / 100, format_quality=quality / 100,
                                                      evaluator_revision=f"eval-v{index}"))
    proposal = MethodProposal(id="proposal-a", project_id="project-a", operation="create", body="# Method",
                              manifest=_manifest(), source_output_ids=ids)
    return repo.save_method_proposal(proposal)


def test_evaluator_derives_thresholds_from_immutable_output_records(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-eval.db"))
    try:
        proposal = _proposal_with_outputs(repo)
        result = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda case, _proposal: {"passed": True, "actual": case["expected"]},
                                                evaluator_revision="method-eval-v1", model_revision="deterministic", latency_ms=12)
        assert not [item for item in result["routing"]["cases"] if not item["passed"]], result["routing"]["cases"]
        assert result["eligible"] is True, result["routing"]
        assert result["comparable_uses"] == 3
        assert result["average_quality"] >= 85
        assert result["groundedness"] >= 0.90
        assert all(item["passed"] for item in result["routing"]["cases"])
        assert repo.get_method_proposal("project-a", proposal["id"])["status"] == "approved"
        assert repo.list_eval_runs("project-a")[0]["summary"]["evaluator_revision"] == "method-eval-v1"
    finally:
        repo.close()


def test_evaluator_treats_durably_filed_outputs_as_verified_support(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-filed.db"))
    try:
        proposal = _proposal_with_outputs(
            repo,
            statuses=("accepted", "filed", "accepted"),
        )
        result = MethodEvaluator(repo).evaluate(
            proposal,
            case_runner=lambda case, _proposal: {"passed": True, "actual": case["expected"]},
        )
        assert result["eligible"] is True
        assert result["accepted_or_reused"] is True
    finally:
        repo.close()


def test_evaluator_blocks_regression_security_and_unavailable_replay(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-regression.db"))
    try:
        proposal = _proposal_with_outputs(repo)
        repo.upsert_eval_case("project-a", "security-1", "security", {"output_id": "output-1", "expected": "deny"})
        blocked = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda *_args: False)
        assert blocked["eligible"] is False
        assert blocked["regression_failures"] >= 1
        unavailable = MethodEvaluator(repo).evaluate(proposal, case_runner=None, evaluator_revision="unavailable-v1")
        assert unavailable["eligible"] is False
        assert unavailable["evaluator_status"] == "unavailable"
    finally:
        repo.close()


def test_evaluator_uses_persisted_manifest_and_blocks_schema_mismatch(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-schema.db"))
    try:
        proposal = _proposal_with_outputs(repo, groundedness=(0.7, 0.8, 0.85))
        # An API caller cannot replace the persisted candidate package with an
        # incomplete manifest just by changing the request payload.
        result = MethodEvaluator(repo).evaluate(
            {**proposal, "manifest": {"task_family": "weekly-report"}},
            case_runner=lambda *_args: True,
        )
        assert result["eligible"] is False
        assert result["groundedness"] < 0.90

        # A malformed persisted candidate is rejected and auditable before any
        # runtime evaluation, instead of raising a transient validation error.
        repo._execute(
            "UPDATE knowledge_method_proposals SET manifest_json=? WHERE project_id=? AND id=?",
            (repo._json_dumps({"task_family": "weekly-report"}), "project-a", proposal["id"]),
        )
        repo._commit()
        blocked = MethodEvaluator(repo).evaluate(proposal, case_runner=lambda *_args: True)
        assert blocked["eligible"] is False
        assert blocked["evaluator_status"] == "blocked"
        assert blocked["package_audit"]["blocking"] is True
        assert any(item["rule"] == "PKG004" for item in blocked["package_audit"]["findings"])
    finally:
        repo.close()


def test_evaluator_uses_real_router_for_sibling_confusion_without_callback(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-routing-eval.db"))
    try:
        proposal = _proposal_with_outputs(
            repo,
            statuses=("accepted", "accepted", "accepted"),
        )
        social = repo.create_method(MethodAsset(
            id="social-method", project_id="project-a", slug="social-calendar",
            name="Social calendar", status=MethodStatus.PUBLISHED,
            active_revision_id="social-revision",
        ))
        repo.save_method_revision(MethodRevision(
            id="social-revision", method_id=social["id"], project_id="project-a", version=1,
            body="# Social", status=MethodStatus.PUBLISHED,
            manifest={"trigger_contract": {"positive_signals": ["quick social post"], "negative_signals": []}},
        ))
        manifest = proposal["manifest"]
        manifest["eval_cases"][3] = {
            "id": "case-unrelated", "type": "should_not_trigger", "prompt": "book a lunch meeting", "expected_method": "",
        }
        manifest["eval_cases"][4] = {
            "id": "case-sibling", "type": "should_not_trigger", "prompt": "quick social post", "expected_method": "social-calendar",
        }
        manifest["eval_cases"][5]["expected_method"] = "social-calendar"
        repo._execute(
            "UPDATE knowledge_method_proposals SET manifest_json=? WHERE project_id=? AND id=?",
            (repo._json_dumps(manifest), "project-a", proposal["id"]),
        )
        repo._commit()
        persisted = repo.get_method_proposal("project-a", proposal["id"])

        result = MethodEvaluator(repo).evaluate(persisted)

        assert result["eligible"] is True, result["routing"]
        sibling = next(item for item in result["routing"]["cases"] if item["id"] == "case-sibling")
        assert sibling["selected_method"] == "social-calendar"
        assert sibling["passed"] is True
    finally:
        repo.close()


def test_evaluator_routes_source_distillation_from_nested_trigger_contract():
    proposal = {
        "manifest": {
            "task_family": "intent-quality-product-inspection-loop",
            "applicability": ["generic documentation work"],
            "exclusions": ["unrelated creative writing"],
            "distillation": {
                "trigger_contract": {
                    "positive_signals": ["product inspection", "intent quality"],
                    "negative_signals": ["unrelated creative writing"],
                }
            },
        }
    }

    routed = MethodEvaluator._routing_method(proposal)
    decision = MethodRouter().select([routed], "Run a product inspection focused on intent quality")

    assert decision.selected_slug == "intent-quality-product-inspection-loop"
    assert routed["manifest"]["trigger_contract"]["positive_signals"] == [
        "product inspection",
        "intent quality",
    ]
