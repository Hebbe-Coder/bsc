"""Project-scoped method registry with immutable, reproducible publication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
from typing import Any
from uuid import uuid4

import yaml

from app.knowledge.growth_contracts import (
    KnowledgeLineageEdge,
    MethodAsset,
    MethodProposal,
    MethodRevision,
    MethodStatus,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_package_audit import MethodPackageAuditor
from app.knowledge.vault import FilesystemWikiVault


class MethodPublicationConflict(ValueError):
    """Raised when a method changed after the caller read its active revision."""


@dataclass
class _PublishedSwap:
    target: Path
    backup: Path
    had_target: bool


class MethodRegistry:
    """Additive C-layer registry; global Skill discovery remains untouched."""

    _publication_lock = threading.RLock()

    def __init__(self, repository: GrowthRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("method Vault root does not exist")

    def create_candidate(
        self,
        project_id: str,
        *,
        slug: str,
        name: str,
        applicability: list[str] | None = None,
        exclusions: list[str] | None = None,
    ) -> dict[str, Any]:
        candidate = MethodAsset(
            project_id=project_id,
            slug=slug,
            name=name,
            applicability=applicability or [],
            exclusions=exclusions or [],
        )
        existing = self.repository.get_method_by_slug(project_id, candidate.slug)
        if existing:
            if existing.get("name") != candidate.name:
                raise ValueError("method slug is already bound to another candidate")
            return existing
        return self.repository.create_method(candidate)

    def create_proposal(
        self,
        *,
        project_id: str,
        method_id: str,
        operation: str,
        body: str,
        manifest: dict[str, Any],
        source_output_ids: list[str],
        rationale: str = "",
    ) -> dict[str, Any]:
        method = self.repository.get_method(project_id, method_id)
        if not method:
            raise KeyError("method not found in project")
        normalized_manifest = self._validate_manifest(manifest)
        if not body.strip():
            raise ValueError("method body is required")
        package_audit = MethodPackageAuditor().audit(body=body, manifest=normalized_manifest)
        output_ids = list(dict.fromkeys(str(value) for value in source_output_ids if str(value)))
        for output_id in output_ids:
            if not self.repository.get_output(project_id, output_id):
                raise ValueError("method proposal output belongs to another project or is missing")
        fingerprint = json.dumps(
            {
                "project_id": project_id,
                "method_id": method_id,
                "operation": operation,
                "body": body,
                "manifest": normalized_manifest,
                "source_output_ids": output_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        proposal_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        existing = self.repository.get_method_proposal(project_id, proposal_id)
        if existing:
            return existing
        return self.repository.save_method_proposal(
            MethodProposal(
                id=proposal_id,
                project_id=project_id,
                method_id=method_id,
                operation=operation,
                body=body,
                manifest=normalized_manifest,
                source_output_ids=output_ids,
                rationale=rationale,
                package_audit=package_audit,
            )
        )

    def publish_proposal(
        self,
        proposal: dict[str, Any],
        *,
        expected_active_revision_id: str,
        gate_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project_id = str(proposal.get("project_id") or "")
        proposal_id = str(proposal.get("id") or "")
        persisted = self.repository.get_method_proposal(project_id, proposal_id)
        if not persisted:
            raise KeyError("method proposal not found in project")
        self._assert_proposal_immutable(persisted, proposal)
        package_audit = MethodPackageAuditor().audit(
            body=str(persisted.get("body") or ""),
            manifest=dict(persisted.get("manifest") or {}),
        )
        if package_audit["blocking"]:
            raise ValueError("method proposal is blocked by static package audit")
        if persisted.get("operation") != "rollback" and not bool(
            (persisted.get("eval_summary") or {}).get("eligible")
        ):
            raise ValueError("method proposal has not passed promotion gates")
        if persisted.get("operation") == "update" and not bool(
            ((persisted.get("eval_summary") or {}).get("evolution") or {}).get("passed")
        ):
            raise ValueError("updated method proposal requires a passing isolated holdout and non-regression evaluation")
        method_id = str(persisted.get("method_id") or "")
        method = self.repository.get_method(project_id, method_id)
        if not method:
            raise KeyError("method not found in project")

        with self._publication_lock:
            method = self.repository.get_method(project_id, method_id) or {}
            active_revision_id = str(method.get("active_revision_id") or "")
            existing_for_proposal = self._revision_for_proposal(
                project_id, method_id, proposal_id
            )
            if existing_for_proposal:
                if active_revision_id != existing_for_proposal["id"]:
                    raise MethodPublicationConflict(
                        "proposal revision exists but is no longer the active method revision"
                    )
                return {"method": method, "revision": existing_for_proposal}
            if active_revision_id != expected_active_revision_id:
                raise MethodPublicationConflict(
                    "method active revision changed before publication"
                )

            version = self.repository.latest_method_version(project_id, method_id) + 1
            manifest = self._validate_manifest(persisted.get("manifest") or {})
            manifest = {
                **manifest,
                "_bsc": {
                    **dict(manifest.get("_bsc") or {}),
                    "proposal_id": proposal_id,
                    "method_id": method_id,
                    "project_id": project_id,
                    "version": version,
                    "gate": gate_metadata or {},
                },
            }
            revision_id = hashlib.sha256(
                f"{project_id}|{method_id}|{version}|{proposal_id}|{persisted['body']}".encode("utf-8")
            ).hexdigest()[:24]
            revision = MethodRevision(
                id=revision_id,
                method_id=method_id,
                project_id=project_id,
                version=version,
                body=persisted["body"],
                manifest=manifest,
                eval_summary={
                    **dict(persisted.get("eval_summary") or {}),
                    "gate": gate_metadata or {},
                },
                status=MethodStatus.PUBLISHED,
            )
            swap: _PublishedSwap | None = None
            try:
                self._insert_revision(revision)
                swap = self._swap_materialization(method, revision)
                self.repository._execute(
                    "UPDATE knowledge_methods SET status='published',active_revision_id=?,updated_at=? "
                    "WHERE project_id=? AND id=? AND active_revision_id=?",
                    (
                        revision.id,
                        self.repository._now(),
                        project_id,
                        method_id,
                        expected_active_revision_id,
                    ),
                )
                current = self.repository.get_method(project_id, method_id)
                if not current or current.get("active_revision_id") != revision.id:
                    raise MethodPublicationConflict(
                        "method active revision changed during publication"
                    )
                self.repository._execute(
                    "UPDATE knowledge_method_proposals SET status='published',updated_at=? "
                    "WHERE project_id=? AND id=?",
                    (self.repository._now(), project_id, proposal_id),
                )
                if active_revision_id:
                    self._insert_supersession_edge(
                        project_id, active_revision_id, revision.id
                    )
                self.repository._commit()
            except Exception:
                self.repository._get_connection().rollback()
                if swap:
                    try:
                        self._rollback_swap(swap)
                    except OSError:
                        pass
                raise
            else:
                if swap:
                    try:
                        self._finalize_swap(swap)
                    except OSError:
                        # Publication is committed; a stale backup is safe and
                        # can be removed by maintenance without falsifying the result.
                        pass
            return {
                "method": self.repository.get_method(project_id, method_id) or {},
                "revision": self.repository.get_method_revision(project_id, revision.id) or {},
            }

    def resolve(
        self,
        project_id: str,
        *,
        method_id: str = "",
        slug: str = "",
        revision_id: str = "",
    ) -> dict[str, Any]:
        if bool(method_id) == bool(slug):
            raise ValueError("provide exactly one of method_id or slug")
        method = (
            self.repository.get_method(project_id, method_id)
            if method_id
            else self.repository.get_method_by_slug(project_id, slug)
        )
        if not method:
            raise KeyError("method not found in project")
        if method.get("status") != MethodStatus.PUBLISHED.value:
            raise ValueError("method is not published")
        selected_id = revision_id or str(method.get("active_revision_id") or "")
        revision = self.repository.get_method_revision(project_id, selected_id)
        if not revision or revision.get("method_id") != method["id"]:
            raise KeyError("published method revision not found in project")
        if revision.get("status") != MethodStatus.PUBLISHED.value:
            raise ValueError("method revision is not published")
        return {
            "method": method,
            "revision": revision,
            "selection": {
                "method_id": method["id"],
                "revision_id": revision["id"],
                "version": revision["version"],
            },
        }

    def list_revisions(
        self,
        project_id: str,
        method_id: str,
        *,
        limit: int = 100,
        before_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """List immutable method revisions newest-first for API/MCP consumers."""
        return self.repository.list_method_revisions(
            project_id,
            method_id,
            limit=limit,
            before_version=before_version,
        )

    def deprecate(
        self,
        project_id: str,
        method_id: str,
        *,
        actor_id: str,
        reason: str,
        expected_active_revision_id: str | None = None,
    ) -> dict[str, Any]:
        if expected_active_revision_id is None:
            method = self.repository.get_method(project_id, method_id)
            if not method:
                raise KeyError("method not found in project")
            expected_active_revision_id = str(method.get("active_revision_id") or "")
        return self.repository.deprecate_method(
            project_id,
            method_id,
            actor_id=actor_id,
            reason=reason,
            expected_active_revision_id=expected_active_revision_id,
        )

    def supersede(
        self,
        project_id: str,
        method_id: str,
        *,
        replacement_method_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if not actor_id:
            raise ValueError("actor_id is required")
        method = self.repository.get_method(project_id, method_id)
        replacement = self.repository.get_method(project_id, replacement_method_id)
        if not method or not replacement or method_id == replacement_method_id:
            raise ValueError("supersession requires two distinct methods in one project")
        self.repository.add_lineage_edge(
            KnowledgeLineageEdge(
                project_id=project_id,
                from_type="method",
                from_id=method_id,
                to_type="method",
                to_id=replacement_method_id,
                relation="method_supersedes_method",
                metadata={"actor_id": actor_id},
            )
        )
        self.repository._execute(
            "UPDATE knowledge_methods SET status='superseded',updated_at=? WHERE project_id=? AND id=?",
            (self.repository._now(), project_id, method_id),
        )
        self.repository._commit()
        return self.repository.get_method(project_id, method_id) or {}

    def rollback(
        self,
        project_id: str,
        method_id: str,
        *,
        target_revision_id: str,
        expected_active_revision_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if not actor_id:
            raise ValueError("actor_id is required")
        target = self.repository.get_method_revision(project_id, target_revision_id)
        if not target or target.get("method_id") != method_id:
            raise KeyError("rollback target revision not found in project")
        manifest = {
            **dict(target.get("manifest") or {}),
            "rollback_target_revision_id": target_revision_id,
        }
        proposal = self.create_proposal(
            project_id=project_id,
            method_id=method_id,
            operation="rollback",
            body=target["body"],
            manifest=manifest,
            source_output_ids=[],
            rationale=f"Rollback requested by {actor_id} to {target_revision_id}",
        )
        return self.publish_proposal(
            proposal,
            expected_active_revision_id=expected_active_revision_id,
            gate_metadata={
                "actor_id": actor_id,
                "operation": "rollback",
                "rollback_target_revision_id": target_revision_id,
            },
        )

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, dict):
            raise ValueError("method manifest must be a mapping")
        try:
            encoded = json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("method manifest must be JSON-compatible") from exc
        decoded = json.loads(encoded)
        if any("\x00" in value for value in MethodRegistry._strings(decoded)):
            raise ValueError("method manifest contains an unsafe binary payload")
        return decoded

    @staticmethod
    def _strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield str(key)
                yield from MethodRegistry._strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from MethodRegistry._strings(item)

    @staticmethod
    def _assert_proposal_immutable(
        persisted: dict[str, Any], supplied: dict[str, Any]
    ) -> None:
        fields = ("project_id", "method_id", "operation", "body")
        if any(persisted.get(field) != supplied.get(field) for field in fields):
            raise ValueError("method proposal is immutable")
        if persisted.get("manifest") != supplied.get("manifest"):
            raise ValueError("method proposal manifest is immutable")
        if list(persisted.get("source_output_ids") or []) != list(
            supplied.get("source_output_ids") or []
        ):
            raise ValueError("method proposal source outputs are immutable")
        if dict(persisted.get("package_audit") or {}) != dict(supplied.get("package_audit") or {}):
            raise ValueError("method proposal package audit is immutable")

    def _revision_for_proposal(
        self, project_id: str, method_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        rows = self.repository._execute(
            "SELECT * FROM knowledge_method_revisions WHERE project_id=? AND method_id=? ORDER BY version DESC",
            (project_id, method_id),
        ).fetchall()
        for row in rows:
            decoded = self.repository._decode_growth(
                row, ("manifest_json", "eval_summary_json")
            ) or {}
            if ((decoded.get("manifest") or {}).get("_bsc") or {}).get(
                "proposal_id"
            ) == proposal_id:
                return decoded
        return None

    def _insert_revision(self, revision: MethodRevision) -> None:
        self.repository._execute(
            "INSERT INTO knowledge_method_revisions "
            "(id,method_id,project_id,version,body,manifest_json,eval_summary_json,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                revision.id,
                revision.method_id,
                revision.project_id,
                revision.version,
                revision.body,
                self.repository._json_dumps(revision.manifest),
                self.repository._json_dumps(revision.eval_summary),
                revision.status.value,
                revision.created_at.isoformat(),
            ),
        )

    def _insert_supersession_edge(
        self, project_id: str, previous_revision_id: str, revision_id: str
    ) -> None:
        edge = KnowledgeLineageEdge(
            project_id=project_id,
            from_type="method_revision",
            from_id=previous_revision_id,
            to_type="method_revision",
            to_id=revision_id,
            relation="method_supersedes_method",
        )
        self.repository._execute(
            "INSERT INTO knowledge_graph_edges "
            "(id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                edge.id,
                edge.project_id,
                edge.from_id,
                edge.to_id,
                edge.relation,
                "{}",
                "",
                edge.created_at.isoformat(),
            ),
        )

    def _swap_materialization(
        self, method: dict[str, Any], revision: MethodRevision
    ) -> _PublishedSwap:
        mapping = self.repository.get_vault(revision.project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(
            self.vault_root, revision.project_id, mapping["vault_path"]
        )
        methods_root = (vault.project_root / "methods").resolve()
        if vault.project_root not in methods_root.parents:
            raise ValueError("method path escaped project Vault")
        methods_root.mkdir(parents=True, exist_ok=True)
        target = methods_root / method["slug"]
        if target.exists() and (target.is_symlink() or not target.is_dir()):
            raise FileExistsError("method path collides with an unmanaged file")
        if target.exists():
            for managed_name in ("SKILL.md", "evals.md"):
                candidate = target / managed_name
                if candidate.exists() and (
                    candidate.is_symlink()
                    or "bsc_managed: true" not in candidate.read_text(encoding="utf-8")
                ):
                    raise FileExistsError("refusing to overwrite unmanaged method files")

        staging_parent = self.vault_root / ".bsc-staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        staged = staging_parent / f"method-{revision.project_id}-{method['slug']}-{token}"
        backup = staging_parent / f"method-{revision.project_id}-{method['slug']}-{token}.backup"
        if target.exists():
            shutil.copytree(target, staged)
        else:
            staged.mkdir(parents=True)
        skill_content = self._render_skill(method, revision)
        eval_content = self._render_evals(revision)
        revision_dir = staged / "revisions" / f"{revision.version:04d}-{revision.id}"
        if revision_dir.exists():
            raise FileExistsError("immutable method revision materialization already exists")
        revision_dir.mkdir(parents=True)
        self._write_staged(revision_dir / "SKILL.md", skill_content)
        self._write_staged(revision_dir / "evals.md", eval_content)
        self._write_staged(staged / "SKILL.md", skill_content)
        self._write_staged(staged / "evals.md", eval_content)

        had_target = target.exists()
        if had_target:
            os.replace(target, backup)
        try:
            os.replace(staged, target)
        except Exception:
            if had_target and backup.exists():
                os.replace(backup, target)
            raise
        finally:
            if staged.exists():
                shutil.rmtree(staged)
        return _PublishedSwap(target=target, backup=backup, had_target=had_target)

    @staticmethod
    def _write_staged(path: Path, content: str) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _render_skill(method: dict[str, Any], revision: MethodRevision) -> str:
        frontmatter = {
            "bsc_managed": True,
            "project_id": revision.project_id,
            "method_id": revision.method_id,
            "revision_id": revision.id,
            "version": revision.version,
            "name": method["name"],
            "slug": method["slug"],
            "prompt_only": bool(revision.manifest.get("prompt_only", True)),
            "manifest": revision.manifest,
        }
        header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{header}\n---\n\n{revision.body.rstrip()}\n"

    @staticmethod
    def _render_evals(revision: MethodRevision) -> str:
        cases = revision.manifest.get("eval_cases") or []
        lines = [
            "---",
            "bsc_managed: true",
            f"revision_id: {revision.id}",
            f"version: {revision.version}",
            "---",
            "",
            "# Evaluation contract",
            "",
            f"Evaluation summary: `{json.dumps(revision.eval_summary, ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Cases",
        ]
        if cases:
            lines.extend(
                f"- `{case.get('id', index)}`: {case.get('expected', '')}"
                for index, case in enumerate(cases, 1)
            )
        else:
            lines.append("- No embedded cases")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _rollback_swap(swap: _PublishedSwap) -> None:
        if swap.target.exists():
            shutil.rmtree(swap.target)
        if swap.had_target and swap.backup.exists():
            os.replace(swap.backup, swap.target)

    @staticmethod
    def _finalize_swap(swap: _PublishedSwap) -> None:
        if swap.backup.exists():
            shutil.rmtree(swap.backup)
