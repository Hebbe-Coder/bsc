from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_agent_analysis_persists_a_queryable_terminal_projection(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "agent-projection-key")

    async def fake_runtime(**kwargs):
        execution_id = kwargs["execution_id"]
        return {
            "status": "completed",
            "project_id": kwargs["project_id"],
            "execution_id": execution_id,
            "mission": {"title": "Projection", "steps": 1, "mode": "template"},
            "artifacts": 1,
            "gaps": 0,
            "gap_details": [],
            "board": None,
            "board_verdict": "",
            "board_consensus": "",
            "board_votes": {},
            "runtime": {
                "status": "completed",
                "execution_id": execution_id,
                "artifact_scope": "data/artifacts/default/project-a/session-a",
                "iterations": 1,
                "elapsed_ms": 1.0,
                "errors": [],
                "stage_modes": {"business_understanding": "mock"},
                "degraded": False,
                "capability_executions": [{
                    "capability_name": "business_understanding",
                    "status": "success",
                    "model_usage": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                        "cached_tokens": None,
                        "reasoning_tokens": None,
                        "reported": True,
                        "complete": True,
                    },
                }],
            },
            "report": {"business_domain": "test", "objectives": []},
        }

    monkeypatch.setattr("app.capabilities.runner.run_business_runtime", fake_runtime)
    client = TestClient(app)
    response = client.post(
        "/agent/analyze",
        json={"input": "queryable agent execution", "project_id": "project-a"},
        headers={"Authorization": "Bearer agent-projection-key"},
    )

    assert response.status_code == 200
    usage = response.json()["runtime"]["capability_executions"][0]["model_usage"]
    assert usage["total_tokens"] == 15
    assert usage["complete"] is True
    execution_id = response.json()["execution_id"]
    status = client.get(f"/api/orchestrate/{execution_id}")

    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["terminal"] is True
