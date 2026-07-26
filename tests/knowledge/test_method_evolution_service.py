import copy

import pytest

from app.knowledge.growth_contracts import (
    MethodAsset,
    MethodRevision,
    MethodStatus,
    OutputAsset,
    OutputEvaluation,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_evolution import (
    METHOD_EVOLUTION_RUN_TYPE,
    MethodEvolutionError,
    MethodEvolutionService,
)


def _manifest(*, signal: str = "weekly report") -> dict:
    return {
        "task_family": "weekly-report",
        "prompt_only": True,
        "trigger_contract": {
            "positive_signals": [signal],
            "negative_signals": ["quick social post"],
        },
        "applicability": ["weekly reporting"],
        "exclusions": ["quick social post"],
        "inputs": [{"name": "evidence"}],
        "outputs": [{"name": "weekly report"}],
        "steps": ["Review evidence", "Draft the report"],
        "evidence_rules": ["cite sources"],
        "failure_handling": ["stop on missing evidence"],
        "eval_cases": [
            {"id": "positive-1", "type": "should_trigger", "split": "positive", "prompt": "create weekly report from evidence", "expected_method": "weekly-report"},
            {"id": "positive-2", "type": "should_trigger", "split": "positive", "prompt": "prepare weekly report", "expected_method": "weekly-report"},
            {"id": "positive-3", "type": "should_trigger", "split": "positive", "prompt": "review weekly report", "expected_method": "weekly-report"},
            {"id": "near-negative-1", "type": "should_not_trigger", "split": "near_negative", "prompt": "quick social post", "expected_method": ""},
            {"id": "near-negative-2", "type": "should_not_trigger", "split": "near_negative", "prompt": "short social post for a sale", "expected_method": ""},
            {"id": "holdout-1", "type": "should_trigger", "split": "holdout", "prompt": "weekly report for leadership", "expected_method": "weekly-report"},
            {"id": "holdout-2", "type": "edge_case", "split": "holdout", "prompt": "weekly report but quick social post", "expected_method": ""},
        ],
    }


def _baseline_with_outputs(repo: GrowthRepository) -> tuple[dict, dict, list[str]]:
    method = repo.create_method(
        MethodAsset(
            id="weekly-report-method",
            project_id="project-a",
            slug="weekly-report",
            name="Weekly report",
            status=MethodStatus.PUBLISHED,
            active_revision_id="weekly-report-baseline",
        )
    )
    baseline = repo.save_method_revision(
        MethodRevision(
            id="weekly-report-baseline",
            project_id="project-a",
            method_id=method["id"],
            version=1,
            body="# Weekly report baseline\n\nUse evidence.",
            manifest=_manifest(),
            eval_summary={"average_quality": 90, "groundedness": 0.95},
            status=MethodStatus.PUBLISHED,
        )
    )
    output_ids: list[str] = []
    for index in range(3):
        output_id = f"baseline-output-{index}"
        output_ids.append(output_id)
        repo.register_output(
            OutputAsset(
                id=output_id,
                project_id="project-a",
                kind="report",
                content_hash=(chr(ord("a") + index) * 64),
                vault_path=f"outputs/2026/{output_id}.md",
                idempotency_key=f"baseline-run-{index}",
                run_id=f"baseline-run-{index}",
                method_revision_id=baseline["id"],
                status="accepted",
            )
        )
        repo.save_output_evaluation(
            OutputEvaluation(
                project_id="project-a",
                output_id=output_id,
                groundedness=0.95,
                task_fit=0.90,
                usefulness=0.90,
                coherence=0.90,
                format_quality=0.90,
                evaluator_revision=f"baseline-eval-{index}",
            )
        )
    return method, baseline, output_ids


def _start(service: MethodEvolutionService, method: dict, baseline: dict, output_ids: list[str], **overrides):
    values = {
        "project_id": "project-a",
        "method_id": method["id"],
        "candidate_body": "# Weekly report baseline\n\nUse evidence with a concise executive synthesis.",
        "candidate_manifest": copy.deepcopy(baseline["manifest"]),
        "supporting_output_ids": output_ids,
        "mutation_dimension": "body",
        "rationale": "Add a concise executive synthesis while preserving all routing and evidence rules.",
        "idempotency_key": "experiment-1",
        "actor_id": "owner",
    }
    values.update(overrides)
    return service.start(**values)


def test_valid_method_evolution_is_reviewable_not_published_and_has_auditable_lineage(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-evolution.db"))
    try:
        method, baseline, output_ids = _baseline_with_outputs(repo)

        experiment, idempotent = _start(MethodEvolutionService(repo), method, baseline, output_ids)

        assert idempotent is False
        assert experiment["status"] == "eligible_for_review"
        assert experiment["decision"] == "retain"
        assert experiment["baseline_revision_id"] == baseline["id"]
        assert experiment["rollback_revision_id"] == baseline["id"]
        proposal = repo.get_method_proposal("project-a", experiment["candidate_proposal_id"])
        assert proposal["operation"] == "update"
        assert proposal["status"] == "approved"
        assert repo.get_method("project-a", method["id"])["active_revision_id"] == baseline["id"]
        run = repo.get_run("project-a", experiment["id"])
        assert run["run_type"] == METHOD_EVOLUTION_RUN_TYPE
        assert run["status"] == "completed"
        assert run["output_refs"]["publication_status"] == "review_required"
        assert any(event["event_type"] == "knowledge.method_evolution.evaluated" for event in repo.list_run_events(project_id="project-a", run_id=experiment["id"]))
        relations = {(edge["from_id"], edge["to_id"], edge["edge_type"]) for edge in repo.list_lineage("project-a")}
        assert (baseline["id"], proposal["id"], "method_revision_baselines_method_proposal") in relations
        assert (experiment["id"], proposal["id"], "run_evaluates_method_proposal") in relations
    finally:
        repo.close()


def test_method_evolution_rejects_more_than_one_production_dimension(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-evolution-diff.db"))
    try:
        method, baseline, output_ids = _baseline_with_outputs(repo)
        manifest = copy.deepcopy(baseline["manifest"])
        manifest["trigger_contract"] = {
            "positive_signals": ["weekly metrics"],
            "negative_signals": ["quick social post"],
        }

        with pytest.raises(MethodEvolutionError, match="exactly the declared production dimension"):
            _start(
                MethodEvolutionService(repo),
                method,
                baseline,
                output_ids,
                candidate_body="# Changed body and routing",
                candidate_manifest=manifest,
            )

        assert repo.list_method_evolution_runs("project-a") == []
    finally:
        repo.close()


def test_method_evolution_discards_holdout_regression(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-evolution-regression.db"))
    try:
        method, baseline, output_ids = _baseline_with_outputs(repo)
        manifest = copy.deepcopy(baseline["manifest"])
        manifest["trigger_contract"] = {
            "positive_signals": ["weekly metrics"],
            "negative_signals": ["quick social post"],
        }

        experiment, _ = _start(
            MethodEvolutionService(repo),
            method,
            baseline,
            output_ids,
            candidate_body=baseline["body"],
            candidate_manifest=manifest,
            mutation_dimension="trigger_contract",
            rationale="Narrow the trigger to metrics only, then verify the existing weekly-report holdouts do not regress.",
        )

        assert experiment["status"] == "discarded"
        assert experiment["decision"] == "discard"
        holdout = experiment["evaluation_summary"]["evolution"]["holdout"]
        assert holdout["baseline_passed"] is True
        assert holdout["candidate_passed"] is False
        assert holdout["regressed_case_ids"] == ["holdout-1"]
        assert repo.get_method("project-a", method["id"])["active_revision_id"] == baseline["id"]
    finally:
        repo.close()


def test_method_evolution_persists_unavailable_evaluation_and_idempotent_recovery(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "method-evolution-unavailable.db"))
    try:
        method, baseline, output_ids = _baseline_with_outputs(repo)
        manifest = copy.deepcopy(baseline["manifest"])
        repo.upsert_eval_case(
            "project-a",
            "execution-1",
            "method_regression",
            {"method_id": method["id"], "prompt": "render a weekly report"},
        )
        service = MethodEvolutionService(repo)

        experiment, idempotent = _start(
            service,
            method,
            baseline,
            output_ids,
            candidate_manifest=manifest,
        )
        replay, replay_idempotent = _start(
            service,
            method,
            baseline,
            output_ids,
            candidate_manifest=manifest,
        )

        assert idempotent is False
        assert experiment["status"] == "unavailable"
        assert experiment["decision"] == "unavailable"
        assert repo.get_run("project-a", experiment["id"])["status"] == "unavailable"
        assert replay_idempotent is True
        assert replay["id"] == experiment["id"]
        assert len(repo.list_method_evolution_runs("project-a")) == 1
        with pytest.raises(MethodEvolutionError, match="idempotency key"):
            _start(
                service,
                method,
                baseline,
                output_ids,
                candidate_body="# Different candidate",
                candidate_manifest=manifest,
            )
    finally:
        repo.close()
