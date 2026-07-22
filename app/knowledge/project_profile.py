"""Project profile revisions and truthful knowledge capability status."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from app.core.config import settings
from app.knowledge.growth_contracts import ProjectKnowledgeProfile
from app.knowledge.growth_repository import GrowthRepository, ProfileRevisionConflictError
from app.knowledge.vault import FilesystemWikiVault


class ProfileRevisionConflict(ValueError):
    """Raised when a profile update was based on a stale active revision."""


AvailabilityProbe = Callable[[], bool | None]


class ProjectProfileService:
    """Resolve compatible defaults and govern immutable profile revisions."""

    _PROTECTED_FIELDS = {"project_id", "revision", "actor_id", "created_at", "updated_at"}

    def __init__(
        self,
        repository: GrowthRepository,
        *,
        settings_obj: Any = settings,
        availability_probes: Mapping[str, AvailabilityProbe] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings_obj
        self.availability_probes = dict(availability_probes or {})
        self._update_lock = RLock()

    def get_profile(self, project_id: str) -> ProjectKnowledgeProfile:
        project_id = self._project_id(project_id)
        persisted = self.repository.get_profile(project_id)
        return ProjectKnowledgeProfile.model_validate(persisted or {"project_id": project_id})

    def update_profile(
        self,
        project_id: str,
        changes: Mapping[str, Any],
        *,
        expected_revision: int,
        actor_id: str,
    ) -> ProjectKnowledgeProfile:
        project_id = self._project_id(project_id)
        actor_id = actor_id.strip()
        if not actor_id:
            raise ValueError("actor_id is required for a profile update")
        if expected_revision < 0:
            raise ValueError("expected_revision must be non-negative")
        forbidden = self._PROTECTED_FIELDS.intersection(changes)
        if forbidden:
            raise ValueError("profile identity and audit fields cannot be updated directly")

        # This lock closes stale-write races for callers sharing this service.
        # The repository remains the owner of durable revision history.
        with self._update_lock:
            current = self.repository.get_profile(project_id)
            current_revision = int(current["revision"]) if current else 0
            if expected_revision != current_revision:
                raise ProfileRevisionConflict(
                    f"expected revision {expected_revision}, current revision {current_revision}"
                )
            base = self.get_profile(project_id).model_dump(mode="python")
            base.update(dict(changes))
            base.update({"project_id": project_id, "revision": current_revision, "actor_id": actor_id})
            candidate = ProjectKnowledgeProfile.model_validate(base)
            try:
                saved = self.repository.save_profile(
                    candidate,
                    actor_id=actor_id,
                    expected_revision=expected_revision,
                )
            except ProfileRevisionConflictError as exc:
                raise ProfileRevisionConflict(str(exc)) from exc
            return ProjectKnowledgeProfile.model_validate(saved)

    def configuration_status(self, project_id: str) -> dict[str, Any]:
        """Report desired configuration separately from observed availability."""
        project_id = self._project_id(project_id)
        persisted_profile = self.repository.get_profile(project_id)
        mapping = self.repository.get_vault(project_id)
        vault = self._vault_status(project_id, mapping)

        scheduler_configured = bool(
            getattr(self.settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)
            and getattr(self.settings, "CELERY_ENABLED", False)
        )
        horizon_configured = bool(
            getattr(self.settings, "HORIZON_ENABLED", False)
            and (
                str(getattr(self.settings, "HORIZON_API_BASE_URL", "")).strip()
                or str(getattr(self.settings, "HORIZON_RUNS_ROOT", "")).strip()
            )
        )
        model_configured = bool(str(getattr(self.settings, "KNOWLEDGE_WIKI_LLM_PROVIDER", "")).strip())
        automation_configured = bool(
            getattr(self.settings, "KNOWLEDGE_GROWTH_ENABLED", False) and scheduler_configured
        )
        return {
            "project_id": project_id,
            "profile": {
                "configured": bool(persisted_profile),
                "available": True,
                "status": "available" if persisted_profile else "default",
                "revision": int(persisted_profile["revision"]) if persisted_profile else 0,
            },
            "vault": vault,
            "scheduler": self._probed_status("scheduler", scheduler_configured),
            "horizon": self._probed_status("horizon", horizon_configured),
            "model": self._probed_status("model", model_configured),
            "automation": self._probed_status("automation", automation_configured),
        }

    def _vault_status(self, project_id: str, mapping: dict[str, Any] | None) -> dict[str, Any]:
        root_value = str(getattr(self.settings, "OBSIDIAN_VAULT_ROOT", "")).strip()
        configured = bool(mapping and root_value)
        result: dict[str, Any] = {
            "configured": configured,
            "available": False if configured else None,
            "status": "unconfigured" if not configured else "unavailable",
            "vault_path": str(mapping.get("vault_path", "")) if mapping else "",
        }
        if not configured:
            return result
        try:
            vault = FilesystemWikiVault(Path(root_value), project_id, str(mapping["vault_path"]))
            available = vault.project_root.is_dir()
            result.update(
                {
                    "available": available,
                    "status": "available" if available else "unavailable",
                    "project_path": str(vault.project_root),
                }
            )
        except Exception:
            # Path details and platform errors are intentionally not surfaced here.
            result.update({"available": False, "status": "unavailable"})
        return result

    def _probed_status(self, name: str, configured: bool) -> dict[str, Any]:
        if not configured:
            return {"configured": False, "available": None, "status": "unconfigured"}
        probe = self.availability_probes.get(name)
        if probe is None:
            return {"configured": True, "available": None, "status": "unknown"}
        try:
            available = probe()
        except Exception:
            available = False
        if available is None:
            return {"configured": True, "available": None, "status": "unknown"}
        return {
            "configured": True,
            "available": bool(available),
            "status": "available" if available else "unavailable",
        }

    @staticmethod
    def _project_id(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project_id is required")
        return normalized
