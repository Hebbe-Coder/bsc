import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import knowledge_workspace_api
from app.api.knowledge_workspace_api import get_wiki_repository
from app.core.config import settings
from app.main import app
from app.middleware import auth
from app.middleware.auth import AuthPrincipal
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.source_triage import SourceTriageService, TriageEvaluation, source_admission_reason
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.primary_web_capture import PrimaryWebCaptureResult
from app.knowledge.wiki_sync import ObsidianSyncService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge import obsidian_local_rest
from app.knowledge.obsidian_local_rest import ObsidianCopilotCommandBridge
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest


def test_workspace_api_requires_scope_and_redacts_raw_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-api.db"))
    repo.configure_vault("project-a", "projects/project-a")
    SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="secret evidence", trust_level="trusted")
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        missing = client.get("/knowledge/sources", headers={"Authorization": "Bearer workspace-admin"})
        scoped = client.get("/knowledge/sources?project_id=project-a", headers={"Authorization": "Bearer workspace-admin"})
        status = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert missing.status_code == 422
        assert scoped.status_code == 200
        source = scoped.json()["data"]["sources"][0]
        assert "raw_content" not in source
        assert status.json()["data"]["vault"]["configured"] is True
        assert status.json()["data"]["vault"]["vault_path"] == "projects/project-a"
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_active_views_exclude_audit_retained_out_of_scope_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-scope-exclusion.db"))
    repo.configure_vault("project-a", "projects/project-a")
    capture = SourceCaptureService(repo)
    visible = capture.capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="visible.md", raw_content="Visible evidence")
    ).source
    excluded = capture.capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="legacy.md", raw_content="Audit-only evidence")
    ).source
    repo.update_source_metadata(
        "project-a",
        excluded["id"],
        {"scope_exclusion": {"reason": "outside_mapped_project_root", "project_root": "projects/project-a"}},
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        status = client.get("/knowledge/workspaces/project-a", headers=headers)
        active_sources = client.get("/knowledge/sources?project_id=project-a", headers=headers)
        audit_sources = client.get(
            "/knowledge/sources?project_id=project-a&include_scope_excluded=true",
            headers=headers,
        )

        assert status.status_code == 200
        assert status.json()["data"]["sources"] == 1
        assert active_sources.status_code == 200
        assert active_sources.json()["data"]["count"] == 1
        assert [item["id"] for item in active_sources.json()["data"]["sources"]] == [visible["id"]]
        assert audit_sources.status_code == 200
        assert {item["id"] for item in audit_sources.json()["data"]["sources"]} == {visible["id"], excluded["id"]}
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_project_picker_is_tenant_scoped(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-project-picker.db"))
    now = repo._now()
    repo._execute(
        "INSERT INTO knowledge_projects (id,tenant_id,name,created_at,metadata,rerank_config) VALUES (?,?,?,?,?,?)",
        ("project-a", settings.DEFAULT_TENANT_ID, "Research intelligence", now, "{}", "{}"),
    )
    repo._execute(
        "INSERT INTO knowledge_projects (id,tenant_id,name,created_at,metadata,rerank_config) VALUES (?,?,?,?,?,?)",
        ("project-b", "foreign-tenant", "Foreign workspace", now, "{}", "{}"),
    )
    repo._commit()
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        assert response.json()["data"] == {
            "projects": [{"id": "project-a", "name": "Research intelligence", "created_at": now}],
            "count": 1,
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_scheduler_availability_is_cached_only_for_read_responses(monkeypatch):
    probes: list[str] = []
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", True)
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://workspace-cache.test:6379/0")
    monkeypatch.setattr(knowledge_workspace_api, "is_celery_real", lambda: True)
    monkeypatch.setattr(
        knowledge_workspace_api,
        "is_celery_broker_available",
        lambda: probes.append("broker") or False,
    )
    knowledge_workspace_api._reset_scheduler_availability_cache()
    try:
        assert knowledge_workspace_api._scheduler_available() is False
        assert knowledge_workspace_api._scheduler_available() is False
        assert probes == ["broker"]

        monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://workspace-cache-next.test:6379/0")
        assert knowledge_workspace_api._scheduler_available() is False
        assert probes == ["broker", "broker"]
    finally:
        knowledge_workspace_api._reset_scheduler_availability_cache()


def test_workspace_local_rest_probe_is_cached_only_for_enabled_read_responses(monkeypatch):
    probes: list[str] = []

    class Probe:
        def probe(self):
            probes.append("probe")
            return {
                "state": "unavailable",
                "detail_code": "request_timeout",
                "transport": "docker_host_tls",
                "plugin_id": "obsidian-local-rest-api",
                "plugin_version": "",
                "configuration_source": "plugin_config",
            }

    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_URL", "")
    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_API_KEY", "cache-token")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", "C:/workspace-cache")
    monkeypatch.setattr(knowledge_workspace_api.ObsidianLocalRestProbe, "from_settings", lambda _settings: Probe())
    knowledge_workspace_api._reset_local_rest_probe_cache()
    try:
        assert knowledge_workspace_api._local_rest_status()["detail_code"] == "request_timeout"
        assert knowledge_workspace_api._local_rest_status()["detail_code"] == "request_timeout"
        assert probes == ["probe"]

        monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_URL", "https://host.docker.internal:27124")
        assert knowledge_workspace_api._local_rest_status()["detail_code"] == "request_timeout"
        assert probes == ["probe", "probe"]
    finally:
        knowledge_workspace_api._reset_local_rest_probe_cache()


def test_workspace_semantic_triage_is_review_only_and_queryable(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-semantic-triage.db"))
    captured = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://example.com/agent-workflow",
            raw_content="A governed AI agent workflow report.",
            trust_level="reviewed",
            metadata={"admission_gate": "project_triage"},
        )
    )

    class SemanticEvaluator:
        revision = "semantic-source-triage-v1"

        def evaluate(self, *, source, profile):
            return TriageEvaluation(
                relevance=90,
                value=85,
                freshness=80,
                outputability=88,
                connectedness=82,
                evaluator_revision=self.revision,
                reasons=["Project-specific fit is strong."],
            )

    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    monkeypatch.setattr(knowledge_workspace_api, "SemanticSourceTriageEvaluator", SemanticEvaluator)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        response = client.post(
            f"/knowledge/sources/{captured.source['id']}/semantic-triage?project_id=project-a",
            headers=headers,
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["admission"] == "explicit_approval_required"
        assert payload["triage"]["disposition"] == "knowledge_candidate"
        assert "raw_content" not in payload["source"]
        assert repo.get_source("project-a", captured.source["id"])["status"] == "validated"

        approval = client.post(
            f"/knowledge/sources/{captured.source['id']}/status",
            headers=headers,
            json={
                "project_id": "project-a",
                "status": "eligible",
                "triage_id": payload["triage"]["id"],
            },
        )
        assert approval.status_code == 200
        assert approval.json()["data"]["source"]["metadata"]["admission_approval"] == {
            "triage_id": payload["triage"]["id"],
            "profile_revision": 0,
            "evaluator_revision": "semantic-source-triage-v1",
            "approved_at": approval.json()["data"]["source"]["metadata"]["admission_approval"]["approved_at"],
            "actor_id": "http",
        }

        current = client.get(
            f"/knowledge/sources/{captured.source['id']}/triage?project_id=project-a",
            headers=headers,
        )
        assert current.status_code == 200
        assert current.json()["data"]["triage"]["id"] == payload["triage"]["id"]
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_capture_web_creates_reviewable_primary_evidence_linked_to_a_horizon_signal(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-primary-web-capture.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo.configure_vault("project-a", "clients/acme")
    discovery = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://publisher.example/evidence",
            raw_content="Radar discovery only.",
            trust_level="reviewed",
            metadata={
                "admission_gate": "project_triage",
                "evidence_role": "discovery_signal",
                **{key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            },
        )
    ).source

    class Capturer:
        def capture(self, url):
            assert url == "https://publisher.example/evidence"
            return PrimaryWebCaptureResult(
                requested_url=url,
                final_url=url,
                title="Independent primary evidence",
                content="# Independent primary evidence\n\nSource URL: https://publisher.example/evidence\n\nA complete independent primary record with enough material for review.",
                content_type="text/html",
                response_sha256="a" * 64,
            )

    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    monkeypatch.setattr(knowledge_workspace_api, "PrimaryWebCapture", Capturer)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge/sources/capture-web",
            headers={"Authorization": "Bearer workspace-admin"},
            json={
                "project_id": "project-a",
                "url": "https://publisher.example/evidence",
                "discovered_from_source_id": discovery["id"],
            },
        )

        assert response.status_code == 200
        source = response.json()["data"]["source"]
        assert source["source_type"] == "primary_web"
        assert source["status"] == "validated"
        assert "raw_content" not in source
        persisted = repo.get_source("project-a", source["id"])
        assert persisted["metadata"]["evidence_role"] == "primary_capture"
        assert persisted["metadata"]["discovered_from_source_id"] == discovery["id"]
        assert persisted["metadata"]["supports_horizon_signal_ids"] == [discovery["id"]]
        assert persisted["metadata"]["fetch"]["response_sha256"] == "a" * 64

        SourceTriageService(repo).triage_source("project-a", discovery["id"])
        SourceCaptureService(repo).transition_source("project-a", source["id"], SourceStatus.ELIGIBLE)
        horizon = repo.get_source("project-a", discovery["id"])
        assert horizon is not None
        assert horizon["status"] == SourceStatus.ELIGIBLE.value
        assert source_admission_reason(repo, "project-a", horizon) == ""
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_exposes_an_honest_release_gate_without_source_bodies_or_secrets(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-release-gate.db"))
    previous_key = settings.API_KEY
    previous_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.API_KEY = "workspace-admin"
    settings.KNOWLEDGE_WIKI_ENABLED = True
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get(
            "/knowledge/workspaces/project-a",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        gate = data["release_gate"]
        assert gate["status"] == "implemented_with_operational_proof_pending"
        assert gate["contract_revision"] == "e1-knowledge-ecosystem-v1"
        assert set(gate["missing_evidence"]) == {
            "o1_secure_boundary_restart",
            "o2_metadata_views",
            "o3_real_plugin_exports",
            "o4_extraction_reference",
            "o5_visualization_inspection",
            "o6_feedback_cycle",
            "compose_recovery",
            "authorization_isolation",
            "browser_desktop_mobile",
        }
        assert "raw_content" not in str(data)
        assert "api_key" not in str(data)
        assert "Authorization" not in str(data)
    finally:
        settings.API_KEY = previous_key
        settings.KNOWLEDGE_WIKI_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_release_evidence_requires_admin_review_and_changes_only_the_project_gate(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-release-evidence.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    evidence_id = "o1_secure_boundary_restart"
    pending = {
        "evidence": {
            "evidence_id": evidence_id,
            "state": "pending",
            "proof_class": "none",
            "observed_at": "",
            "durable_ids": [],
            "detail_code": "awaiting_observation",
        }
    }
    verified = {
        "evidence": {
            "evidence_id": evidence_id,
            "state": "verified",
            "proof_class": "real",
            "observed_at": "2026-08-01T00:00:00+00:00",
            "durable_ids": ["run:obsidian-restart-1"],
            "detail_code": "restart_verified",
        }
    }
    try:
        submitted = client.post(
            "/knowledge/workspaces/project-a/release-evidence",
            headers={"Authorization": "Bearer workspace-admin"},
            json=pending,
        )
        assert submitted.status_code == 200
        assert submitted.json()["data"]["evidence"]["state"] == "pending"
        assert submitted.json()["data"]["evidence"]["revision"] == 1

        status = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})
        assert status.status_code == 200
        gate = status.json()["data"]["release_gate"]
        assert evidence_id in gate["pending_evidence"]
        assert gate["status"] == "implemented_with_operational_proof_pending"

        with monkeypatch.context() as auth_patch:
            auth_patch.setattr(
                auth,
                "_principal_from_bearer",
                lambda key: AuthPrincipal("project_admin", "default", "project-a", "project-key", "") if key == "project-key" else None,
            )
            forbidden = client.post(
                f"/knowledge/workspaces/project-a/release-evidence/{evidence_id}/verify",
                headers={"Authorization": "Bearer project-key"},
                json=verified,
            )
            assert forbidden.status_code == 403

            wrong_project = client.get(
                "/knowledge/workspaces/project-b/release-evidence",
                headers={"Authorization": "Bearer project-key"},
            )
            assert wrong_project.status_code == 403

        reviewed = client.post(
            f"/knowledge/workspaces/project-a/release-evidence/{evidence_id}/verify",
            headers={"Authorization": "Bearer workspace-admin"},
            json=verified,
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["data"]["evidence"] == {
            "evidence_id": evidence_id,
            "state": "verified",
            "proof_class": "real",
            "observed_at": "2026-08-01T00:00:00+00:00",
            "durable_ids": ["run:obsidian-restart-1"],
            "detail_code": "restart_verified",
            "revision": 2,
            "recorded_by": "admin",
        }

        evidence_list = client.get(
            "/knowledge/workspaces/project-a/release-evidence",
            headers={"Authorization": "Bearer workspace-admin"},
        )
        assert evidence_list.status_code == 200
        assert evidence_list.json()["data"]["evidence"] == [reviewed.json()["data"]["evidence"]]
        assert "raw_content" not in evidence_list.text
        assert "api_key" not in evidence_list.text
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_release_evidence_rejects_unreviewed_verified_claims_and_source_bodies(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-release-evidence-input.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        verified_submission = client.post(
            "/knowledge/workspaces/project-a/release-evidence",
            headers={"Authorization": "Bearer workspace-admin"},
            json={
                "evidence": {
                    "evidence_id": "o1_secure_boundary_restart",
                    "state": "verified",
                    "proof_class": "real",
                    "observed_at": "2026-08-01T00:00:00+00:00",
                    "durable_ids": ["run:unreviewed"],
                    "detail_code": "claimed",
                }
            },
        )
        assert verified_submission.status_code == 400

        body_attempt = client.post(
            "/knowledge/workspaces/project-a/release-evidence",
            headers={"Authorization": "Bearer workspace-admin"},
            json={
                "evidence": {
                    "evidence_id": "o1_secure_boundary_restart",
                    "state": "pending",
                    "proof_class": "none",
                    "raw_content": "must not enter the release ledger",
                }
            },
        )
        assert body_attempt.status_code == 422

        forbidden_metadata_attempt = client.post(
            "/knowledge/workspaces/project-a/release-evidence",
            headers={"Authorization": "Bearer workspace-admin"},
            json={
                "evidence": {
                    "evidence_id": "o1_secure_boundary_restart",
                    "state": "pending",
                    "proof_class": "none",
                    "source_url": "https://must-not-be-stored.example",
                }
            },
        )
        assert forbidden_metadata_attempt.status_code == 422
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_maintenance_run_persists_scoped_sources_and_task_constraints(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-maintenance-inputs.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    captured = {}

    def start_run(self, **kwargs):
        captured.update(kwargs)
        return {"status": "queued", "run_id": "maintenance-run"}

    monkeypatch.setattr(knowledge_workspace_api.WikiCommandService, "start_run", start_run)
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge/runs",
            headers={"Authorization": "Bearer workspace-admin"},
            json={
                "project_id": "project-a",
                "job_type": "wiki_maintenance",
                "source_ids": ["source-a", "source-a", "source-b"],
                "task_constraints": ["Map the source to the project boundary.", "Map the source to the project boundary."],
            },
        )

        assert response.status_code == 200
        assert captured["input_refs"] == {
            "source_ids": ["source-a", "source-b"],
            "task_constraints": ["Map the source to the project boundary."],
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_exposes_the_last_integrated_growth_cycle(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-growth-status.db"))
    run = KnowledgeRun(id="growth-daily-1", project_id="project-a", run_type="growth_daily", trigger="manual")
    repo.create_run(run)
    repo.update_run_status(
        "project-a",
        run.id,
        RunStatus.COMPLETED,
        output_refs={
            "sync": {
                "status": "completed",
                "sources": {"created": 2, "duplicates": 1},
                "outputs": {"registered": 1, "duplicates": 0},
                "triage": {"evaluated": 2, "eligible": 1, "pending_review": 1},
                "metadata_views": {"status": "completed", "created": 2, "updated": 1, "unchanged": 9, "conflicts": 0},
            },
            "growth": {"status": "generated", "period": "2026-07-23"},
        },
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        growth = response.json()["data"]["growth"]
        assert growth["status"] == "completed"
        assert growth["last_run"]["id"] == run.id
        assert growth["sync"] == {
            "status": "completed",
            "sources": {"created": 2, "duplicates": 1},
            "outputs": {"registered": 1, "duplicates": 0},
            "triage": {"evaluated": 2, "eligible": 1, "pending_review": 1},
            "metadata_views": {"status": "completed", "created": 2, "updated": 1, "unchanged": 9, "conflicts": 0},
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_distinguishes_missing_plugin_folder_from_ready_export_route(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-plugin-route.db"))
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "bsc-plugins.json").write_text(
        """{
  "plugins": [
    {
      "id": "obsidian-clipper",
      "name": "Obsidian Clipper exports",
      "adapter": "filesystem_drop",
      "input_paths": ["00_Inbox/web-clipper"]
    }
  ]
}
""",
        encoding="utf-8",
    )
    repo.configure_vault("project-a", "projects/project-a")
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        missing = client.get("/knowledge/workspaces/project-a", headers=headers)
        assert missing.status_code == 200
        missing_plugin = missing.json()["data"]["plugins"]["plugins"][0]
        assert missing_plugin["path_status"] == "missing"
        assert missing_plugin["status"] == "awaiting_trust"
        assert missing_plugin["trust_state"] == "untrusted"

        (project_root / "00_Inbox" / "web-clipper").mkdir(parents=True)
        ready = client.get("/knowledge/workspaces/project-a", headers=headers)
        assert ready.status_code == 200
        ready_plugin = ready.json()["data"]["plugins"]["plugins"][0]
        assert ready_plugin["path_status"] == "ready"
        assert ready_plugin["status"] == "awaiting_trust"
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_exposes_bounded_horizon_import_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-horizon-status.db"))
    SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://example.com/horizon-signal",
            raw_content="Immutable Horizon evidence.",
            trust_level="reviewed",
        )
    )
    run = KnowledgeRun(id="horizon-import-1", project_id="project-a", run_type="horizon_capture", trigger="manual")
    repo.create_run(run)
    repo.update_run_status(
        "project-a",
        run.id,
        RunStatus.COMPLETED,
        output_refs={
            "horizon_run_id": "run-native-1",
            "stage": "enriched",
            "source_mode": "run_store",
            "horizon": {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 0},
        },
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        horizon = response.json()["data"]["horizon"]
        assert horizon["captured_sources"] == 1
        assert horizon["last_run"] == {
            "id": "horizon-import-1",
            "status": "completed",
            "updated_at": repo.get_run("project-a", run.id)["updated_at"],
            "horizon_run_id": "run-native-1",
            "stage": "enriched",
            "source_mode": "run_store",
            "accepted": 1,
            "created": 1,
            "duplicates": 0,
            "rejected": 0,
            "skipped": False,
            "outcome": "processed",
            "items_observed": 1,
            "failure": None,
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_distinguishes_horizon_channel_failure_from_empty_result(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-horizon-channel-failure.db"))
    run = KnowledgeRun(id="horizon-channel-failure", project_id="project-a", run_type="horizon_capture", trigger="manual")
    repo.create_run(run)
    repo.update_run_status(
        "project-a",
        run.id,
        RunStatus.FAILED,
        error="Horizon stage artifact was not found",
        output_refs={
            "outcome": "channel_error",
            "source_mode": "run_store",
            "failure": {"category": "transient_dependency", "code": "horizon_unavailable", "retryable": True},
        },
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        last_run = response.json()["data"]["horizon"]["last_run"]
        assert last_run["status"] == "failed"
        assert last_run["outcome"] == "channel_error"
        assert last_run["items_observed"] == 0
        assert last_run["failure"] == {
            "category": "transient_dependency", "code": "horizon_unavailable", "retryable": True
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_exposes_a_redacted_local_rest_plugin_probe(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-local-rest.db"))
    repo.configure_vault("project-a", "projects/project-a")
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo

    class Probe:
        def probe(self):
            return {
                "state": "connected",
                "detail_code": "authenticated_manifest_verified",
                "transport": "loopback_tls",
                "plugin_id": "obsidian-local-rest-api",
                "plugin_version": "5.0.2",
                "configuration_source": "runtime_env",
            }

    monkeypatch.setattr(knowledge_workspace_api.ObsidianLocalRestProbe, "from_settings", lambda _settings: Probe())
    knowledge_workspace_api._reset_local_rest_probe_cache()
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        assert response.json()["data"]["local_rest"] == {
            "state": "connected",
            "detail_code": "authenticated_manifest_verified",
            "transport": "loopback_tls",
            "plugin_id": "obsidian-local-rest-api",
            "plugin_version": "5.0.2",
            "configuration_source": "runtime_env",
        }
        assert "api_key" not in str(response.json()).lower()
    finally:
        knowledge_workspace_api._reset_local_rest_probe_cache()
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_keeps_local_rest_idle_until_authorized_and_explicitly_enabled(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-local-rest-idle.db"))
    repo.configure_vault("project-a", "projects/project-a")
    requested: list[object] = []

    class ForbiddenClient:
        def __init__(self, *_args, **_kwargs):
            requested.append("client_constructed")
            raise AssertionError("disabled Local REST must not construct an HTTP client")

    monkeypatch.setattr(settings, "API_KEY", "workspace-admin")
    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_ENABLED", False)
    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_URL", "")
    monkeypatch.setattr(settings, "OBSIDIAN_LOCAL_REST_API_KEY", "")
    monkeypatch.setattr(obsidian_local_rest.httpx, "Client", ForbiddenClient)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        unauthorized = client.get("/knowledge/workspaces/project-a")
        authorized = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert unauthorized.status_code == 401
        assert authorized.status_code == 200
        assert authorized.json()["data"]["local_rest"]["state"] == "unconfigured"
        assert requested == []
    finally:
        app.dependency_overrides.clear()
        repo.close()


def _configure_project_copilot_workspace(
    tmp_path: Path,
    repo: WikiRepository,
    *,
    trusted: bool,
    save_folder: str,
    model_ready: bool = True,
) -> None:
    project_root = tmp_path / "projects" / "project-a"
    (project_root / "04_Outputs" / "copilot").mkdir(parents=True)
    (project_root / "copilot" / "copilot-conversations").mkdir(parents=True)
    (tmp_path / ".obsidian" / "plugins" / "copilot").mkdir(parents=True)
    settings = {"defaultSaveFolder": save_folder, "defaultModelKey": "test-model|deepseek"}
    if model_ready:
        settings["deepseekApiKey"] = "test-provider-key"
    (tmp_path / ".obsidian" / "plugins" / "copilot" / "data.json").write_text(
        json.dumps(settings), encoding="utf-8"
    )
    repo.configure_vault("project-a", "projects/project-a")
    manifest = ObsidianPluginManifest.from_payload({"plugins": [{
        "id": "copilot",
        "name": "Copilot",
        "adapter": "filesystem_output",
        "input_paths": ["04_Outputs/copilot"],
    }]})
    manifest.write_to(project_root)
    if trusted:
        manifest.set_trust(
            project_root,
            plugin_ids=["copilot"],
            trusted=True,
            actor_id="test-admin",
            reason="test bridge approval",
        )


def test_workspace_copilot_command_requires_trusted_runtime_and_audits_the_dispatch(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-copilot-command.db"))
    _configure_project_copilot_workspace(
        tmp_path, repo, trusted=True,
        save_folder="projects/project-a/copilot/copilot-conversations",
    )
    monkeypatch.setattr(settings, "API_KEY", "workspace-admin")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path))
    app.dependency_overrides[get_wiki_repository] = lambda: repo

    class Bridge:
        def available_commands(self):
            return {
                "state": "available", "detail_code": "allowed_commands_discovered", "transport": "loopback_tls",
                "commands": [{"key": "governed_delivery", "name": "Copilot: PBOS delivery", "available": True}],
            }

        def invoke(self, command_key: str):
            assert command_key == "governed_delivery"
            return {
                "state": "invoked", "detail_code": "command_invoked", "transport": "loopback_tls",
                "command_key": command_key, "command_name": "Copilot: PBOS delivery",
            }

    monkeypatch.setattr(ObsidianCopilotCommandBridge, "from_settings", lambda _settings: Bridge())
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        commands = client.get("/knowledge/workspaces/project-a/copilot/commands", headers=headers)
        response = client.post(
            "/knowledge/workspaces/project-a/copilot/commands/governed_delivery", headers=headers
        )

        assert commands.status_code == 200
        assert commands.json()["data"]["commands"] == [{
            "key": "governed_delivery", "name": "Copilot: PBOS delivery", "available": True,
        }]
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["state"] == "invoked"
        assert body["command"] == {"key": "governed_delivery", "name": "Copilot: PBOS delivery"}
        run = repo.get_run("project-a", body["run_id"])
        assert run["run_type"] == "obsidian_copilot_command"
        assert run["status"] == "completed"
        assert run["input_refs"] == {
            "bridge": "obsidian_local_rest", "plugin_id": "copilot", "command_key": "governed_delivery",
        }
        assert run["output_refs"] == {
            "state": "invoked", "detail_code": "command_invoked", "command_key": "governed_delivery",
        }
    finally:
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_copilot_command_rejects_untrusted_or_misaligned_plugin_without_dispatch(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-copilot-command-rejected.db"))
    _configure_project_copilot_workspace(
        tmp_path, repo, trusted=False,
        save_folder="projects/project-a/copilot/copilot-conversations",
    )
    monkeypatch.setattr(settings, "API_KEY", "workspace-admin")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path))
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    calls: list[str] = []

    class ForbiddenBridge:
        def invoke(self, _command_key: str):
            calls.append("invoke")
            raise AssertionError("an untrusted plugin must not dispatch a Copilot command")

    monkeypatch.setattr(ObsidianCopilotCommandBridge, "from_settings", lambda _settings: ForbiddenBridge())
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        untrusted = client.post(
            "/knowledge/workspaces/project-a/copilot/commands/governed_delivery", headers=headers
        )
        assert untrusted.status_code == 409
        assert untrusted.json()["message"]["code"] == "copilot_bridge_not_trusted"
        first_run = repo.list_runs("project-a")[0]
        assert first_run["run_type"] == "obsidian_copilot_command"
        assert first_run["status"] == "failed"
        assert first_run["output_refs"] == {
            "state": "failed",
            "detail_code": "copilot_bridge_not_trusted",
            "command_key": "governed_delivery",
        }
        assert calls == []

        project_root = tmp_path / "projects" / "project-a"
        manifest = ObsidianPluginManifest.load(project_root)
        manifest.set_trust(
            project_root, plugin_ids=["copilot"], trusted=True, actor_id="test-admin", reason="test approval"
        )
        (tmp_path / ".obsidian" / "plugins" / "copilot" / "data.json").write_text(
            json.dumps({"defaultSaveFolder": "projects/project-a/04_Outputs/copilot"}), encoding="utf-8"
        )
        mismatch = client.post(
            "/knowledge/workspaces/project-a/copilot/commands/governed_delivery", headers=headers
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["message"]["code"] == "copilot_runtime_not_configured"
        second_run = repo.list_runs("project-a")[0]
        assert second_run["status"] == "failed"
        assert second_run["output_refs"]["detail_code"] == "copilot_runtime_not_configured"
        assert calls == []
    finally:
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_copilot_command_rejects_a_known_missing_provider_without_dispatch(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-copilot-model-missing.db"))
    _configure_project_copilot_workspace(
        tmp_path,
        repo,
        trusted=True,
        save_folder="projects/project-a/copilot/copilot-conversations",
        model_ready=False,
    )
    monkeypatch.setattr(settings, "API_KEY", "workspace-admin")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path))
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    calls: list[str] = []

    class ForbiddenBridge:
        def invoke(self, _command_key: str):
            calls.append("invoke")
            raise AssertionError("a missing Copilot provider must not dispatch a command")

    monkeypatch.setattr(ObsidianCopilotCommandBridge, "from_settings", lambda _settings: ForbiddenBridge())
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge/workspaces/project-a/copilot/commands/governed_delivery",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 409
        assert response.json()["message"] == {
            "code": "copilot_model_not_configured",
            "message": "Enable Copilot Plus or configure the selected Copilot provider before opening delivery",
            "detail_code": "copilot_provider_credential_missing",
        }
        assert calls == []
    finally:
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_exposes_horizon_producer_failure_without_claiming_empty_result(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-horizon-producer-failure.db"))
    run = KnowledgeRun(id="horizon-producer-failure", project_id="project-a", run_type="horizon_capture", trigger="schedule")
    repo.create_run(run)
    repo.update_run_status(
        "project-a",
        run.id,
        RunStatus.FAILED,
        error="HZ_EMPTY_INPUT: No items available for scoring.",
        output_refs={
            "outcome": "producer_failure",
            "source_mode": "run_store",
            "failure": {"category": "transient_dependency", "code": "horizon_producer_failed", "retryable": True},
        },
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        last_run = response.json()["data"]["horizon"]["last_run"]
        assert last_run["status"] == "failed"
        assert last_run["outcome"] == "producer_failure"
        assert last_run["items_observed"] == 0
        assert last_run["failure"] == {
            "category": "transient_dependency", "code": "horizon_producer_failed", "retryable": True
        }
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_status_reports_host_horizon_store_when_the_docker_mount_is_not_local(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-host-horizon-status.db"))
    previous_key = settings.API_KEY
    previous_root = settings.HORIZON_RUNS_ROOT
    previous_host = settings.HORIZON_RUNS_HOST_PATH
    previous_enabled = settings.HORIZON_ENABLED
    settings.API_KEY = "workspace-admin"
    settings.HORIZON_ENABLED = True
    settings.HORIZON_RUNS_ROOT = "/horizon-runs"
    settings.HORIZON_RUNS_HOST_PATH = str(tmp_path)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert response.status_code == 200
        assert response.json()["data"]["horizon"]["artifact_store"] == {
            "configured": True,
            "available": True,
            "mode": "host_fallback",
        }
    finally:
        settings.API_KEY = previous_key
        settings.HORIZON_RUNS_ROOT = previous_root
        settings.HORIZON_RUNS_HOST_PATH = previous_host
        settings.HORIZON_ENABLED = previous_enabled
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_requires_the_full_operational_layout_before_reporting_ready(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-layout.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer workspace-admin"}
        repo.configure_vault("project-a", "projects/project-a")
        project_root = vault_root / "projects" / "project-a"
        project_root.mkdir(parents=True)
        for path in ("AGENTS.md", "wiki/index.md", "wiki/overview.md", "wiki/log.md"):
            target = project_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Existing baseline\n", encoding="utf-8")

        incomplete = client.get("/knowledge/workspaces/project-a", headers=headers)
        initialized = client.post("/knowledge/workspaces/project-a/initialize", headers=headers)
        ready = client.get("/knowledge/workspaces/project-a", headers=headers)

        assert incomplete.status_code == 200
        assert incomplete.json()["data"]["vault"]["connection"]["state"] == "mapped_incomplete"
        assert "00_Inbox" in incomplete.json()["data"]["vault"]["connection"]["missing_managed_directories"]
        assert initialized.status_code == 200
        assert "00_Inbox" in initialized.json()["data"]["created_directories"]
        assert ready.status_code == 200
        assert ready.json()["data"]["vault"]["connection"]["state"] == "ready"
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_api_reports_a_disabled_wiki_feature(monkeypatch):
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    client = TestClient(app)
    try:
        response = client.get(
            "/knowledge/workspaces/project-a",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 503
        assert response.json()["message"]["code"] == "knowledge_wiki_disabled"
    finally:
        settings.API_KEY = previous_key


def test_workspace_run_event_replay_is_scoped_and_streams_terminal_events(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-events.db"))
    run = KnowledgeRun(id="run-events", project_id="project-a", run_type="weekly_distillation", trigger="manual")
    repo.create_run(run)
    repo.update_run_status("project-a", run.id, RunStatus.COMPLETED, output_refs={"week": "2026-W30"})
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer workspace-admin"}
        replay = client.get("/knowledge/runs/run-events/events?project_id=project-a", headers=headers)
        stream = client.get("/knowledge/runs/run-events/events/stream?project_id=project-a", headers=headers)
        other = client.get("/knowledge/runs/run-events/events?project_id=project-b", headers=headers)

        assert [event["sequence"] for event in replay.json()["data"]["events"]] == [1, 2]
        assert "event: knowledge.run.completed" in stream.text
        assert other.status_code == 404
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_horizon_capture_records_unavailable_when_sidecar_is_not_configured(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-horizon.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", False)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge/horizon/capture",
            headers={"Authorization": "Bearer workspace-admin"},
            json={"project_id": "project-a", "stage": "filtered"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "unavailable"
        run = repo.list_runs("project-a")[0]
        assert run["run_type"] == "horizon_capture"
        assert run["input_refs"]["horizon_run_id"] == ""
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_feishu_import_is_scoped_auditable_and_credential_safe(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-feishu-import.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    payload = {
        "project_id": "project-a",
        "export": {
            "document_id": "doccnA1",
            "revision_id": "rev-7",
            "document_type": "minutes",
            "source_url": "https://example.feishu.cn/minutes/doccnA1",
            "title": "Weekly knowledge review",
            "content": "Decision: retain evidence gates.",
            "source_time": "2026-07-23T09:00:00+00:00",
        },
    }
    try:
        headers = {"Authorization": "Bearer workspace-admin"}
        created = client.post("/knowledge/sources/feishu/import", headers=headers, json=payload)
        duplicate = client.post("/knowledge/sources/feishu/import", headers=headers, json=payload)
        rejected = client.post(
            "/knowledge/sources/feishu/import",
            headers=headers,
            json={
                "project_id": "project-a",
                "export": {**payload["export"], "access_token": "do-not-persist-me"},
            },
        )

        assert created.status_code == 200
        result = created.json()["data"]
        assert result["created"] is True
        assert result["source"]["source_type"] == "feishu_minutes"
        assert result["source"]["metadata"]["feishu_revision_id"] == "rev-7"
        assert "raw_content" not in result["source"]
        assert duplicate.status_code == 200
        assert duplicate.json()["data"]["created"] is False
        assert duplicate.json()["data"]["source"]["id"] == result["source"]["id"]

        run = repo.get_run("project-a", result["run_id"])
        assert run and run["run_type"] == "feishu_import"
        assert run["status"] == "completed"
        assert run["output_refs"] == {
            "created": True,
            "source_id": result["source"]["id"],
            "source_type": "feishu_minutes",
            "source_revision": "rev-7",
        }
        assert rejected.status_code == 400
        assert "do-not-persist-me" not in str(repo.list_runs("project-a"))
        assert "do-not-persist-me" not in str(repo.list_sources("project-a"))
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_source_transition_requires_scoped_writer_and_changes_lifecycle(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-transition.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="obsidian_markdown", origin="note.md", raw_content="Review me")
    ).source
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            f"/knowledge/sources/{source['id']}/status",
            headers={"Authorization": "Bearer workspace-admin"},
            json={"project_id": "project-a", "status": "eligible"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["source"]["status"] == "eligible"
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_source_transition_requires_an_authoring_safe_triage_for_governed_evidence(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-transition-triage.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="primary_web",
            origin="https://publisher.example/primary",
            raw_content="Reviewable primary evidence.",
            trust_level="reviewed",
            metadata={"admission_gate": "project_triage"},
        )
    ).source
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            f"/knowledge/sources/{source['id']}/status",
            headers={"Authorization": "Bearer workspace-admin"},
            json={"project_id": "project-a", "status": "eligible"},
        )

        assert response.status_code == 400
        assert "authoring-eligible triage_id" in response.text
        assert repo.get_source("project-a", source["id"])["status"] == "validated"
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_lists_and_reads_growth_distillations_from_the_mapped_vault(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-growth-distillation.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    repo.configure_vault("project-a", "projects/project-a")
    paths = [
        "distillations/weekly/2026-W30/summary.md",
        "distillations/weekly/2026-W30/actions.md",
    ]
    FilesystemWikiVault(vault_root, "project-a", "projects/project-a").commit({
        paths[0]: "# Summary\n\n[source:source-a] supports the project decision.\n",
        paths[1]: "# Actions\n\nVerify [source:source-a] before publication.\n",
    })
    record = repo.record_growth_distillation(
        project_id="project-a",
        period="2026-W30",
        kind="weekly",
        input_hash="a" * 64,
        paths=paths,
        manifest={
            "source_cutoff": "2026-07-24T09:00:00+00:00",
            "generation": {"mode": "llm", "provider": "test", "model": "test-model", "reason": ""},
        },
    )
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        listed = client.get("/knowledge/distillations?project_id=project-a", headers=headers)

        assert listed.status_code == 200
        assert listed.json()["data"] == {
            "count": 1,
            "distillations": [
                {
                    "id": record["id"],
                    "project_id": "project-a",
                    "record_type": "growth",
                    "kind": "weekly",
                    "period": "2026-W30",
                    "week": "2026-W30",
                    "knowledge_path": paths[0],
                    "content_path": paths[1],
                    "context_path": "",
                    "paths": paths,
                    "source_cutoff": "2026-07-24T09:00:00+00:00",
                    "status": "generated",
                    "created_at": record["created_at"],
                    "current": True,
                    "revision_count": 1,
                    "manifest": record["manifest"],
                    "generation": record["manifest"]["generation"],
                }
            ],
        }

        detail = client.get(f"/knowledge/distillations/{record['id']}?project_id=project-a", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["data"]["distillation"]["record_type"] == "growth"
        assert detail.json()["data"]["documents"] == {
            paths[0]: "# Summary\n\n[source:source-a] supports the project decision.\n",
            paths[1]: "# Actions\n\nVerify [source:source-a] before publication.\n",
        }

        cross_project = client.get(f"/knowledge/distillations/{record['id']}?project_id=project-b", headers=headers)
        assert cross_project.status_code == 404
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_reads_the_archived_files_for_a_previous_growth_revision(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "workspace-growth-history.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    repo.configure_vault("project-a", "projects/project-a")
    path = "distillations/weekly/2026-W30/summary.md"
    old_hash = "a" * 64
    current_hash = "b" * 64
    FilesystemWikiVault(vault_root, "project-a", "projects/project-a").commit({
        path: "# Current summary\n\n[source:source-current]\n",
        "distillations/weekly/2026-W30/manifest.json": json.dumps({"input_hash": current_hash}),
        f"distillations/weekly/2026-W30/revisions/{old_hash}/summary.md": "# Archived summary\n\n[source:source-old]\n",
    })
    old = repo.record_growth_distillation(
        project_id="project-a", period="2026-W30", kind="weekly", input_hash=old_hash, paths=[path], manifest={}
    )
    current = repo.record_growth_distillation(
        project_id="project-a", period="2026-W30", kind="weekly", input_hash=current_hash, paths=[path], manifest={}
    )
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        listed = client.get("/knowledge/distillations?project_id=project-a", headers=headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["data"]["distillations"]] == [current["id"]]
        assert listed.json()["data"]["distillations"][0]["current"] is True
        assert listed.json()["data"]["distillations"][0]["revision_count"] == 2

        history = client.get(
            "/knowledge/distillations?project_id=project-a&include_history=true",
            headers=headers,
        )
        assert history.status_code == 200
        history_by_id = {item["id"]: item for item in history.json()["data"]["distillations"]}
        assert set(history_by_id) == {old["id"], current["id"]}
        assert history_by_id[old["id"]]["current"] is False
        assert history_by_id[current["id"]]["current"] is True

        archived_detail = client.get(f"/knowledge/distillations/{old['id']}?project_id=project-a", headers=headers)
        current_detail = client.get(f"/knowledge/distillations/{current['id']}?project_id=project-a", headers=headers)

        assert archived_detail.status_code == 200
        assert archived_detail.json()["data"]["distillation"]["current"] is False
        assert archived_detail.json()["data"]["distillation"]["revision_count"] == 2
        assert archived_detail.json()["data"]["documents"] == {path: "# Archived summary\n\n[source:source-old]\n"}
        assert current_detail.status_code == 200
        assert current_detail.json()["data"]["distillation"]["current"] is True
        assert current_detail.json()["data"]["distillation"]["revision_count"] == 2
        assert current_detail.json()["data"]["documents"] == {path: "# Current summary\n\n[source:source-current]\n"}
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_admin_operations_are_scoped_and_read_distillation_files(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-operations.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        mapping = client.put(
            "/knowledge/workspaces/project-a/vault",
            headers=headers,
            json={"vault_path": "clients/acme"},
        )
        assert mapping.status_code == 200
        assert mapping.json()["data"]["vault"]["vault_path"] == "clients/acme"

        mapped_status = client.get("/knowledge/workspaces/project-a", headers=headers)
        assert mapped_status.status_code == 200
        assert mapped_status.json()["data"]["vault"]["connection"]["state"] == "mapped_uninitialized"

        plugin_bridge = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={
                "plugins": [
                    {
                        "id": "readwise",
                        "name": "Readwise Export",
                        "adapter": "filesystem_drop",
                        "input_paths": ["raw/readwise"],
                    }
                ]
            },
        )
        assert plugin_bridge.status_code == 200
        assert plugin_bridge.json()["data"]["plugins"][0]["status"] == "awaiting_export"
        assert plugin_bridge.json()["data"]["plugins"][0]["trust_state"] == "trusted"
        manifest = vault_root / "clients" / "acme" / "bsc-plugins.json"
        assert manifest.is_file()
        assert '"id": "readwise"' in manifest.read_text(encoding="utf-8")
        assert (vault_root / "clients" / "acme" / "bsc-plugin-trust.json").is_file()
        plugin_export = vault_root / "clients" / "acme" / "raw" / "readwise" / "highlights.md"
        plugin_export.parent.mkdir(parents=True, exist_ok=True)
        plugin_export.write_text("A verified plugin export", encoding="utf-8")
        report = ObsidianSyncService(repo, vault_root).sync(project_id="project-a")
        captured_source = repo.list_sources("project-a")[0]
        assert report["created"] == 1
        assert captured_source["source_type"] == "obsidian_plugin:readwise"
        assert captured_source["metadata"]["obsidian_plugin"] == "readwise"

        revoked = client.put(
            "/knowledge/workspaces/project-a/plugins/trust",
            headers=headers,
            json={"plugin_ids": ["readwise"], "trusted": False, "reason": "fixture revocation"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["data"]["plugins"][0]["status"] == "awaiting_trust"
        assert ObsidianSyncService(repo, vault_root).sync(project_id="project-a")["blocked"] == 1

        invalid_plugin = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={"plugins": [{"id": "escape", "input_paths": ["wiki/escape"]}]},
        )
        assert invalid_plugin.status_code == 400

        duplicate_plugin = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={
                "plugins": [
                    {"id": "readwise", "input_paths": ["raw/readwise"]},
                    {"id": "readwise", "input_paths": ["inbox/readwise"]},
                ]
            },
        )
        assert duplicate_plugin.status_code == 400

        output_bridge = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={
                "plugins": [
                    {
                        "id": "hyperframes",
                        "name": "HyperFrames output",
                        "adapter": "filesystem_output",
                        "input_paths": ["04_Outputs/hyperframes"],
                    }
                ]
            },
        )
        assert output_bridge.status_code == 200
        bridge = output_bridge.json()["data"]["plugins"][0]
        assert bridge["adapter"] == "filesystem_output"
        assert bridge["status"] == "awaiting_output"

        invalid_output_plugin = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={"plugins": [{"id": "output-escape", "adapter": "filesystem_output", "input_paths": ["wiki/escape"]}]},
        )
        assert invalid_output_plugin.status_code == 400

        broad_output_plugin = client.put(
            "/knowledge/workspaces/project-a/plugins",
            headers=headers,
            json={"plugins": [{"id": "output-root", "adapter": "filesystem_output", "input_paths": ["04_Outputs"]}]},
        )
        assert broad_output_plugin.status_code == 400

        source = SourceCaptureService(repo).capture(
            CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="private evidence")
        ).source
        source_response = client.get(f"/knowledge/sources/{source['id']}?project_id=project-a", headers=headers)
        assert source_response.status_code == 200
        assert "raw_content" not in source_response.json()["data"]["source"]

        captured = client.post(
            "/knowledge/sources/capture",
            headers=headers,
            json={
                "project_id": "project-a", "source_type": "manual_upload", "origin": "interview.txt",
                "raw_content": "Customer confirms approval is required.", "trust_level": "reviewed",
            },
        )
        assert captured.status_code == 200
        assert "raw_content" not in captured.json()["data"]["source"]
        capture_events = repo.list_run_events(project_id="project-a", run_id=captured.json()["data"]["run_id"])
        assert any(event["event_type"] == "knowledge.source.captured" for event in capture_events)

        proposal = client.post(
            "/knowledge/proposals",
            headers=headers,
            json={
                "project_id": "project-a",
                "rationale": "No longer needed",
                "operations": [{"operation": "append", "path": "wiki/log.md", "content": "- rejected\n"}],
            },
        ).json()["data"]["proposal"]
        rejected = client.post(
            f"/knowledge/proposals/{proposal['id']}/reject?project_id=project-a", headers=headers
        )
        assert rejected.status_code == 200
        assert rejected.json()["data"]["proposal"]["status"] == "rejected"

        schedule = repo.upsert_schedule(
            project_id="project-a", job_type="source_sync", cron="*/5 * * * *", timezone_name="UTC", enabled=False, next_run_at=""
        )
        paused = client.patch(
            f"/knowledge/schedules/{schedule['id']}", headers=headers,
            json={"project_id": "project-a", "enabled": False},
        )
        assert paused.status_code == 200
        assert paused.json()["data"]["schedule"]["enabled"] == 0

        vault = FilesystemWikiVault(vault_root, "project-a", "clients/acme")
        paths = [
            "distillations/2026-W30/knowledge-action.md",
            "distillations/2026-W30/content-creation.md",
            "distillations/2026-W30/context-pack.md",
        ]
        vault.commit({path: f"# {path}\n" for path in paths})
        record = repo.record_distillation(
            project_id="project-a", week="2026-W30", paths=paths, source_cutoff="cutoff"
        )
        distillation = client.get(f"/knowledge/distillations/{record['id']}?project_id=project-a", headers=headers)
        assert distillation.status_code == 200
        assert set(distillation.json()["data"]["documents"]) == set(paths)

        failed = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
        repo.create_run(failed)
        repo.update_run_status("project-a", failed.id, RunStatus.FAILED, error="temporary")
        retried = client.post(f"/knowledge/runs/{failed.id}/retry?project_id=project-a", headers=headers)
        assert retried.status_code == 200
        retry_id = retried.json()["data"]["run_id"]
        assert repo.get_run("project-a", retry_id)["retry_of"] == failed.id
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_restore_revision_creates_a_scoped_draft_proposal(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-restore.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    repo.configure_vault("project-a", "clients/acme")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="Evidence", trust_level="trusted")
    ).source
    version_one = "---\ntitle: Approval\nkind: concept\n---\nVersion one [source:%s]" % source["id"]
    version_two = "---\ntitle: Approval\nkind: concept\n---\nVersion two [source:%s]" % source["id"]
    contents = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/index.md": "# Index\n",
        "wiki/log.md": "# Log\n",
        "wiki/concepts/approval.md": version_one,
    }
    vault = FilesystemWikiVault(vault_root, "project-a", "clients/acme")
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    contents["wiki/concepts/approval.md"] = version_two
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    page = next(item for item in repo.list_pages("project-a") if item["path"] == "wiki/concepts/approval.md")
    original = next(item for item in repo.list_page_revisions("project-a", page["id"]) if item["version"] == 1)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            f"/knowledge/wiki/pages/{page['id']}/revisions/{original['id']}/restore?project_id=project-a",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 200
        proposal = response.json()["data"]["proposal"]
        assert proposal["status"] == "draft"
        assert proposal["operations"][0]["content"] == version_one
        assert proposal["source_ids"] == [source["id"]]
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()
