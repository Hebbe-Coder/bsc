"""Adopt explicitly declared Obsidian plugin outputs into the governed D-layer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import mimetypes
from pathlib import Path
import re
from typing import Any

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.output_registry import OutputRegistry


_MAX_OUTPUT_BYTES = 25 * 1024 * 1024
_MAX_OUTPUT_CONTRACT_BYTES = 16 * 1024
_TEMPORARY_SUFFIXES = (".tmp", ".temp", ".swp", ".lock")
_OUTPUT_CONTRACT_TEXT_FIELDS = frozenset({"title", "goal", "audience", "channel"})
_OUTPUT_CONTRACT_REFERENCE_FIELDS = frozenset({"source_refs", "page_refs"})
_OUTPUT_CONTRACT_KIND = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_OUTPUT_CONTRACT_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ObsidianOutputSyncService:
    """Copy declared external plugin results into immutable, pending D-layer assets.

    The original Obsidian file remains untouched. Registered copies are not
    eligible for future context until the existing output evaluation and
    feedback gates accept them.
    """

    def __init__(self, repository: GrowthRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")

    def sync(self, *, project_id: str, run_id: str = "") -> dict[str, int]:
        report = {"scanned": 0, "registered": 0, "duplicates": 0, "rejected": 0, "skipped": 0, "blocked": 0}
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        project_root = (self.vault_root / str(mapping["vault_path"])).resolve()
        if self.vault_root not in project_root.parents and project_root != self.vault_root:
            raise ValueError("project Vault mapping escaped the configured root")
        manifest = ObsidianPluginManifest.load(project_root)
        if not project_root.is_dir():
            return report
        registry = OutputRegistry(self.repository, self.vault_root)
        for plugin in manifest.plugins:
            if plugin.adapter != "filesystem_output":
                continue
            if not manifest.is_trusted(plugin):
                report["blocked"] += len(plugin.input_paths)
                continue
            for configured_path in plugin.input_paths:
                export_root = (project_root / configured_path).resolve()
                if project_root not in export_root.parents and export_root != project_root:
                    report["rejected"] += 1
                    continue
                if not export_root.is_dir() or export_root.is_symlink():
                    continue
                for path in export_root.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.is_symlink() or self._skip(path, export_root):
                        report["skipped"] += 1
                        continue
                    try:
                        relative = path.relative_to(project_root).as_posix()
                        if manifest.output_plugin_for(relative) != plugin:
                            report["skipped"] += 1
                            continue
                        if path.stat().st_size > _MAX_OUTPUT_BYTES:
                            report["rejected"] += 1
                            continue
                        report["scanned"] += 1
                        content = path.read_bytes()
                        output = self._asset(project_id, run_id, plugin.plugin_id, plugin.name, relative, content)
                        output_id = registry.deterministic_id(output)
                        existing = self.repository.get_output(project_id, output_id)
                        existed = existing is not None
                        if existing:
                            # The original external file has one immutable
                            # registration. Later source-sync runs may observe
                            # it again, but must not claim they produced it or
                            # turn a harmless retry into a conflict.
                            output = output.model_copy(update={"run_id": str(existing.get("run_id") or "")})
                        registry.register_content(output, content, original_path=relative)
                        report["duplicates" if existed else "registered"] += 1
                    except (OSError, ValueError):
                        report["rejected"] += 1
        return report

    @staticmethod
    def _skip(path: Path, export_root: Path) -> bool:
        relative = path.relative_to(export_root)
        if any(part.startswith(".") for part in relative.parts):
            return True
        return path.name.lower().endswith(_TEMPORARY_SUFFIXES)

    @staticmethod
    def _asset(
        project_id: str,
        run_id: str,
        plugin_id: str,
        plugin_name: str,
        original_path: str,
        content: bytes,
    ) -> OutputAsset:
        content_hash = hashlib.sha256(content).hexdigest()
        filename = Path(original_path).name
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        contract = ObsidianOutputSyncService._output_contract(content, project_id)
        provenance = {
            "goal": str(contract.get("goal") or "not_provided_by_external_plugin"),
            "audience": str(contract.get("audience") or "not_provided_by_external_plugin"),
            "channel": str(contract.get("channel") or "obsidian_plugin"),
            "generator": f"obsidian_plugin:{plugin_id}",
            "provider": "external_plugin",
            "model": "unknown",
            "prompt_revision": "vault_output_contract_v1" if contract else "unknown",
        }
        provenance_gaps = [
            key
            for key in ("goal", "audience", "provider", "model", "prompt_revision")
            if provenance[key] in {"", "unknown", "not_provided_by_external_plugin"}
        ]
        now = datetime.now(timezone.utc)
        return OutputAsset(
            project_id=project_id,
            kind=str(contract.get("output_kind") or "external_plugin_output"),
            title=str(contract.get("title") or filename),
            mime_type=mime_type,
            content_hash=content_hash,
            vault_path=f"outputs/{now:%Y}/pending/{filename}",
            run_id=run_id,
            source_refs=list(contract.get("source_refs") or []),
            page_refs=list(contract.get("page_refs") or []),
            idempotency_key=f"obsidian_plugin_output|{plugin_id}|{original_path}|{content_hash}",
            metadata={
                "origin": "external",
                "original_path": original_path,
                "obsidian_plugin": plugin_id,
                "plugin_name": plugin_name,
                "obsidian_adapter": "filesystem_output",
                "bsc_output_contract": str(contract.get("bsc_output_contract") or ""),
                **provenance,
                "provenance_gaps": provenance_gaps,
            },
        )

    @staticmethod
    def _output_contract(content: bytes, project_id: str) -> dict[str, Any]:
        """Read the bounded BSC output contract without parsing arbitrary YAML.

        The contract is optional for third-party outputs. When supplied, the
        project identifier and every referenced asset remain subject to the
        existing OutputRegistry project-scope checks.
        """
        if len(content) > _MAX_OUTPUT_CONTRACT_BYTES:
            return {}
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return {}
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---", 4)
        if end < 0:
            return {}
        fields: dict[str, str] = {}
        for line in text[4:end].splitlines():
            if ":" not in line:
                continue
            raw_key, raw_value = line.split(":", 1)
            key = raw_key.strip().lower()
            if key not in {"bsc_output_contract", "project_id", "output_kind", *_OUTPUT_CONTRACT_TEXT_FIELDS, *_OUTPUT_CONTRACT_REFERENCE_FIELDS}:
                continue
            value = raw_value.strip().strip("\"'")
            if len(value) > 512:
                raise ValueError("output contract field exceeds 512 characters")
            fields[key] = value
        version = fields.get("bsc_output_contract", "")
        if not version:
            return {}
        if version != "v1":
            raise ValueError("output contract revision is unsupported")
        declared_project = fields.get("project_id", "")
        if declared_project and declared_project != project_id:
            raise ValueError("output contract project does not match its Vault route")
        output_kind = fields.get("output_kind", "")
        if output_kind and not _OUTPUT_CONTRACT_KIND.fullmatch(output_kind):
            raise ValueError("output contract kind is invalid")
        references = {
            key: ObsidianOutputSyncService._contract_references(fields.get(key, ""))
            for key in _OUTPUT_CONTRACT_REFERENCE_FIELDS
        }
        return {
            "bsc_output_contract": version,
            "output_kind": output_kind,
            **{key: fields.get(key, "") for key in _OUTPUT_CONTRACT_TEXT_FIELDS},
            **references,
        }

    @staticmethod
    def _contract_references(value: str) -> list[str]:
        raw = value.strip().strip("[]")
        if not raw:
            return []
        references = [part.strip().strip("\"'") for part in raw.split(",") if part.strip()]
        if len(references) > 64 or any(not _OUTPUT_CONTRACT_REFERENCE.fullmatch(item) for item in references):
            raise ValueError("output contract references are invalid")
        return list(dict.fromkeys(references))
