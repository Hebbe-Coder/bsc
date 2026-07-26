from app.artifacts import (
    ArtifactGraphStore,
    CapabilitySelectionArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    MissionArtifact,
    SOPRoutingEvaluationArtifact,
)


def test_dbos_artifacts_round_trip_with_parent_lineage_and_additive_export(tmp_path):
    root = tmp_path / "artifacts"
    store = ArtifactGraphStore(str(root), tenant_id="tenant-a", project_id="project-a", session_id="session-a")
    mission = MissionArtifact(project_id="project-a", label="Mission", mission_id="mission-a")
    store.add(mission)
    diagnosis = DiagnosisArtifact(project_id="project-a", label="Diagnosis", mission_id=mission.artifact_id, parent_ids=[mission.artifact_id])
    store.add(diagnosis)
    selection = CapabilitySelectionArtifact(
        project_id="project-a",
        label="Selection",
        mission_id=mission.artifact_id,
        diagnosis_id=diagnosis.artifact_id,
        parent_ids=[diagnosis.artifact_id],
    )
    store.add(selection)
    sop = DynamicSOPArtifact(
        project_id="project-a",
        label="SOP",
        mission_id=mission.artifact_id,
        diagnosis_id=diagnosis.artifact_id,
        selection_id=selection.artifact_id,
        parent_ids=[diagnosis.artifact_id, selection.artifact_id],
    )
    store.add(sop)
    evaluation = SOPRoutingEvaluationArtifact(
        project_id="project-a",
        label="Routing evaluation",
        mission_id=mission.artifact_id,
        diagnosis_id=diagnosis.artifact_id,
        selection_id=selection.artifact_id,
        dynamic_sop_id=sop.artifact_id,
        evaluation_status="passed",
        holdout_passed=True,
        parent_ids=[mission.artifact_id, diagnosis.artifact_id, selection.artifact_id, sop.artifact_id],
    )
    store.add(evaluation)

    reopened = ArtifactGraphStore(str(root), tenant_id="tenant-a", project_id="project-a", session_id="session-a")
    restored = reopened.get(sop.artifact_id)
    export = reopened.export(project_id="project-a")

    assert isinstance(restored, DynamicSOPArtifact)
    assert restored.parent_ids == [diagnosis.artifact_id, selection.artifact_id]
    assert [item["artifact_id"] for item in export["_artifact_graph"]["dbos"]["missions"]] == [mission.artifact_id]
    assert [item["artifact_id"] for item in export["_artifact_graph"]["dbos"]["dynamic_sops"]] == [sop.artifact_id]
    assert [item["artifact_id"] for item in export["_artifact_graph"]["dbos"]["sop_routing_evaluations"]] == [evaluation.artifact_id]
    assert reopened.get_parents(sop.artifact_id)[0].artifact_id == diagnosis.artifact_id
