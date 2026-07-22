import json
from pathlib import Path

from app.api import mcp_http
from app.main import app


FIXTURE = Path(__file__).parents[2] / "docs" / "api" / "growth-v1.contract.json"


def test_growth_contract_fixture_matches_registered_rest_and_mcp_surface():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    registered_paths = set(app.openapi()["paths"])
    tool_names = set(mcp_http._TOOL_SPECS)

    assert fixture["version"] == "growth-v1"
    assert set(fixture["rest_paths"]) <= registered_paths
    assert set(fixture["mcp_tools"]) <= tool_names
    assert fixture["pagination"]["maximum_limit"] == 500
    assert fixture["authorization"]["reader"]["mutate"] is False
    assert fixture["errors"]["state_conflict"] == {
        "http_status": 409,
        "mcp_code": -32009,
    }
