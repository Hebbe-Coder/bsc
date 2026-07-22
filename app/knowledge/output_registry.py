"""Immutable, project-scoped output registration and Vault materialization."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any

import yaml

from app.knowledge.growth_contracts import KnowledgeLineageEdge, OutputAsset, OutputStatus
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.vault import FilesystemWikiVault


_YEAR = re.compile(r"^20\d{2}$")
_REQUIRED_PROVENANCE = (
    "goal",
    "audience",
    "channel",
    "generator",
    "provider",
    "model",
    "prompt_revision",
)


class OutputRegistry:
    """Register one immutable D-layer asset and its managed Vault copy.

    The database and filesystem cannot share one physical transaction. This
    service validates all lineage endpoints before writing, uses atomic file
    replacement, and compensates filesystem writes when database registration
    does not commit.
    """

    def __init__(self, repository: GrowthRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("output Vault root does not exist")

    @staticmethod
    def deterministic_id(output: OutputAsset) -> str:
        identity = f"{output.project_id}|{output.idempotency_key}|{output.content_hash.lower()}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def register_content(
        self,
        output: OutputAsset,
        content: bytes,
        *,
        original_path: str = "",
    ) -> dict[str, Any]:
        if not isinstance(content, bytes):
            raise TypeError("output content must be bytes")
        actual_hash = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual_hash, output.content_hash.lower()):
            raise ValueError("output content hash does not match content hash")

        self._validate_provenance(output)
        self._validate_references(output)
        output_id = self.deterministic_id(output)
        canonical_path = self._canonical_vault_path(output, output_id)
        normalized = output.model_copy(
            update={"id": output_id, "content_hash": actual_hash, "vault_path": canonical_path}
        )

        mapping = self.repository.get_vault(output.project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(
            self.vault_root, output.project_id, mapping["vault_path"]
        )
        target = self._safe_target(vault, normalized.vault_path)
        index = target.parent / "index.md"

        existing = self._existing_registration(normalized)
        if existing:
            self._assert_immutable_retry(existing, normalized)
            self._materialize(
                target,
                content,
                index,
                self._index(normalized, original_path=original_path),
                allow_managed_recovery=True,
            )
            self._ensure_lineage(normalized)
            return existing

        created_target = False
        created_index = False
        try:
            created_target, created_index = self._materialize(
                target,
                content,
                index,
                self._index(normalized, original_path=original_path),
            )
            registered = self.repository.register_output(normalized)
            self._ensure_lineage(normalized)
            return registered
        except Exception:
            # Keep a committed registration inspectable. If no registration
            # exists, remove only files created by this attempt.
            committed = self._existing_registration(normalized)
            if not committed:
                if created_target and target.exists():
                    target.unlink()
                if created_index and index.exists():
                    index.unlink()
                self._remove_empty_parents(target.parent, vault.project_root)
            raise

    def register_file(
        self,
        output: OutputAsset,
        source_path: Path | str,
        *,
        original_path: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path).resolve(strict=True)
        if not source.is_file() or source.is_symlink():
            raise ValueError("output source must be a regular file")
        content = source.read_bytes()
        return self.register_content(
            output,
            content,
            original_path=original_path if original_path is not None else str(source),
        )

    def read_content(
        self,
        project_id: str,
        output_id: str,
        *,
        max_text_bytes: int = 1_000_000,
    ) -> dict[str, Any]:
        """Read a verified managed output without exposing arbitrary Vault files."""
        output = self.repository.get_output(project_id, output_id)
        if not output:
            raise KeyError("output not found in project")
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(
            self.vault_root, project_id, mapping["vault_path"]
        )
        target = self._safe_target(vault, str(output["vault_path"]))
        if not target.is_file() or target.is_symlink():
            raise ValueError("output materialization is missing or is not a regular file")
        content = target.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual_hash, str(output["content_hash"]).lower()):
            raise ValueError("output materialization content hash does not match registration")

        descriptor: dict[str, Any] = {
            "output_id": output_id,
            "mime_type": str(output.get("mime_type") or "application/octet-stream"),
            "content_hash": actual_hash,
            "byte_size": len(content),
            "vault_path": str(output["vault_path"]),
            "content": "",
        }
        if not descriptor["mime_type"].startswith("text/"):
            return {**descriptor, "render_mode": "binary"}
        if len(content) > max(1, max_text_bytes):
            return {**descriptor, "render_mode": "oversized_text"}
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("output text materialization is not valid UTF-8") from exc
        return {**descriptor, "render_mode": "text", "content": text}

    def adopt_external(
        self,
        output: OutputAsset,
        source_path: Path | str,
        *,
        actor_role: str,
    ) -> dict[str, Any]:
        if actor_role not in {"project_admin", "admin", "system"}:
            raise PermissionError("external output adoption requires project administrator permission")
        if str(output.metadata.get("origin") or "") != "external":
            raise ValueError("adopted output provenance must declare origin=external")
        return self.register_file(output, source_path)

    def file_output(
        self,
        project_id: str,
        output_id: str,
        *,
        actor_id: str,
        reason: str,
        expected_status: OutputStatus | str | None = OutputStatus.ACCEPTED,
    ) -> dict[str, Any]:
        """Verify the immutable Vault asset, then persist the filed transition."""
        output = self.repository.get_output(project_id, output_id)
        if not output:
            raise KeyError("output not found in project")
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(self.vault_root, project_id, mapping["vault_path"])
        target = self._safe_target(vault, str(output["vault_path"]))
        if not target.is_file() or target.is_symlink():
            raise ValueError("output materialization is missing or is not a regular file")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), str(output["content_hash"]).lower()):
            raise ValueError("output materialization content hash does not match registration")
        return self.repository.file_output(
            project_id,
            output_id,
            actor_id=actor_id,
            reason=reason,
            expected_status=expected_status,
        )

    def file(
        self,
        project_id: str,
        output_id: str,
        *,
        actor_id: str,
        reason: str,
        expected_status: OutputStatus | str | None = OutputStatus.ACCEPTED,
    ) -> dict[str, Any]:
        """Backward-compatible alias for the public ``file_output`` contract."""
        return self.file_output(
            project_id,
            output_id,
            actor_id=actor_id,
            reason=reason,
            expected_status=expected_status,
        )

    def _existing_registration(self, output: OutputAsset) -> dict[str, Any] | None:
        row = self.repository._execute(
            "SELECT * FROM knowledge_outputs WHERE project_id=? AND idempotency_key=?",
            (output.project_id, output.idempotency_key),
        ).fetchone()
        return self.repository._decode_growth(
            row, ("source_refs_json", "page_refs_json", "quality_json", "metadata_json")
        )

    @staticmethod
    def _assert_immutable_retry(existing: dict[str, Any], output: OutputAsset) -> None:
        expected = {
            "id": output.id,
            "content_hash": output.content_hash,
            "vault_path": output.vault_path,
            "run_id": output.run_id,
            "method_revision_id": output.method_revision_id,
            "context_revision": output.context_revision,
        }
        conflicts = [key for key, value in expected.items() if str(existing.get(key) or "") != str(value or "")]
        if conflicts:
            raise ValueError(f"output retry conflicts with immutable registration fields: {', '.join(conflicts)}")
        for key in _REQUIRED_PROVENANCE:
            if str((existing.get("metadata") or {}).get(key) or "") != str(output.metadata.get(key) or ""):
                raise ValueError(f"output retry conflicts with immutable provenance: {key}")

    @staticmethod
    def _validate_provenance(output: OutputAsset) -> None:
        missing = [key for key in _REQUIRED_PROVENANCE if not str(output.metadata.get(key) or "").strip()]
        if missing:
            raise ValueError(f"output provenance is missing required fields: {', '.join(missing)}")

    def _validate_references(self, output: OutputAsset) -> None:
        for source_id in output.source_refs:
            if not self.repository.get_source(output.project_id, source_id):
                raise ValueError(f"source reference is missing or belongs to another project: {source_id}")
        for page_id in output.page_refs:
            if not self.repository.get_page(output.project_id, page_id):
                raise ValueError(f"page reference is missing or belongs to another project: {page_id}")
        if output.run_id and not self.repository.get_run(output.project_id, output.run_id):
            raise ValueError("run reference is missing or belongs to another project")
        if output.method_revision_id and not self.repository.get_method_revision(
            output.project_id, output.method_revision_id
        ):
            raise ValueError("method revision is missing or belongs to another project")

    @staticmethod
    def _canonical_vault_path(output: OutputAsset, output_id: str) -> str:
        requested = PurePosixPath(output.vault_path)
        if not requested.parts or requested.parts[0] != "outputs":
            raise ValueError("output Vault path must be below outputs/")
        year = requested.parts[1] if len(requested.parts) > 1 and _YEAR.fullmatch(requested.parts[1]) else ""
        if not year:
            year = output.created_at.astimezone(timezone.utc).strftime("%Y")
        filename = requested.name
        if filename in {"", ".", "..", "index.md"}:
            raise ValueError("output filename is not safe")
        return PurePosixPath("outputs", year, output_id, filename).as_posix()

    @staticmethod
    def _safe_target(vault: FilesystemWikiVault, relative_path: str) -> Path:
        target = (vault.project_root / relative_path).resolve()
        if vault.project_root not in target.parents:
            raise ValueError("output path escaped project Vault")
        current = vault.project_root
        for part in PurePosixPath(relative_path).parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ValueError("output path crosses a symlink")
        return target

    def _ensure_lineage(self, output: OutputAsset) -> None:
        for source_id in output.source_refs:
            self.repository.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id=output.project_id,
                    from_type="source",
                    from_id=source_id,
                    to_type="output",
                    to_id=output.id,
                    relation="output_used_source",
                )
            )
        for page_id in output.page_refs:
            self.repository.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id=output.project_id,
                    from_type="page",
                    from_id=page_id,
                    to_type="output",
                    to_id=output.id,
                    relation="output_used_page",
                )
            )
        if output.run_id:
            self.repository.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id=output.project_id,
                    from_type="run",
                    from_id=output.run_id,
                    to_type="output",
                    to_id=output.id,
                    relation="output_produced_by_run",
                )
            )
        if output.method_revision_id:
            self.repository.add_lineage_edge(
                KnowledgeLineageEdge(
                    project_id=output.project_id,
                    from_type="method_revision",
                    from_id=output.method_revision_id,
                    to_type="output",
                    to_id=output.id,
                    relation="output_used_method_revision",
                )
            )

    @classmethod
    def _materialize(
        cls,
        target: Path,
        content: bytes,
        index: Path,
        index_content: str,
        *,
        allow_managed_recovery: bool = False,
    ) -> tuple[bool, bool]:
        target.parent.mkdir(parents=True, exist_ok=True)
        created_target = not target.exists()
        created_index = not index.exists()
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise FileExistsError("output materialization collision")
            existing_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            expected_hash = hashlib.sha256(content).hexdigest()
            if not hmac.compare_digest(existing_hash, expected_hash):
                raise FileExistsError("output materialization collision")
        if index.exists():
            if index.is_symlink() or "bsc_managed: true" not in index.read_text(encoding="utf-8"):
                raise FileExistsError("output metadata collision with an unmanaged file")
        elif target.exists() and not created_target and not allow_managed_recovery:
            raise FileExistsError("output materialization collision without managed metadata")

        if created_target:
            cls._atomic_write_bytes(target, content)
        if created_index:
            cls._atomic_write_bytes(index, index_content.encode("utf-8"))
        return created_target, created_index

    @staticmethod
    def _atomic_write_bytes(target: Path, content: bytes) -> None:
        temporary = target.with_name(f".{target.name}.bsc-{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _remove_empty_parents(path: Path, stop: Path) -> None:
        while path != stop and stop in path.parents:
            try:
                path.rmdir()
            except OSError:
                return
            path = path.parent

    @staticmethod
    def _index(output: OutputAsset, *, original_path: str) -> str:
        metadata = {
            "bsc_managed": True,
            "project_id": output.project_id,
            "output_id": output.id,
            "kind": output.kind,
            "content_hash": output.content_hash,
            "mime_type": output.mime_type,
            "run_id": output.run_id,
            "method_revision_id": output.method_revision_id,
            "context_revision": output.context_revision,
            "source_refs": output.source_refs,
            "page_refs": output.page_refs,
            "original_path": original_path,
            "provenance": {key: output.metadata.get(key, "") for key in _REQUIRED_PROVENANCE},
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
        refs = "\n".join(f"- `{ref}`" for ref in [*output.source_refs, *output.page_refs]) or "- None"
        return f"---\n{frontmatter}\n---\n\n# {output.title or output.kind}\n\n## Evidence and context\n{refs}\n"
