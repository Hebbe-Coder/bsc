from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_http_mcp_advertises_the_dynamic_business_os_tools():
    client = TestClient(app)
    response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {
        "dbos_create_mission",
        "dbos_diagnose_mission",
        "dbos_confirm_mission",
        "dbos_execute_mission",
        "dbos_run_external_worker",
        "dbos_cancel_external_worker",
        "dbos_review_mission",
        "dbos_control_center",
        "dbos_record_feedback",
        "dbos_record_decision",
        "dbos_stop_mission",
        "dbos_rollback_execution",
    }.issubset(names)
