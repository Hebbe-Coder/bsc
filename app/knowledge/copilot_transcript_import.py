"""Import a completed Obsidian Copilot reply as a governed review draft.

Copilot's automatic conversation archive is intentionally not a D-layer
delivery. This service provides a separate, explicit transition for an owner
to preserve one completed model response as a BSC-owned review package. The
original conversation remains untouched and the imported output is registered
only, so it cannot become personal-learning evidence without the normal
evidence, evaluation, outcome, and attribution gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.output_registry import OutputRegistry


_ARCHIVE_SUBPATH = Path("copilot") / "copilot-conversations"
_MAX_TRANSCRIPT_BYTES = 1 * 1024 * 1024
_AI_MESSAGE = re.compile(
    r"(?ms)^\*\*(?:ai|assistant)\*\*:\s*(?P<body>.*?)(?=^\*\*(?:user|ai|assistant)\*\*:|\Z)"
)
_TRAILING_TIMESTAMP = re.compile(r"\n?\[Timestamp:[^\]\r\n]*\]\s*\Z", re.IGNORECASE)
_TRUNCATED_RESPONSE = re.compile(r"response\s+was\s+truncated|before\s+any\s+content\s+could\s+be\s+generated", re.IGNORECASE)
_TEMPORARY_SUFFIXES = (".tmp", ".temp", ".swp", ".lock")


class CopilotTranscriptImportError(ValueError):
    """Raised when the explicit transcript-to-review transition is unsafe."""


@dataclass(frozen=True)
class CompletedCopilotResponse:
    relative_path: str
    archived_at: str
    transcript_sha256: str
    response_sha256: str
    title: str
    model: str
    provider: str
    response: str


class CopilotTranscriptImportService:
    """Create an immutable D-layer review draft from one completed chat reply."""

    def __init__(self, repository: GrowthRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise CopilotTranscriptImportError("obsidian_vault_unavailable")

    def import_latest(self, *, project_id: str, actor_id: str) -> dict[str, Any]:
        actor = " ".join(str(actor_id).split())
        if not actor:
            raise CopilotTranscriptImportError("import_actor_required")
        project_root = self._project_root(project_id)
        archive_root = self._trusted_archive_root(project_root)
        response = self._latest_completed_response(project_root, archive_root)
        output, content = self._output_for_response(project_id, response, actor)
        registry = OutputRegistry(self.repository, self.vault_root)
        output_id = registry.deterministic_id(output)
        existing = self.repository.get_output(project_id, output_id)
        registered = registry.register_content(output, content, original_path=response.relative_path)
        return {
            "output": registered,
            "idempotent": existing is not None,
            "transcript": self._transcript_metadata(response),
        }

    def inspect_latest(self, *, project_id: str) -> dict[str, Any]:
        """Return bounded metadata without importing or exposing content."""
        project_root = self._project_root(project_id)
        archive_root = self._trusted_archive_root(project_root)
        response = self._latest_completed_response(project_root, archive_root)
        output, _ = self._output_for_response(project_id, response, "status_probe")
        output_id = OutputRegistry.deterministic_id(output)
        imported = self.repository.get_output(project_id, output_id) is not None
        return {
            "state": "already_imported" if imported else "ready_to_import",
            "output_id": output_id if imported else None,
            "transcript": self._transcript_metadata(response),
        }

    @staticmethod
    def _transcript_metadata(response: CompletedCopilotResponse) -> dict[str, str]:
        return {
            "original_path": response.relative_path,
            "archived_at": response.archived_at,
            "title": response.title,
            "model": response.model,
            "provider": response.provider,
            "transcript_sha256": response.transcript_sha256,
            "response_sha256": response.response_sha256,
        }

    @staticmethod
    def _output_for_response(
        project_id: str,
        response: CompletedCopilotResponse,
        actor: str,
    ) -> tuple[OutputAsset, bytes]:
        content = CopilotTranscriptImportService._review_package(project_id, response)
        content_hash = hashlib.sha256(content).hexdigest()
        output = OutputAsset(
            project_id=project_id,
            kind="personal_execution_plan",
            title=response.title,
            mime_type="text/markdown",
            content_hash=content_hash,
            vault_path=f"outputs/{datetime.now(timezone.utc):%Y}/copilot-import/{Path(response.relative_path).stem}.md",
            idempotency_key=(
                f"copilot_transcript_import|{response.relative_path}|{response.transcript_sha256}"
            ),
            metadata={
                "origin": "copilot_transcript_import",
                "original_path": response.relative_path,
                "obsidian_plugin": "copilot",
                "obsidian_adapter": "transcript_import",
                "import_actor": actor,
                "transcript_sha256": response.transcript_sha256,
                "response_sha256": response.response_sha256,
                "goal": "Review an existing Copilot response before it enters the PBOS delivery loop",
                "audience": "project_owner",
                "channel": "internal",
                "generator": "bsc:copilot_transcript_import",
                "provider": response.provider or "unknown",
                "model": response.model or "unknown",
                "prompt_revision": "copilot-transcript-import-v1",
                "requires_evidence": True,
                "review_gate": "external_evidence_quality_owner_outcome_required",
            },
        )
        return output, content

    def _project_root(self, project_id: str) -> Path:
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise CopilotTranscriptImportError("project_vault_unconfigured")
        try:
            project_root = (self.vault_root / str(mapping["vault_path"])).resolve()
            project_root.relative_to(self.vault_root)
        except (KeyError, OSError, ValueError) as exc:
            raise CopilotTranscriptImportError("project_vault_path_invalid") from exc
        if not project_root.is_dir() or project_root.is_symlink():
            raise CopilotTranscriptImportError("project_vault_unavailable")
        return project_root

    def _trusted_archive_root(self, project_root: Path) -> Path:
        manifest = ObsidianPluginManifest.load(project_root)
        plugin = next((item for item in manifest.plugins if item.plugin_id == "copilot"), None)
        if plugin is None or plugin.adapter != "filesystem_output" or not manifest.is_trusted(plugin):
            raise CopilotTranscriptImportError("copilot_bridge_not_trusted")
        public = manifest.public_status(project_root=project_root, vault_root=self.vault_root)
        status = next((item for item in public.get("plugins", []) if item.get("id") == "copilot"), {})
        runtime = status.get("runtime_configuration") if isinstance(status, dict) else {}
        if not isinstance(runtime, dict) or runtime.get("state") != "configured":
            raise CopilotTranscriptImportError("copilot_archive_route_not_configured")
        archive_root = (project_root / _ARCHIVE_SUBPATH).resolve()
        try:
            archive_root.relative_to(project_root)
        except ValueError as exc:
            raise CopilotTranscriptImportError("copilot_archive_path_invalid") from exc
        if not archive_root.is_dir() or archive_root.is_symlink():
            raise CopilotTranscriptImportError("copilot_archive_unavailable")
        return archive_root

    def _latest_completed_response(self, project_root: Path, archive_root: Path) -> CompletedCopilotResponse:
        candidates: list[Path] = []
        for path in archive_root.rglob("*.md"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                relative = path.relative_to(archive_root)
                if any(part.startswith(".") for part in relative.parts) or path.name.lower().endswith(_TEMPORARY_SUFFIXES):
                    continue
                if path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
                    continue
                candidates.append(path)
            except OSError:
                continue
        for path in sorted(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True):
            parsed = self._parse_completed_response(project_root, path)
            if parsed is not None:
                return parsed
        raise CopilotTranscriptImportError("no_completed_copilot_response")

    @staticmethod
    def _parse_completed_response(project_root: Path, path: Path) -> CompletedCopilotResponse | None:
        try:
            raw = path.read_bytes()
            archived_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            relative_path = path.relative_to(project_root).as_posix()
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        fields = CopilotTranscriptImportService._frontmatter(text)
        responses = [
            _TRAILING_TIMESTAMP.sub("", match.group("body")).strip()
            for match in _AI_MESSAGE.finditer(text)
        ]
        response = next(
            (item for item in reversed(responses) if item and not _TRUNCATED_RESPONSE.search(item)),
            "",
        )
        if not response:
            return None
        model, provider = CopilotTranscriptImportService._model_fields(fields.get("modelkey", ""))
        title = " ".join(fields.get("topic", "").split())[:200] or "Imported Copilot review draft"
        return CompletedCopilotResponse(
            relative_path=relative_path,
            archived_at=archived_at,
            transcript_sha256=hashlib.sha256(raw).hexdigest(),
            response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
            title=title,
            model=model,
            provider=provider,
            response=response,
        )

    @staticmethod
    def _frontmatter(text: str) -> dict[str, str]:
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---", 4)
        if end < 0:
            return {}
        fields: dict[str, str] = {}
        for line in text[4:end].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized = key.strip().lower()
            if normalized in {"modelkey", "topic"}:
                fields[normalized] = value.strip().strip("\"'")
        return fields

    @staticmethod
    def _model_fields(value: str) -> tuple[str, str]:
        model, separator, provider = value.partition("|")
        if not separator:
            return "", ""
        scalar = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
        model = model.strip()
        provider = provider.strip()
        return (model, provider) if scalar.fullmatch(model) and scalar.fullmatch(provider) else ("", "")

    @staticmethod
    def _review_package(project_id: str, response: CompletedCopilotResponse) -> bytes:
        title = json.dumps(response.title, ensure_ascii=False)
        source_path = json.dumps(response.relative_path, ensure_ascii=False)
        return (
            "---\n"
            "bsc_output_contract: v1\n"
            f"project_id: {project_id}\n"
            "output_kind: personal_execution_plan\n"
            f"title: {title}\n"
            'goal: "Review a Copilot-generated PBOS plan before governed acceptance"\n'
            'audience: "project_owner"\n'
            'channel: "internal"\n'
            "source_refs:\n"
            "page_refs:\n"
            "---\n\n"
            "# Imported Copilot review draft\n\n"
            "This BSC-owned review package preserves one completed Obsidian Copilot response. "
            "It is not a native Copilot D-layer export, verified evidence, accepted outcome, Capability, or Strategy Genome.\n\n"
            f"- Original archive: {source_path}\n"
            f"- Transcript SHA-256: `{response.transcript_sha256}`\n"
            f"- Response SHA-256: `{response.response_sha256}`\n"
            f"- Model: `{response.model or 'unknown'}` / provider: `{response.provider or 'unknown'}`\n\n"
            "## Copilot response\n\n"
            f"{response.response}\n\n"
            "## Required review gates\n\n"
            "Attach eligible external evidence, complete quality review, and record an owner-attributed observed outcome before any PBOS learning claim.\n"
        ).encode("utf-8")
