from pathlib import Path
from types import SimpleNamespace

import pytest

from app.knowledge.growth_contracts import ProjectKnowledgeProfile
from app.knowledge.growth_repository import GrowthRepository, ProfileRevisionConflictError
from app.knowledge.project_profile import (
    ProfileRevisionConflict,
    ProjectProfileService,
)


def _settings(**overrides):
    values = {
        "OBSIDIAN_VAULT_ROOT": "",
        "KNOWLEDGE_SCHEDULES_ENABLED": False,
        "CELERY_ENABLED": False,
        "HORIZON_ENABLED": False,
        "HORIZON_API_BASE_URL": "",
        "HORIZON_RUNS_ROOT": "",
        "KNOWLEDGE_WIKI_LLM_PROVIDER": "",
        "KNOWLEDGE_GROWTH_ENABLED": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_profile_service_resolves_defaults_without_persisting_them(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "profiles.db"))
    try:
        profile = ProjectProfileService(repo, settings_obj=_settings()).get_profile("project-a")

        assert profile.project_id == "project-a"
        assert profile.revision == 0
        assert profile.language == "zh-CN"
        assert profile.primary_output_types == ["markdown"]
        assert repo.get_profile("project-a") is None
        assert repo.list_profile_revisions("project-a") == []
    finally:
        repo.close()


def test_profile_updates_are_revisioned_audited_and_reject_stale_writers(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "profile-revisions.db"))
    service = ProjectProfileService(repo, settings_obj=_settings())
    try:
        first = service.update_profile(
            "project-a",
            {"research_domains": ["agent systems"], "content_voice": "technical"},
            expected_revision=0,
            actor_id="owner-a",
        )
        second = service.update_profile(
            "project-a",
            {"target_audiences": ["engineering leaders"]},
            expected_revision=1,
            actor_id="editor-b",
        )

        assert first.revision == 1
        assert first.actor_id == "owner-a"
        assert second.revision == 2
        assert second.research_domains == ["agent systems"]
        assert second.target_audiences == ["engineering leaders"]
        assert second.actor_id == "editor-b"
        assert [item["revision"] for item in repo.list_profile_revisions("project-a")] == [2, 1]

        with pytest.raises(ProfileRevisionConflict, match="expected revision 1.*current revision 2"):
            service.update_profile(
                "project-a",
                {"language": "en-US"},
                expected_revision=1,
                actor_id="stale-editor",
            )
    finally:
        repo.close()


def test_profile_updates_require_actor_and_remain_project_scoped(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "profile-scope.db"))
    service = ProjectProfileService(repo, settings_obj=_settings())
    try:
        with pytest.raises(ValueError, match="actor_id"):
            service.update_profile("project-a", {"language": "en-US"}, expected_revision=0, actor_id="")

        service.update_profile(
            "project-a", {"research_domains": ["private-a"]}, expected_revision=0, actor_id="owner-a"
        )
        assert service.get_profile("project-b").research_domains == []
        assert repo.list_profile_revisions("project-b") == []
    finally:
        repo.close()


def test_configuration_status_separates_configuration_from_runtime_availability(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = GrowthRepository(db_path=str(tmp_path / "configuration.db"))
    repo.configure_vault("project-a", "projects/project-a", actor_id="owner")
    settings = _settings(
        OBSIDIAN_VAULT_ROOT=str(vault_root),
        KNOWLEDGE_SCHEDULES_ENABLED=True,
        CELERY_ENABLED=True,
        HORIZON_ENABLED=True,
        HORIZON_API_BASE_URL="https://horizon.example",
        KNOWLEDGE_WIKI_LLM_PROVIDER="deepseek",
        KNOWLEDGE_GROWTH_ENABLED=True,
    )
    service = ProjectProfileService(
        repo,
        settings_obj=settings,
        availability_probes={
            "scheduler": lambda: False,
            "horizon": lambda: True,
            "model": lambda: None,
            "automation": lambda: False,
        },
    )
    try:
        service.update_profile("project-a", {"user_role": "researcher"}, expected_revision=0, actor_id="owner")
        status = service.configuration_status("project-a")

        assert status["profile"] == {"configured": True, "available": True, "status": "available", "revision": 1}
        assert status["vault"]["configured"] is True
        assert status["vault"]["available"] is True
        assert Path(status["vault"]["project_path"]) == project_root
        assert status["scheduler"]["configured"] is True
        assert status["scheduler"]["available"] is False
        assert status["scheduler"]["status"] == "unavailable"
        assert status["horizon"]["status"] == "available"
        assert status["model"]["configured"] is True
        assert status["model"]["available"] is None
        assert status["model"]["status"] == "unknown"
        assert status["automation"]["configured"] is True
        assert status["automation"]["status"] == "unavailable"
    finally:
        repo.close()


def test_configuration_status_reports_missing_dependencies_as_unconfigured(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "missing-configuration.db"))
    try:
        status = ProjectProfileService(repo, settings_obj=_settings()).configuration_status("project-a")

        assert status["profile"]["status"] == "default"
        assert status["vault"]["status"] == "unconfigured"
        assert status["scheduler"]["status"] == "unconfigured"
        assert status["horizon"]["status"] == "unconfigured"
        assert status["model"]["status"] == "unconfigured"
        assert status["automation"]["status"] == "unconfigured"
    finally:
        repo.close()


def test_profile_compare_and_swap_is_enforced_across_repository_instances(tmp_path):
    database = str(tmp_path / "profile-cas.db")
    first = GrowthRepository(db_path=database)
    second = GrowthRepository(db_path=database)
    try:
        created = first.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", user_role="researcher"),
            actor_id="first",
            expected_revision=0,
        )
        updated = second.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", user_role="operator"),
            actor_id="second",
            expected_revision=created["revision"],
        )
        assert updated["revision"] == 2
        with pytest.raises(ProfileRevisionConflictError, match="expected profile revision 1, current revision 2"):
            first.save_profile(
                ProjectKnowledgeProfile(project_id="project-a", user_role="stale"),
                actor_id="first",
                expected_revision=1,
            )
        assert first.get_profile("project-a")["user_role"] == "operator"
        assert [item["revision"] for item in first.list_profile_revisions("project-a")] == [2, 1]
    finally:
        first.close()
        second.close()


def test_project_source_policy_is_revisioned_with_the_profile_and_validates_retention(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "profile-source-policy.db"))
    service = ProjectProfileService(repo, settings_obj=_settings())
    try:
        profile = service.update_profile(
            "project-a",
            {
                "source_policy": {
                    "primary_origin_prefixes": ["https://research.example/"],
                    "trusted_origin_prefixes": ["https://news.example/"],
                    "community_origin_prefixes": ["https://community.example/"],
                    "blocked_origin_prefixes": ["https://blocked.example/"],
                    "trusted_source_types": ["manual_upload", "web_clip"],
                    "require_triage_source_types": ["horizon_signal"],
                    "primary_retention_days": 730,
                    "trusted_retention_days": 365,
                    "community_retention_days": 30,
                    "untrusted_retention_days": 14,
                }
            },
            expected_revision=0,
            actor_id="owner-a",
        )

        assert profile.revision == 1
        assert profile.source_policy.primary_origin_prefixes == ["https://research.example/"]
        assert profile.source_policy.community_retention_days == 30
        assert repo.get_profile("project-a")["source_policy"]["blocked_origin_prefixes"] == ["https://blocked.example/"]
        assert repo.list_profile_revisions("project-a")[0]["profile"]["source_policy"]["primary_retention_days"] == 730

        with pytest.raises(ValueError, match="retention"):
            service.update_profile(
                "project-a",
                {"source_policy": {"untrusted_retention_days": 0}},
                expected_revision=1,
                actor_id="owner-a",
            )
    finally:
        repo.close()
