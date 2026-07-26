import pytest

from app.api import mcp_http
from app.core.config import settings
from app.mcp import growth_tools, server


EXPECTED_GROWTH_TOOLS = {
    "knowledge_growth_profile",
    "knowledge_growth_assets",
    "knowledge_growth_source_triage",
    "knowledge_growth_method",
    "knowledge_growth_output",
    "knowledge_growth_feedback",
    "knowledge_growth_failure",
    "knowledge_growth_lineage",
    "knowledge_growth_summary",
    "knowledge_growth_review",
    "knowledge_growth_schedule",
    "knowledge_growth_run",
    "knowledge_growth_distillation",
}


def test_complete_growth_tool_surface_is_independent_of_legacy_wiki(monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)

    names = {item["name"] for item in mcp_http._tool_list()}

    assert EXPECTED_GROWTH_TOOLS <= names
    assert "knowledge_growth_triage" in names
    assert "knowledge_growth_weekly_distill" in names
    assert "wiki_read" not in names


@pytest.mark.parametrize("role", ["admin", "system", "project_admin"])
def test_growth_admin_and_system_roles_can_mutate_scoped_project(monkeypatch, role):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    scoped = "project-a" if role in {"system", "project_admin"} else None
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": (role, scoped))

    server._authorize_growth_project("project-a", "key", write=True)
    if scoped:
        with pytest.raises(PermissionError, match="project"):
            server._authorize_growth_project("project-b", "key", write=True)


@pytest.mark.parametrize("role", ["reader", "project_reader"])
def test_growth_reader_roles_are_read_only(monkeypatch, role):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    scoped = "project-a" if role == "project_reader" else None
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": (role, scoped))

    server._authorize_growth_project("project-a", "reader-key")
    with pytest.raises(PermissionError, match="read-only"):
        server._authorize_growth_project("project-a", "reader-key", write=True)
    if scoped:
        with pytest.raises(PermissionError, match="project"):
            server._authorize_growth_project("project-b", "reader-key")


def test_growth_authorization_reports_availability_and_write_policy(monkeypatch):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("admin", None))
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", False)
    with pytest.raises(RuntimeError, match="disabled"):
        server._authorize_growth_project("project-a")

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", False)
    with pytest.raises(RuntimeError, match="writes are disabled"):
        server._authorize_growth_project("project-a", write=True)


def test_growth_action_permissions_are_stable():
    assert server._growth_action_is_write("method", "list") is False
    assert server._growth_action_is_write("method", "revisions") is False
    assert server._growth_action_is_write("method", "experiments") is False
    assert server._growth_action_is_write("method", "experiment") is False
    assert server._growth_action_is_write("method", "propose") is True
    assert server._growth_action_is_write("method", "distill") is True
    assert server._growth_action_is_write("method", "deprecate") is True
    assert server._growth_action_is_write("method", "evolve") is True
    assert server._growth_action_is_write("output", "file") is True
    assert server._growth_action_is_write("failure", "list") is False
    assert server._growth_action_is_write("failure", "resolve") is True
    assert server._growth_action_is_write("run", "events") is False
    with pytest.raises(ValueError, match="unsupported"):
        server._growth_action_is_write("run", "shell")


def test_idempotent_growth_run_is_unavailable_when_scheduler_feature_is_disabled(monkeypatch):
    class Repository:
        updates = []

        def claim_schedule_run(self, run, key):
            assert run.project_id == "project-a"
            assert key == "manual-1"
            return {"claimed": True, "run_id": "run-a"}

        def update_run_status(self, project_id, run_id, status, **kwargs):
            self.updates.append((project_id, run_id, status.value, kwargs))

    repo = Repository()
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)

    result = growth_tools._start_run(
        repo,
        project_id="project-a",
        job_type="growth_daily",
        idempotency_key="manual-1",
        input_refs={},
    )

    assert result == {"status": "unavailable", "run_id": "run-a"}
    assert repo.updates[0][2] == "unavailable"
    assert repo.updates[0][3]["output_refs"]["failure"]["code"] == "scheduler_disabled"


def test_method_distillation_is_described_as_a_review_only_mcp_write(monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)

    schema = next(item for item in mcp_http._tool_list() if item["name"] == "knowledge_growth_method")["inputSchema"]

    assert "distill" in schema["properties"]["action"]["enum"]
    assert "review-only" in schema["properties"]["payload"]["description"]


def test_method_distillation_mcp_action_passes_the_scoped_source_to_the_governed_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir()

    class Repository:
        def get_vault(self, project_id):
            assert project_id == "project-a"
            return None

        def close(self):
            pass

    class Distiller:
        calls = []

        def __init__(self, repository):
            assert isinstance(repository, Repository)

        def distill(self, *, project_id, source_id, actor_id, candidate_ids):
            self.calls.append((project_id, source_id, actor_id, candidate_ids))
            return {
                "run_id": "source-method-run",
                "proposals": [{"id": "proposal-a", "body": "never returned by the summary transport"}],
                "provider": {"provider": "test", "model": "test-model"},
            }

    monkeypatch.setattr(growth_tools, "_repo", Repository)
    monkeypatch.setattr(growth_tools, "SourceMethodDistillationService", Distiller)

    result = growth_tools.growth_method(
        "project-a",
        "distill",
        payload={"source_id": "source-a", "candidate_ids": ["accepted-candidate-a"]},
    )

    assert Distiller.calls == [("project-a", "source-a", "mcp", ["accepted-candidate-a"])]
    assert result["run_id"] == "source-method-run"
    assert result["publication_status"] == "proposal_only"
    assert result["proposals"][0]["id"] == "proposal-a"
    assert "body" not in result["proposals"][0]


def test_method_evolution_mcp_action_uses_the_governed_service_and_stays_review_only(monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)

    class Repository:
        def get_vault(self, project_id):
            assert project_id == "project-a"
            return None

        def close(self):
            pass

    class Evolution:
        calls = []

        def __init__(self, repository):
            assert isinstance(repository, Repository)

        def start(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "id": "experiment-a",
                "project_id": kwargs["project_id"],
                "candidate_proposal_id": "proposal-a",
                "decision": "retain",
                "status": "eligible_for_review",
            }, False

    monkeypatch.setattr(growth_tools, "_repo", Repository)
    monkeypatch.setattr(growth_tools, "MethodEvolutionService", Evolution)

    result = growth_tools.growth_method(
        "project-a",
        "evolve",
        method_id="method-a",
        payload={
            "candidate_body": "# Candidate",
            "candidate_manifest": {"task_family": "weekly-report"},
            "supporting_output_ids": ["output-a", "output-b", "output-c"],
            "mutation_dimension": "body",
            "rationale": "Keep routing fixed while improving the executive synthesis in the method output.",
            "idempotency_key": "mcp-evolution-1",
        },
    )
    schema = next(item for item in mcp_http._tool_list() if item["name"] == "knowledge_growth_method")["inputSchema"]

    assert Evolution.calls == [{
        "project_id": "project-a",
        "method_id": "method-a",
        "candidate_body": "# Candidate",
        "candidate_manifest": {"task_family": "weekly-report"},
        "supporting_output_ids": ["output-a", "output-b", "output-c"],
        "mutation_dimension": "body",
        "rationale": "Keep routing fixed while improving the executive synthesis in the method output.",
        "idempotency_key": "mcp-evolution-1",
        "actor_id": "mcp",
    }]
    assert result["publication_status"] == "review_required"
    assert result["experiment"]["candidate_proposal_id"] == "proposal-a"
    assert {"evolve", "experiments", "experiment"} <= set(schema["properties"]["action"]["enum"])
