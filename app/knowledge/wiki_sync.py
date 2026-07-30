"""One-way, non-destructive import of user-authored Obsidian Markdown into evidence records."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
import hashlib
import mimetypes
import re
from datetime import datetime, timezone

from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.wiki_contracts import MediaAsset, SourceStatus
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.obsidian_metadata import is_managed_index_path
from app.knowledge.obsidian_source_projection import is_managed_evidence_path


class ObsidianSyncService:
    """Import only user Markdown; never treat generated project output as new evidence."""

    def __init__(self, repository: WikiRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")
        self.capture_service = SourceCaptureService(repository)

    def sync(self, *, project_id: str) -> dict[str, int]:
        report = {"scanned": 0, "created": 0, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0, "blocked": 0}
        seen_paths: set[str] = set()
        mappings = {
            str(mapping["project_id"]): PurePosixPath(str(mapping["vault_path"]).replace("\\", "/")).parts
            for mapping in self.repository.list_vaults()
            if mapping.get("vault_path")
        }
        project_root = mappings.get(project_id, ())
        project_directory = (self.vault_root.joinpath(*project_root)).resolve() if project_root else None
        manifest = ObsidianPluginManifest.load(project_directory)
        managed_roots = {("projects",)} | set(mappings.values())
        for path in self.vault_root.rglob("*"):
            if path.is_symlink():
                report["skipped"] += 1
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(self.vault_root)
            if self._excluded(relative, project_root, managed_roots):
                continue
            project_relative = "/".join(relative.parts[len(project_root):]) if project_root else ""
            declared_plugin = manifest.declared_plugin_for(project_relative) if project_relative else None
            plugin = manifest.plugin_for(project_relative) if project_relative else None
            if plugin and self._is_bsc_bridge_healthcheck(plugin.plugin_id, relative.parts[len(project_root):]):
                # The local Clipper probe proves destination alignment only.
                # It is never evidence and must not make a bridge look used.
                continue
            seen_paths.add(relative.as_posix())
            if declared_plugin and not plugin:
                # A declared path remains visible in workspace status, but is
                # not read until its exact adapter/root configuration is trusted.
                report["blocked"] += 1
                continue
            workspace_role = ObsidianPluginManifest.workspace_role_for(
                tuple(relative.parts[len(project_root):]) if project_root else ()
            )
            extension = path.suffix.lower()
            if extension not in {".md", ".txt", ".json", ".canvas"}:
                result = self.capture_service.capture(
                    CapturedSourceInput(
                        project_id=project_id,
                        source_type="obsidian_unsupported",
                        origin=relative.as_posix(),
                        vault_path=relative.as_posix(),
                        raw_content=f"Unsupported format retained as provenance only: {relative.as_posix()}",
                        content_hash=self._file_hash(path),
                        trust_level="untrusted",
                        metadata={
                            "sync": "obsidian",
                            **self._plugin_metadata(plugin),
                            **self._workspace_metadata(workspace_role),
                            "modified_at": path.stat().st_mtime_ns,
                            "extension": extension,
                            "byte_size": path.stat().st_size,
                            "extraction_status": "unsupported",
                        },
                    )
                )
                report["rejected" if result.created else "duplicates"] += 1
                self._reconcile_plugin_provenance(result.source, plugin, workspace_role)
                self._mark_present(result.source)
                self._register_media_asset(result.source, path, relative)
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                result = self.capture_service.capture(
                    CapturedSourceInput(
                        project_id=project_id,
                        source_type="obsidian_file",
                        origin=relative.as_posix(),
                        vault_path=relative.as_posix(),
                        raw_content=f"UTF-8 extraction failed; immutable file fingerprint retained: {relative.as_posix()}",
                        content_hash=self._file_hash(path),
                        metadata={
                            "sync": "obsidian",
                            **self._plugin_metadata(plugin),
                            **self._workspace_metadata(workspace_role),
                            "modified_at": path.stat().st_mtime_ns,
                            "extension": extension,
                            "byte_size": path.stat().st_size,
                            "extraction_status": "encoding_error",
                        },
                    )
                )
                report["rejected" if result.created else "duplicates"] += 1
                self._reconcile_plugin_provenance(result.source, plugin, workspace_role)
                self._mark_present(result.source)
                self._register_media_asset(result.source, path, relative)
                continue
            if not content:
                report["skipped"] += 1
                continue
            plugin_provenance = self._plugin_provenance(plugin, content)
            report["scanned"] += 1
            result = self.capture_service.capture(
                CapturedSourceInput(
                    project_id=project_id,
                    source_type=self._source_type(plugin, workspace_role, extension),
                    origin=relative.as_posix(),
                    vault_path=relative.as_posix(),
                    raw_content=content,
                    trust_level="untrusted",
                    metadata={
                        "sync": "obsidian",
                        **self._plugin_metadata(plugin),
                        **plugin_provenance,
                        **self._workspace_metadata(workspace_role),
                        "modified_at": path.stat().st_mtime_ns,
                        "extension": extension,
                        "extraction_status": "complete",
                    },
                )
            )
            report["created" if result.created else "duplicates"] += 1
            self._reconcile_plugin_provenance(result.source, plugin, workspace_role, plugin_provenance)
            self._mark_present(result.source)
            self._register_media_asset(result.source, path, relative)
        for source in self.repository.list_sources(project_id):
            metadata = source.get("metadata") or {}
            origin = str(source.get("origin") or "")
            if metadata.get("sync") != "obsidian" or not origin:
                continue
            if project_root and not self._is_within_project_root(origin, project_root):
                if self._quarantine_out_of_scope_source(source, project_root):
                    report["rejected"] += 1
                continue
            if origin in seen_paths or metadata.get("source_present") is False:
                continue
            self.repository.update_source_metadata(
                project_id,
                source["id"],
                {
                    **metadata,
                    "source_present": False,
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            report["deleted"] += 1
        return report

    def _mark_present(self, source: dict) -> None:
        metadata = source.get("metadata") or {}
        if metadata.get("source_present") is not False:
            return
        restored = {**metadata, "source_present": True}
        restored.pop("deleted_at", None)
        self.repository.update_source_metadata(source["project_id"], source["id"], restored)

    def _quarantine_out_of_scope_source(self, source: dict, project_root: tuple[str, ...]) -> bool:
        """Retain pre-boundary records for audit without treating them as evidence.

        Earlier releases scanned the entire Vault after a project mapping was
        configured. A path outside the mapped project can be a plugin cache or
        transient conversation, so it must not remain usable just because an
        older sync captured it. The source body and audit record are retained;
        only its lifecycle eligibility and active-presence signal are revoked.
        """
        metadata = dict(source.get("metadata") or {})
        exclusion = metadata.get("scope_exclusion") if isinstance(metadata.get("scope_exclusion"), dict) else {}
        project_path = "/".join(project_root)
        already_quarantined = (
            source.get("status") == SourceStatus.REJECTED.value
            and metadata.get("source_present") is False
            and exclusion.get("reason") == "outside_mapped_project_root"
            and exclusion.get("project_root") == project_path
        )
        if already_quarantined:
            return False
        updated_metadata = {
            **metadata,
            "source_present": False,
            "scope_exclusion": {
                "reason": "outside_mapped_project_root",
                "project_root": project_path,
                "excluded_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        self.repository.update_source_metadata(str(source["project_id"]), str(source["id"]), updated_metadata)
        if source.get("status") != SourceStatus.REJECTED.value:
            self.repository.update_source_status(str(source["project_id"]), str(source["id"]), SourceStatus.REJECTED)
            self.repository.mark_source_citations_stale(str(source["project_id"]), str(source["id"]))
        return True

    def _register_media_asset(self, source: dict, path: Path, relative: Path) -> None:
        """Register an immutable Vault file descriptor without copying its bytes."""
        try:
            self.repository.register_media_asset(
                MediaAsset(
                    project_id=str(source["project_id"]),
                    source_id=str(source["id"]),
                    mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    byte_hash=self._file_hash(path),
                    byte_size=path.stat().st_size,
                    storage_ref=relative.as_posix(),
                    metadata={"sync": "obsidian", "extension": path.suffix.lower()},
                )
            )
        except OSError:
            # The source capture remains durable even when a user concurrently
            # moves a file. A later sync can register the descriptor safely.
            return

    def _reconcile_plugin_provenance(
        self,
        source: dict,
        plugin,
        workspace_role: str,
        plugin_provenance: dict | None = None,
    ) -> None:
        """Attach a trusted bridge to a duplicate without changing its evidence body.

        Older captures can predate a bridge declaration. When their immutable
        content hash matches a later trusted export, recording this narrow
        provenance makes the existing evidence visible through the bridge
        rather than recapturing or rewriting it.
        """
        if plugin is None:
            return
        metadata = source.get("metadata") or {}
        expected = {
            "obsidian_plugin": plugin.plugin_id,
            "plugin_name": plugin.name,
            "obsidian_adapter": plugin.adapter,
            **self._workspace_metadata(workspace_role),
            **(plugin_provenance or {}),
        }
        if all(metadata.get(key) == value for key, value in expected.items()):
            return
        self.repository.update_source_metadata(
            source["project_id"],
            source["id"],
            {**metadata, "sync": "obsidian", **expected},
        )

    @staticmethod
    def _plugin_metadata(plugin) -> dict:
        if plugin is None:
            return {}
        return {
            "obsidian_plugin": plugin.plugin_id,
            "plugin_name": plugin.name,
            "obsidian_adapter": plugin.adapter,
        }

    @staticmethod
    def _plugin_provenance(plugin, content: str) -> dict:
        """Map bounded Zotero frontmatter into source provenance metadata.

        Only bibliographic identifiers from notes exported through the trusted
        bridge are retained. The note body stays in immutable source storage
        and is never exposed by plugin route status APIs.
        """
        if plugin is None or plugin.plugin_id != "obsidian-zotero-desktop-connector":
            return {}
        frontmatter = ObsidianSyncService._frontmatter(content)
        fields = {
            "zotero_citation_key": ("citekey", "citationkey", "cite_key"),
            "zotero_doi": ("doi",),
            "zotero_url": ("url", "sourceurl"),
            "zotero_source_date": ("date", "issued"),
            "zotero_item_key": ("itemkey", "item_key", "zotero_item_key"),
        }
        return {
            field: value
            for field, aliases in fields.items()
            if (value := next((frontmatter[name] for name in aliases if frontmatter.get(name)), ""))
        }

    @staticmethod
    def _frontmatter(content: str) -> dict[str, str]:
        """Read scalar frontmatter without accepting arbitrary YAML features."""
        prefix = content[:16_384]
        if not prefix.startswith("---\n"):
            return {}
        end = prefix.find("\n---", 4)
        if end < 0:
            return {}
        values: dict[str, str] = {}
        for line in prefix[4:end].splitlines():
            match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9_-]{0,63})\s*:\s*(.*?)\s*", line)
            if not match:
                continue
            key = match.group(1).lower().replace("-", "_")
            value = match.group(2).strip().strip("\"'")
            if value and len(value) <= 512:
                values[key] = value
        return values

    @staticmethod
    def _workspace_metadata(workspace_role: str) -> dict:
        return {"obsidian_workspace_role": workspace_role} if workspace_role else {}

    @staticmethod
    def _source_type(plugin, workspace_role: str, extension: str) -> str:
        if plugin is not None:
            return f"obsidian_plugin:{plugin.plugin_id}"
        if workspace_role:
            return f"obsidian_{workspace_role}"
        return "obsidian_markdown" if extension == ".md" else "obsidian_file"

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _excluded(
        relative: Path,
        project_root: tuple[str, ...] = (),
        managed_roots: set[tuple[str, ...]] | None = None,
    ) -> bool:
        parts = relative.parts
        if any(part.startswith(".") for part in parts):
            return True
        if parts and parts[0].lower() in {"distillations", "methods", "outputs", "reviews"}:
            return True
        name = relative.name.lower()
        if name.startswith("~") or name.endswith((".tmp", ".temp", ".swp", ".lock")):
            return True
        if project_root and parts[:len(project_root)] == project_root:
            project_relative = parts[len(project_root):]
            if is_managed_index_path(project_relative):
                return True
            if is_managed_evidence_path(project_relative):
                return True
            return not ObsidianPluginManifest.is_syncable_knowledge_path(project_relative)
        if project_root:
            return True
        return any(parts[:len(root)] == root for root in managed_roots or {("projects",)})

    @staticmethod
    def _is_within_project_root(origin: str, project_root: tuple[str, ...]) -> bool:
        parts = PurePosixPath(origin.replace("\\", "/").strip("/")).parts
        return tuple(parts[:len(project_root)]) == project_root

    @staticmethod
    def _is_bsc_bridge_healthcheck(plugin_id: str, project_relative: tuple[str, ...]) -> bool:
        return (
            plugin_id == "obsidian-clipper"
            and len(project_relative) >= 3
            and project_relative[-1].lower() == "bsc.local.md"
        )
