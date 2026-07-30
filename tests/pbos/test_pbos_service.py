import pytest

from app.artifacts import ArtifactGraphStore, ArtifactStatus, ArtifactType, MissionArtifact, PersonalExecutionPlanArtifact, PersonalProfileArtifact, SOPVersionArtifact
from app.pbos import PBOSService
from app.pbos import PBOSProjectionService
from app.pbos import PBOSReportService


def _mission(store, mission_id: str = "mission") -> MissionArtifact:
    mission = MissionArtifact(
        artifact_id=mission_id,
        project_id="personal",
        mission_id=mission_id,
        title=mission_id,
        label=mission_id,
    )
    store.add(mission)
    return mission


def test_pbos_requires_evidence_before_claiming_personal_plan(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    service = PBOSService(store, "personal")
    plan = service.compile_plan("mission-1")
    assert plan.compilation_state == "capture_required"
    assert plan.evidence_gap_plan


def _accepted_outcome(
    service: PBOSService,
    mission_id: str,
    *,
    score: float,
    comparison_key: str = "personal_ai_project_delivery",
    comparison_context: str = "solo-ai-runtime",
    baseline_quality: float | None = None,
):
    record = service.record_execution(
        mission_id,
        "",
        {
            "actions": ["Delivered one reviewable slice."],
            "tool_receipts": [{"kind": "test", "passed": True, "command": "pytest focused"}],
            "reflection": {"completed": "Observed the result and recorded the next adjustment."},
        },
    )
    metrics = {"comparison_context": comparison_context}
    if baseline_quality is not None:
        metrics["baseline_quality"] = baseline_quality
    return service.record_outcome(
        record.artifact_id,
        {
            "quality_score": score,
            "acceptance_status": "accepted",
            "comparison_key": comparison_key,
            "metrics": metrics,
        },
    )


def test_pbos_promotes_only_after_three_comparable_complete_outcomes_with_a_baseline(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    service = PBOSService(store, "personal")
    profile = service.save_profile({"focus": ["AI delivery"]})
    assert isinstance(profile, PersonalProfileArtifact)
    for score in (70, 80, 90):
        _accepted_outcome(service, "mission-1", score=score, baseline_quality=60)
    result = service.evolve()
    assert result["state"] == "promote"
    assert store.get_by_type(ArtifactType.SOP_VERSION)[0].promotion_state == "promote"
    assert store.get_by_type(ArtifactType.CAPABILITY)[0].name == "AI project delivery"


def test_pbos_evolution_requires_a_real_baseline_and_does_not_mix_contexts(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    service = PBOSService(store, "personal")
    for score in (70, 80, 90):
        _accepted_outcome(service, "mission-1", score=score, baseline_quality=None)

    candidate = service.evolve()

    assert candidate["state"] == "candidate"
    assert not store.get_by_type(ArtifactType.SOP_VERSION)

    for score in (82, 83, 84):
        _accepted_outcome(
            service,
            "mission-1",
            score=score,
            comparison_key="ai_delivery",
            comparison_context="project-a",
            baseline_quality=65,
        )
    for score in (82, 83, 84):
        _accepted_outcome(
            service,
            "mission-1",
            score=score,
            comparison_key="ai_delivery",
            comparison_context="project-b",
            baseline_quality=65,
        )

    mixed = service.evolve("ai_delivery")

    assert mixed["state"] == "comparison_context_required"
    assert not store.get_by_type(ArtifactType.SOP_VERSION)


def test_pbos_rollback_restores_the_previous_strategy_after_two_comparable_regressions(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    service = PBOSService(store, "personal")
    for score in (74, 76, 78):
        _accepted_outcome(service, "mission-1", score=score, baseline_quality=60)
    first = service.evolve()
    first_version = first["sop_version"]

    for score in (90, 92, 94):
        _accepted_outcome(service, "mission-1", score=score)
    second = service.evolve()
    second_version = second["sop_version"]
    assert second["state"] == "promote"
    assert second_version.supersedes_id == first_version.artifact_id

    _accepted_outcome(service, "mission-1", score=50)
    _accepted_outcome(service, "mission-1", score=48)
    rollback = service.evolve()

    assert rollback["state"] == "rollback"
    restored = store.get(first_version.artifact_id)
    deprecated = store.get(second_version.artifact_id)
    assert restored.status == ArtifactStatus.ACTIVE
    assert deprecated.status == ArtifactStatus.DEPRECATED


def test_pbos_strategy_genome_and_cockpit_expose_traceable_growth_state(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    service = PBOSService(store, "personal")
    for score in (74, 76, 78):
        _accepted_outcome(service, "mission-1", score=score, baseline_quality=60)
    promoted = service.evolve()
    genome = promoted["sop_version"].genome

    assert {"input_conditions", "decision_rules", "execution_paths", "failure_boundaries", "success_metrics", "verification", "evidence", "confidence"}.issubset(genome)
    cockpit = service.cockpit()
    assert cockpit["strategies"][0]["artifact_id"] == promoted["sop_version"].artifact_id
    assert cockpit["project_health"]["accepted_outcomes"] == 3
    assert cockpit["failure_patterns"] == []


def test_local_capture_is_read_only_and_hashes_declared_file(tmp_path):
    report = tmp_path / "test-report.txt"
    report.write_text("passed", encoding="utf-8")
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store)
    service = PBOSService(store, "personal")
    record = service.capture_local_execution("mission", "", str(tmp_path), ["test-report.txt", "../outside.txt"])
    assert record.tool_receipts[0]["kind"] == "local_file"
    assert record.tool_receipts[0]["path"] == "test-report.txt"


def test_obsidian_projection_preserves_user_edits_as_conflict(tmp_path):
    artifact = PersonalProfileArtifact(project_id="personal", label="Personal profile")
    projection = PBOSProjectionService(tmp_path, "personal")
    assert projection.sync(artifact)["state"] == "synced"
    path = tmp_path / "pbos" / "profile" / f"{artifact.artifact_id}.md"
    path.write_text("user edited", encoding="utf-8")
    assert projection.sync(artifact)["state"] == "conflict"


def test_weekly_report_writes_only_observed_pbos_state(tmp_path):
    service = PBOSService(ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal"), "personal")
    report = PBOSReportService(service, tmp_path).weekly("2026-W31")
    assert report["state"] == "written"
    assert report["path"] == "distillations/每周蒸馏/2026-W31/pbos/personal-growth.md"
    content = (tmp_path / report["path"]).read_text(encoding="utf-8")
    assert "No verified outcome" in content


def test_today_action_and_daily_report_use_the_first_pending_grounded_plan_step(tmp_path):
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission-action")
    plan = PersonalExecutionPlanArtifact(
        project_id="personal",
        mission_id="mission-action",
        title="Close the governed Vault delivery loop",
        compilation_state="context_grounded",
        rationale=["The active project requires a reviewable evidence boundary before expansion."],
        knowledge_context_refs=["vault:03_Projects/active/control-plane.md"],
        phases=[{
            "title": "Freeze the evidence boundary",
            "actions": ["Map the current Vault evidence to the delivery acceptance card."],
            "checks": ["Every delivery claim links to a governed source or receipt."],
        }],
    )
    store.add(plan)
    service = PBOSService(store, "personal")

    action = service.today_action()
    cockpit = service.cockpit()
    report = PBOSReportService(service, tmp_path).periodic("pbos_daily", "2026-07-30")
    content = (tmp_path / report["path"]).read_text(encoding="utf-8")

    assert action["state"] == "recommended"
    assert action["title"] == "Map the current Vault evidence to the delivery acceptance card."
    assert action["success_check"] == "Every delivery claim links to a governed source or receipt."
    assert cockpit["today_action"]["plan_id"] == plan.artifact_id
    assert "Map the current Vault evidence" in content
    assert "Every delivery claim links" in content
    assert "vault:03_Projects/active/control-plane.md" in content
    assert "pbos-managed-sha256" in content


def test_managed_daily_report_refreshes_but_preserves_user_edits_as_a_conflict(tmp_path):
    service = PBOSService(ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal"), "personal")
    reports = PBOSReportService(service, tmp_path)
    first = reports.periodic("pbos_daily", "2026-07-30")
    path = tmp_path / first["path"]

    # Legacy BSC-owned reports are eligible for the integrity-marker upgrade.
    legacy = path.read_text(encoding="utf-8").replace("<!-- pbos-managed-sha256", "<!-- legacy-pbos-managed-sha256")
    path.write_text(legacy, encoding="utf-8")
    assert reports.periodic("pbos_daily", "2026-07-30")["state"] == "written"
    assert "pbos-managed-sha256" in path.read_text(encoding="utf-8")

    path.write_text(path.read_text(encoding="utf-8") + "\nUser note: do not overwrite.\n", encoding="utf-8")
    assert reports.periodic("pbos_daily", "2026-07-30")["state"] == "conflict"


def test_project_scope_hides_another_personal_profile(tmp_path):
    root = tmp_path / "shared"
    alpha = PBOSService(ArtifactGraphStore(str(root), project_id="alpha"), "alpha")
    beta = PBOSService(ArtifactGraphStore(str(root), project_id="beta"), "beta")
    alpha.save_profile({"focus": ["private alpha work"]})
    assert beta.profile() is None


def test_cockpit_prefers_the_last_persisted_profile_and_plan(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store)
    old_profile = PersonalProfileArtifact(
        artifact_id="old-profile",
        project_id="personal",
        focus=["stale profile"],
        created_at="2099-01-01T00:00:00",
    )
    store.add(old_profile)
    old_profile.updated_at = "2020-01-01T00:00:00"
    store._atomic_write_text(store._artifact_path(old_profile.artifact_id), old_profile.model_dump_json(indent=2))
    store._index[old_profile.artifact_id]["updated_at"] = old_profile.updated_at
    store._save_index()
    stale_plan = PersonalExecutionPlanArtifact(
        artifact_id="old-plan",
        project_id="personal",
        mission_id="mission",
        title="stale plan",
        created_at="2099-01-01T00:00:00",
    )
    store.add(stale_plan)
    stale_plan.updated_at = "2020-01-01T00:00:00"
    store._atomic_write_text(store._artifact_path(stale_plan.artifact_id), stale_plan.model_dump_json(indent=2))
    store._index[stale_plan.artifact_id]["updated_at"] = stale_plan.updated_at
    store._save_index()

    service = PBOSService(store, "personal")
    current_profile = service.save_profile({"focus": ["current profile"]})
    current_plan = service.compile_plan("mission")
    cockpit = service.cockpit()

    assert service.profile().artifact_id == current_profile.artifact_id
    assert cockpit["today"]["artifact_id"] == current_plan.artifact_id


def test_one_complete_outcome_cannot_promote_a_strategy(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store)
    service = PBOSService(store, "personal")
    record = service.record_execution("mission", "", {"actions": ["deliver"], "tool_receipts": [{"kind": "test", "verified": True}]})
    service.record_outcome(record.artifact_id, {"quality_score": 99, "acceptance_status": "accepted"})
    assert service.evolve()["state"] == "insufficient_evidence"


def test_cockpit_marks_incomplete_accepted_outcomes_ineligible_for_personal_learning(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store)
    service = PBOSService(store, "personal")
    record = service.record_execution(
        "mission",
        "",
        {"actions": ["Ran the release check."], "tool_receipts": [{"kind": "test", "passed": True}]},
    )
    service.record_outcome(record.artifact_id, {"acceptance_status": "accepted", "quality_score": 100})

    cockpit = service.cockpit()
    vault = tmp_path / "vault"
    vault.mkdir()
    report = PBOSReportService(service, vault).periodic("pbos_daily", "2026-07-30")
    content = (tmp_path / "vault" / report["path"]).read_text(encoding="utf-8")

    assert cockpit["project_health"]["accepted_outcomes"] == 1
    assert cockpit["project_health"]["eligible_personal_outcomes"] == 0
    assert cockpit["outcome_observations"][0]["eligible_for_evolution"] is False
    assert "reflection" in cockpit["outcome_observations"][0]["missing_requirements"]
    assert "not eligible for personal learning" in content


def test_feedback_is_a_traceable_constraint_for_the_next_plan(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store, "mission-1")
    _mission(store, "mission-2")
    service = PBOSService(store, "personal")
    service.save_profile({"focus": ["AI delivery"]})
    first_plan = service.compile_plan("mission-1")
    record = service.record_execution("mission-1", first_plan.artifact_id, {"actions": ["deliver"]})
    outcome = service.record_outcome(record.artifact_id, {"acceptance_status": "accepted", "quality_score": 75})
    feedback = service.record_feedback(outcome.artifact_id, {
        "source": "manual_reflection",
        "sentiment": "negative",
        "statement": "The review needs source citations before approval.",
    })

    next_plan = service.compile_plan("mission-2")

    assert next_plan.feedback_refs == [feedback.artifact_id]
    assert feedback.artifact_id in next_plan.parent_ids
    assert any("The review needs source citations before approval." in item for item in next_plan.rationale)
    assert any("source citations" in action for phase in next_plan.phases for action in phase["actions"])
    assert next_plan.compilation_state == "capture_required"


def test_feedback_requires_an_outcome_in_the_same_project(tmp_path):
    service = PBOSService(ArtifactGraphStore(str(tmp_path), project_id="personal"), "personal")

    try:
        service.record_feedback("missing-outcome", {"statement": "Need more evidence."})
    except ValueError as exc:
        assert str(exc) == "outcome record not found"
    else:
        raise AssertionError("feedback without an outcome must be rejected")


def test_cockpit_exposes_feedback_that_will_constrain_the_next_plan(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="personal")
    _mission(store)
    service = PBOSService(store, "personal")
    record = service.record_execution("mission", "", {"actions": ["deliver"]})
    outcome = service.record_outcome(record.artifact_id, {"acceptance_status": "accepted", "quality_score": 70})
    feedback = service.record_feedback(outcome.artifact_id, {"statement": "Use the evidence atlas in the review."})

    cockpit = service.cockpit()

    assert cockpit["feedback"][0]["artifact_id"] == feedback.artifact_id
    assert cockpit["feedback"][0]["statement"] == "Use the evidence atlas in the review."


def test_pbos_refuses_missing_lineage_references(tmp_path):
    service = PBOSService(ArtifactGraphStore(str(tmp_path), project_id="personal"), "personal")
    with pytest.raises(ValueError, match="Mission"):
        service.compile_plan("missing")
    with pytest.raises(ValueError, match="execution record"):
        service.record_outcome("missing", {"acceptance_status": "accepted", "quality_score": 80})
