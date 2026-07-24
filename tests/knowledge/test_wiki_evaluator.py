from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_repository import WikiRepository


def test_evaluator_persists_project_baselines_and_reports_non_regression(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "wiki-eval.db"))
    evaluator = WikiEvaluator(repo)
    try:
        evaluator.save_case(
            project_id="project-a",
            case_id="citation-case",
            case_type="citation",
            expected={"source_ids": ["source-a"]},
        )
        evaluator.save_case(
            project_id="project-a",
            case_id="sop-case",
            case_type="sop",
            expected={"constraints": ["human approval"]},
        )

        passing = evaluator.evaluate(
            project_id="project-a",
            candidate={"source_ids": ["source-a"], "content": "The SOP requires human approval."},
        )
        failing = evaluator.evaluate(
            project_id="project-a",
            candidate={"source_ids": [], "content": "Automate everything."},
        )

        assert passing.status == "passed"
        assert passing.score == 1.0
        assert passing.baseline_score is None
        assert failing.baseline_score == 1.0
        assert failing.score_delta == -1.0
        assert failing.latency_ms >= 0
        assert {row["summary"]["score"] for row in repo.list_eval_runs("project-a")} == {0.0, 1.0}
        assert failing.status == "failed"
        assert {finding["code"] for finding in failing.findings} == {"missing_expected_source", "missing_required_constraint"}
        assert repo.list_eval_cases("project-b") == []
    finally:
        repo.close()


def test_evaluator_truthfully_reports_missing_baseline(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "wiki-eval-empty.db"))
    try:
        report = WikiEvaluator(repo).evaluate(project_id="project-a", candidate={"content": "Anything"})
        assert report.status == "unavailable"
        assert report.skipped_reason == "missing evaluation baseline"
        assert repo.list_eval_runs("project-a")[0]["status"] == "unavailable"
    finally:
        repo.close()


def test_evaluator_reports_scoped_cases_as_not_applicable_for_other_wiki_paths(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "wiki-eval-scoped.db"))
    evaluator = WikiEvaluator(repo)
    try:
        evaluator.save_case(
            project_id="project-a",
            case_id="workbench-citation",
            case_type="citation",
            expected={"source_ids": ["source-workbench"], "scope_paths": ["wiki/concepts/workbench.md"]},
        )

        unrelated = evaluator.evaluate(
            project_id="project-a",
            candidate={"paths": ["wiki/reviews/provenance-repair.md"], "content": "Repair record."},
        )
        scoped = evaluator.evaluate(
            project_id="project-a",
            candidate={"paths": ["wiki/concepts/workbench.md"], "source_ids": ["source-workbench"], "content": "Cited workbench."},
        )

        assert unrelated.status == "not_applicable"
        assert unrelated.coverage == 0.0
        assert unrelated.skipped_reason == "no applicable evaluation cases"
        assert scoped.status == "passed"
        assert scoped.score == 1.0
    finally:
        repo.close()
