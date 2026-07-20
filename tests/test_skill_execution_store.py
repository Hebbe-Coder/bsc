from app.core.database import SQLiteBackend
from app.skills.execution_store import SkillExecutionStore


def test_skill_request_defaults_to_configured_provider(monkeypatch):
    from app.api.skill_routes import ExecuteSkillRequest
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_PROVIDER", "deepseek")

    request = ExecuteSkillRequest(skill_id="prd-analysis", params={})

    assert request.llm_provider == "deepseek"


def test_skill_execution_store_persists_and_updates_state(tmp_path):
    backend = SQLiteBackend(str(tmp_path / "skill-executions.db"))
    store = SkillExecutionStore(connection=backend)
    store.create({
        "execution_id": "exec-store-1",
        "skill_id": "business-discovery",
        "status": "running",
        "params": {"idea": "reduce cycle time"},
        "provider": "mock",
        "model_name": "",
        "streaming": False,
        "from_cache": False,
        "manifest_revision": "1.0.0:abc",
    })

    store.update("exec-store-1", status="completed", result="ok")
    loaded = SkillExecutionStore(connection=backend).get("exec-store-1")

    assert loaded["status"] == "completed"
    assert loaded["result"] == "ok"
    assert loaded["params"] == {"idea": "reduce cycle time"}
    assert loaded["completed_at"]


def test_skill_api_queries_completed_execution_after_memory_reset(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import skill_routes
    from app.core.config import settings

    skill_dir = tmp_path / "skills" / "durable-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "id: durable-skill\n"
        "name: Durable Skill\n"
        "version: 1.0.0\n"
        "entrypoint: chain:prd-analysis\n"
        "inputs:\n  - name: idea\n"
        "outputs:\n  - name: result\n"
        "---\n"
        "Persist this execution.\n",
        encoding="utf-8",
    )
    backend = SQLiteBackend(str(tmp_path / "skill-api.db"))
    monkeypatch.setattr("app.skills.execution_store.get_db", lambda: backend)
    monkeypatch.setattr(settings, "SKILL_ROOT", str(tmp_path / "skills"))

    class FakeChain:
        @classmethod
        def create(cls, provider, model_name):
            return cls()

        async def ainvoke(self, input_data):
            return "durable-result"

    monkeypatch.setitem(skill_routes.CHAIN_REGISTRY, "prd-analysis", FakeChain)
    app = FastAPI()
    app.include_router(skill_routes.router)
    client = TestClient(app)

    started = client.post(
        "/api/skill/execute",
        json={
            "skill_id": "durable-skill",
            "params": {"idea": "persist me"},
            "llm_provider": "mock",
            "use_cache": False,
        },
    )
    execution_id = started.json()["execution_id"]
    skill_routes.executions.clear()
    loaded = client.get(f"/api/skill/execution/{execution_id}")

    assert loaded.status_code == 200
    assert loaded.json()["status"] == "completed"
    assert loaded.json()["result"] == "durable-result"
