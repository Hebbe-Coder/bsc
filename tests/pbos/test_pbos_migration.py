from app.artifacts import ArtifactGraphStore, MissionArtifact, PersonalProfileArtifact
from app.pbos import PBOSService
from app.pbos.migration import PBOSMigrationError, export_bundle, import_bundle


def _store(path):
    return ArtifactGraphStore(str(path), tenant_id="tenant", project_id="project", session_id="dbos")


def _source_graph(tmp_path):
    store = _store(tmp_path / "source")
    mission = MissionArtifact(project_id="project", label="Migrate PBOS lineage")
    store.add(mission)
    service = PBOSService(store, "project")
    profile = service.save_profile({"focus": ["delivery"]})
    plan = service.compile_plan(mission.artifact_id)
    execution = service.record_execution(mission.artifact_id, plan.artifact_id, {"actions": ["test"]})
    outcome = service.record_outcome(
        execution.artifact_id,
        {
            "acceptance_status": "accepted",
            "quality_score": 80,
            "outcome_summary": "The migrated delivery completed its recorded evidence handoff.",
        },
    )
    service.record_feedback(outcome.artifact_id, {"statement": "Keep the evidence link."})
    return store, mission, profile


def test_bundle_import_preserves_pbos_parent_closure_and_is_idempotent(tmp_path):
    source, mission, profile = _source_graph(tmp_path)
    destination = _store(tmp_path / "destination")

    bundle = export_bundle(source)
    first = import_bundle(destination, bundle)
    second = import_bundle(destination, bundle)

    assert bundle["artifacts"][0]["artifact_id"] == mission.artifact_id
    assert profile.artifact_id in first["added_ids"]
    assert len(first["added_ids"]) == len(bundle["artifacts"])
    assert second["added_ids"] == []
    assert len(second["skipped_ids"]) == len(bundle["artifacts"])
    assert destination.get_by_type(PersonalProfileArtifact.model_fields["artifact_type"].default)[0].artifact_id == profile.artifact_id


def test_bundle_import_rejects_tampering_before_writing(tmp_path):
    source, _, _ = _source_graph(tmp_path)
    destination = _store(tmp_path / "destination")
    bundle = export_bundle(source)
    bundle["artifacts"][-1]["statement"] = "tampered"

    try:
        import_bundle(destination, bundle)
    except PBOSMigrationError as exc:
        assert str(exc) == "PBOS bundle integrity check failed"
    else:
        raise AssertionError("tampered bundle must be rejected")
    assert destination.count() == 0
