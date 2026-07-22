"""Policy, approval and publication gate for project-scoped methods."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_registry import MethodRegistry
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


_PROJECT_ADMIN_ROLES = {"project_admin", "admin", "system"}
_SYSTEM_ADMIN_ROLES = {"admin", "system"}
_PRIVILEGED_KEYS = {
    "commands",
    "command",
    "hooks",
    "agents",
    "requires_code",
    "requires_filesystem",
    "requires_network",
    "requires_mcp_permission",
    "mcp_permissions",
    "capabilities",
}


class MethodGate:
    def __init__(
        self,
        repository: GrowthRepository,
        registry: MethodRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or MethodRegistry(
            repository, settings.OBSIDIAN_VAULT_ROOT
        )

    def publish_prompt_method(
        self,
        *,
        project_id: str,
        proposal_id: str,
        actor_id: str,
        actor_role: str = "project_admin",
        project_policy_allows: bool | None = None,
        global_policy_allows: bool = True,
        automatic: bool = False,
        policy_revision: str = "unspecified",
        system_admin_approved: bool = False,
        approval_reason: str = "",
        policy_allows: bool | None = None,
    ) -> dict[str, Any]:
        if project_policy_allows is None:
            project_policy_allows = bool(policy_allows)
        proposal = self.repository.get_method_proposal(project_id, proposal_id)
        if not proposal:
            raise KeyError("method proposal not found in project")
        audit = self._start_audit(
            project_id=project_id,
            proposal=proposal,
            actor_id=actor_id,
            actor_role=actor_role,
            project_policy_allows=project_policy_allows,
            global_policy_allows=global_policy_allows,
            automatic=automatic,
            policy_revision=policy_revision,
            system_admin_approved=system_admin_approved,
            approval_reason=approval_reason,
        )
        try:
            if not actor_id or actor_role not in _PROJECT_ADMIN_ROLES:
                raise PermissionError("method publication requires project administrator permission")
            if not project_policy_allows:
                raise PermissionError("project policy does not allow method publication")
            if automatic and not global_policy_allows:
                raise PermissionError("global policy does not allow automatic method publication")
            evaluation = proposal.get("eval_summary") or {}
            if not evaluation.get("eligible"):
                raise ValueError("method proposal has not passed promotion gates")

            manifest = proposal.get("manifest") or {}
            privileged = self._is_privileged(manifest)
            if privileged and (
                actor_role not in _SYSTEM_ADMIN_ROLES
                or not system_admin_approved
                or not approval_reason.strip()
            ):
                raise PermissionError(
                    "privileged methods require explicit system administrator approval"
                )
            method_id = str(proposal.get("method_id") or "")
            if not method_id:
                slug = str(manifest.get("task_family") or f"method-{proposal_id[:8]}")
                method = self.repository.get_method_by_slug(project_id, slug)
                if not method:
                    method = self.registry.create_candidate(
                        project_id,
                        slug=slug,
                        name=str(manifest.get("name") or slug.replace("-", " ").title()),
                        applicability=list(manifest.get("applicability") or []),
                        exclusions=list(manifest.get("exclusions") or []),
                    )
                method_id = method["id"]
                self.repository._execute(
                    "UPDATE knowledge_method_proposals SET method_id=?,updated_at=? WHERE project_id=? AND id=?",
                    (method_id, self.repository._now(), project_id, proposal_id),
                )
                self.repository._commit()
                proposal = self.repository.get_method_proposal(project_id, proposal_id) or {}
            method = self.repository.get_method(project_id, method_id)
            if not method:
                raise KeyError("method not found in project")
            gate_metadata = {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "automatic": automatic,
                "project_policy_allows": project_policy_allows,
                "global_policy_allows": global_policy_allows,
                "policy_revision": policy_revision,
                "privileged": privileged,
                "system_admin_approved": system_admin_approved,
                "approval_reason": approval_reason,
                "findings": list(evaluation.get("findings") or []),
                "audit_run_id": audit["id"],
            }
            published = self.registry.publish_proposal(
                proposal,
                expected_active_revision_id=str(method.get("active_revision_id") or ""),
                gate_metadata=gate_metadata,
            )
            self.repository.update_run_status(
                project_id,
                audit["id"],
                RunStatus.COMPLETED,
                output_refs={
                    "method_id": published["method"]["id"],
                    "revision_id": published["revision"]["id"],
                    "policy_revision": policy_revision,
                },
            )
            return published["method"]
        except Exception as exc:
            self._fail_audit(project_id, audit["id"], exc)
            raise

    def rollback(
        self,
        *,
        project_id: str,
        method_id: str,
        target_revision_id: str,
        actor_id: str,
        actor_role: str,
        reason: str,
    ) -> dict[str, Any]:
        if actor_role not in _PROJECT_ADMIN_ROLES or not actor_id or not reason.strip():
            raise PermissionError("method rollback requires an administrator and a reason")
        method = self.repository.get_method(project_id, method_id)
        if not method:
            raise KeyError("method not found in project")
        return self.registry.rollback(
            project_id,
            method_id,
            target_revision_id=target_revision_id,
            expected_active_revision_id=str(method.get("active_revision_id") or ""),
            actor_id=actor_id,
        )["method"]

    @classmethod
    def _is_privileged(cls, manifest: dict[str, Any]) -> bool:
        if not bool(manifest.get("prompt_only", True)):
            return True

        def visit(value: Any) -> bool:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in _PRIVILEGED_KEYS and item not in (None, False, "", [], {}):
                        return True
                    if visit(item):
                        return True
            elif isinstance(value, list):
                return any(visit(item) for item in value)
            return False

        return visit(manifest)

    def _start_audit(
        self,
        *,
        project_id: str,
        proposal: dict[str, Any],
        actor_id: str,
        actor_role: str,
        project_policy_allows: bool,
        global_policy_allows: bool,
        automatic: bool,
        policy_revision: str,
        system_admin_approved: bool,
        approval_reason: str,
    ) -> dict[str, Any]:
        audit_id = hashlib.sha256(
            f"{project_id}|{proposal['id']}|{actor_id}|{policy_revision}|{uuid4().hex}".encode("utf-8")
        ).hexdigest()[:24]
        return self.repository.create_run(
            KnowledgeRun(
                id=audit_id,
                project_id=project_id,
                run_type="method_publish",
                trigger="automatic" if automatic else "manual",
                status=RunStatus.RUNNING,
                actor_id=actor_id,
                input_refs={
                    "proposal_id": proposal["id"],
                    "actor_role": actor_role,
                    "project_policy_allows": project_policy_allows,
                    "global_policy_allows": global_policy_allows,
                    "policy_revision": policy_revision,
                    "system_admin_approved": system_admin_approved,
                    "approval_reason": approval_reason,
                    "evaluation_findings": list((proposal.get("eval_summary") or {}).get("findings") or []),
                },
            )
        )

    def _fail_audit(self, project_id: str, audit_id: str, exc: Exception) -> None:
        try:
            self.repository.update_run_status(
                project_id,
                audit_id,
                RunStatus.FAILED,
                error=str(exc) or exc.__class__.__name__,
            )
        except Exception:
            # The publication error remains primary; the original run row is
            # still durable and can be reconciled as an interrupted audit.
            pass
