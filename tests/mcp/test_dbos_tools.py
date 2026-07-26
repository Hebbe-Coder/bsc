from __future__ import annotations

import pytest

from app.api import dbos_api, mcp_http
from app.core.config import settings
from app.mcp import dbos_tools, server
from app.dbos.external_worker import ExternalWorkerPolicyError


def test_dbos_tools_reject_an_empty_project_id():
    with pytest.raises(ValueError, match="project_id"):
        dbos_tools.dbos_create_mission("", "Title", "Intent")


def test_dbos_mcp_surface_tracks_the_feature_flag(monkeypatch):
    monkeypatch.setattr(settings, "DYNAMIC_BUSINESS_OS_ENABLED", True)
    names = {item["name"] for item in mcp_http._tool_list()}
    assert {
        "dbos_create_mission",
        "dbos_diagnose_mission",
        "dbos_confirm_mission",
        "dbos_execute_mission",
        "dbos_run_external_worker",
        "dbos_cancel_external_worker",
        "dbos_review_mission",
        "dbos_control_center",
        "dbos_stop_mission",
        "dbos_rollback_execution",
    } <= names

    monkeypatch.setattr(settings, "DYNAMIC_BUSINESS_OS_ENABLED", False)
    assert not ({"dbos_create_mission", "dbos_control_center"} & {item["name"] for item in mcp_http._tool_list()})


@pytest.mark.parametrize("role", ["reader", "project_reader"])
def test_dbos_mcp_readers_cannot_mutate(monkeypatch, role):
    monkeypatch.setattr(settings, "DYNAMIC_BUSINESS_OS_ENABLED", True)
    scoped_project = "project-a" if role == "project_reader" else None
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": (role, scoped_project))

    server._authorize_dbos_project("project-a")
    with pytest.raises(PermissionError, match="read-only"):
        server._authorize_dbos_project("project-a", write=True)


def test_dbos_tools_use_the_same_project_scoped_service(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    created = dbos_tools.dbos_create_mission(
        "project-a",
        "Conversion recovery",
        "Recover conversion before a launch window",
        context={"role": "operator", "industry": "ecommerce", "organization_stage": "growth", "goal": "conversion"},
    )
    mission_id = created["mission"]["artifact_id"]

    diagnosed = dbos_tools.dbos_diagnose_mission("project-a", mission_id)
    selected = diagnosed["selection"]["selected"][0]["capability_name"]
    task_id = diagnosed["dynamic_sop"]["phases"][0]["tasks"][0]["task_id"]
    decision = dbos_tools.dbos_record_decision(
        "project-a", mission_id, task_id, "Use the conversion recovery sequence", actor_id="owner",
    )
    confirmed = dbos_tools.dbos_confirm_mission("project-a", mission_id, "owner", [selected])
    control = dbos_tools.dbos_control_center("project-a", mission_id)

    assert confirmed["mission"]["mission_status"] == "confirmed"
    assert control["mission"]["artifact_id"] == mission_id
    assert control["selection"]["selected"][0]["capability_name"] == selected
    assert control["decisions"][0]["artifact_id"] == decision["decision"]["artifact_id"]

    with pytest.raises(ExternalWorkerPolicyError, match="disabled"):
        dbos_tools.dbos_run_external_worker(
            "project-a", mission_id, diagnosed["dynamic_sop"]["artifact_id"], selected,
            "research-worker", "test-model", "https://worker.example/run", {"prompt": "must not leave BSC"}, "external-once",
        )
    updated = dbos_tools.dbos_control_center("project-a", mission_id)
    assert updated["health"]["external_worker_runs_rejected"] == 1


def test_dbos_mcp_stop_uses_the_project_scoped_service(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    created = dbos_tools.dbos_create_mission(
        "project-a",
        "Paused recovery",
        "Pause a conversion recovery plan for review.",
        context={"role": "operator", "industry": "ecommerce", "organization_stage": "growth", "goal": "conversion"},
    )
    mission_id = created["mission"]["artifact_id"]
    diagnosed = dbos_tools.dbos_diagnose_mission("project-a", mission_id)
    selected = diagnosed["selection"]["selected"][0]["capability_name"]
    dbos_tools.dbos_confirm_mission("project-a", mission_id, "owner", [selected])

    stopped = dbos_tools.dbos_stop_mission("project-a", mission_id, "Owner paused the mission.")

    assert stopped["mission"]["mission_status"] == "stopped"
