import json

from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.main import app


def _event_payload(stream_text: str) -> dict:
    data_line = next(line for line in stream_text.splitlines() if line.startswith("data: "))
    return json.loads(data_line[6:])


def test_growth_sse_replay_terminal_cursor_cross_project_and_bounded_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "API_KEY", "growth-sse-admin")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    repo = GrowthRepository(db_path=str(tmp_path / "growth-sse.db"))
    app.dependency_overrides[get_growth_repository] = lambda: repo
    headers = {"Authorization": "Bearer growth-sse-admin"}
    try:
        run = KnowledgeRun(
            project_id="project-a",
            run_type="growth_daily",
            trigger="test",
            status=RunStatus.RUNNING,
            actor_id="system",
        )
        repo.create_run(run)
        repo.append_run_event(
            project_id="project-a",
            run_id=run.id,
            event_type="knowledge.growth.asset.created",
            payload={"asset_id": "asset-a", "secret": "sk-1234567890", "large": "x" * 80_000},
        )
        repo.append_run_event(
            project_id="project-a",
            run_id=run.id,
            event_type="knowledge.growth.model.completed",
            payload={
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "usage": {
                    "provider_calls": 1,
                    "reported_calls": 1,
                    "complete": True,
                    "total_tokens": 3292,
                    "reasoning_tokens": 1384,
                    "api_key": "must-not-leak",
                },
                "attempt_count": 2,
                "retry_count": 1,
                "retry_categories": ["server_error", "not_a_safe_category"],
            },
        )
        repo.update_run_status("project-a", run.id, RunStatus.COMPLETED, output_refs={"asset_id": "asset-a"})

        with TestClient(app) as client:
            replay = client.get(
                f"/knowledge/projects/project-a/runs/{run.id}/events",
                headers=headers,
                params={"after_sequence": 1, "limit": 2},
            )
            stream = client.get(
                f"/knowledge/projects/project-a/runs/{run.id}/events/stream",
                headers={**headers, "Last-Event-ID": "1"},
            )
            ahead = client.get(
                f"/knowledge/projects/project-a/runs/{run.id}/events",
                headers=headers,
                params={"after_sequence": 99},
            )
            cross = client.get(
                f"/knowledge/projects/project-b/runs/{run.id}/events",
                headers=headers,
            )

        assert replay.status_code == 200
        events = replay.json()["data"]["events"]
        assert [event["sequence"] for event in events] == [2, 3]
        assert all(event["project_id"] == "project-a" for event in events)
        assert events[1]["payload"]["usage"] == {
            "provider_calls": 1,
            "reported_calls": 1,
            "complete": True,
            "total_tokens": 3292,
            "reasoning_tokens": 1384,
        }
        assert events[1]["payload"]["attempt_count"] == 2
        assert events[1]["payload"]["retry_count"] == 1
        assert events[1]["payload"]["retry_categories"] == ["server_error"]
        assert "api_key" not in events[1]["payload"]["usage"]
        assert events[-1]["terminal"] is True
        assert stream.status_code == 200
        assert "id: 2" in stream.text and "id: 3" in stream.text
        assert "sk-1234567890" not in stream.text
        assert len(stream.content) < 70_000
        assert _event_payload(stream.text)["actor"] == "system"
        assert ahead.status_code == 409
        assert ahead.json()["message"]["code"] == "growth_event_sequence_ahead"
        assert cross.status_code == 404
        assert cross.json()["message"]["code"] == "growth_resource_not_found"
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repo.close()
