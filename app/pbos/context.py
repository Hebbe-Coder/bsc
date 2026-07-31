"""Bounded Obsidian context for PBOS planning.

PBOS may use working context and governed knowledge, but never treats raw
captures as personal experience or sends the full Vault to a plan compiler.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Iterable

from app.knowledge.context_pack import WikiContextProvider
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.wiki_repository import WikiRepository


class PBOSVaultContextBuilder:
    """Return a compact, reviewable context pack from the project memory layer."""

    ALLOWED_ROOTS = (
        "03_Projects/active",
        "02_Assets/curated",
        "methods",
        "04_Outputs",
        "outputs",
        "distillations",
    )
    EXCLUDED_PARTS = {"revisions", "pbos", ".obsidian", ".git"}
    MAX_DOCUMENTS = 8
    MAX_FILE_BYTES = 24 * 1024
    MAX_EXCERPT_CHARS = 1_200
    TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv"}
    NEXT_CONTEXT_FILENAMES = frozenset({
        "03-下周上下文包.md",
        "03-next-context.md",
        "next_context.md",
    })

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()

    def build(self) -> dict[str, Any]:
        if not self.project_root.is_dir():
            return {"availability": "vault_unavailable", "documents": [], "refs": []}
        documents: list[dict[str, Any]] = []
        latest_context = self._latest_weekly_context()
        if latest_context is not None:
            document = self._document(latest_context)
            if document is not None:
                documents.append(document)
        for root_name in self.ALLOWED_ROOTS:
            root = (self.project_root / root_name).resolve()
            if not root.is_dir() or not self._within_project(root):
                continue
            for candidate in sorted(root.rglob("*")):
                if len(documents) >= self.MAX_DOCUMENTS:
                    break
                if latest_context is not None and candidate == latest_context:
                    continue
                # A weekly next-context package is explicitly a handoff into
                # the next plan. Older packages are historical artifacts, not
                # competing instructions for the current decision.
                if candidate.name in self.NEXT_CONTEXT_FILENAMES:
                    continue
                if not self._eligible(candidate):
                    continue
                document = self._document(candidate)
                if document is not None:
                    documents.append(document)
            if len(documents) >= self.MAX_DOCUMENTS:
                break
        return {
            "availability": "available" if documents else "no_governed_context",
            "documents": documents,
            "refs": [item["ref"] for item in documents],
        }

    def _latest_weekly_context(self) -> Path | None:
        root = (self.project_root / "distillations").resolve()
        if not root.is_dir() or not self._within_project(root):
            return None
        candidates = [
            candidate
            for candidate in root.rglob("*")
            if candidate.name in self.NEXT_CONTEXT_FILENAMES and self._eligible(candidate)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (
                candidate.parent.name,
                candidate.stat().st_mtime_ns,
                candidate.as_posix(),
            ),
        )

    def _eligible(self, candidate: Path) -> bool:
        if not candidate.is_file() or candidate.is_symlink() or candidate.suffix.lower() not in self.TEXT_SUFFIXES:
            return False
        if candidate.name.lower().endswith(".excalidraw.md"):
            return False
        try:
            relative = candidate.resolve().relative_to(self.project_root)
        except ValueError:
            return False
        return not any(part in self.EXCLUDED_PARTS for part in relative.parts)

    def _document(self, candidate: Path) -> dict[str, Any] | None:
        try:
            payload = candidate.read_bytes()[: self.MAX_FILE_BYTES]
            text = payload.decode("utf-8")
            relative = candidate.resolve().relative_to(self.project_root).as_posix()
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        excerpt = self._excerpt(text)
        if not excerpt:
            return None
        return {
            "ref": f"vault:{relative}",
            "path": relative,
            "title": self._title(text, candidate.stem),
            "excerpt": excerpt,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _within_project(self, path: Path) -> bool:
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    def _excerpt(self, text: str) -> str:
        source_lines = text.splitlines()
        first_content = next((index for index, line in enumerate(source_lines) if line.strip()), None)
        if first_content is not None and source_lines[first_content].strip() == "---":
            closing = next(
                (index for index in range(first_content + 1, len(source_lines)) if source_lines[index].strip() == "---"),
                None,
            )
            if closing is not None:
                source_lines = source_lines[closing + 1:]
        lines = [line.strip() for line in source_lines if line.strip() and not line.strip().startswith("---")]
        return "\n".join(lines)[: self.MAX_EXCERPT_CHARS]

    @staticmethod
    def _title(text: str, fallback: str) -> str:
        for line in text.splitlines():
            value = line.strip()
            if value.startswith("# "):
                return value[2:].strip()[:200] or fallback
        return fallback[:200]


class PBOSGovernedContextProvider:
    """Combine bounded working notes with retrieval-selected published Wiki pages.

    The filesystem is useful for the user's current project context, but it is
    not an authority for B-layer knowledge. Published pages and their evidence
    lineage are therefore selected from BSC's project-scoped repository first.
    """

    def __init__(
        self,
        project_root: Path | str,
        *,
        project_id: str,
        vault_root: Path | str,
        repository: WikiRepository | None = None,
        wiki_context_provider: WikiContextProvider | None = None,
        repository_factory: Callable[[], WikiRepository] = WikiRepository,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_id = project_id
        self.vault_root = Path(vault_root).resolve()
        self.repository = repository
        self.wiki_context_provider = wiki_context_provider
        self.repository_factory = repository_factory
        self.working_context = PBOSVaultContextBuilder(self.project_root)

    def build(self, *, task_constraints: Iterable[str] = ()) -> dict[str, Any]:
        working = self.working_context.build()
        repository = self.repository or self.repository_factory()
        owns_repository = self.repository is None
        try:
            provider = self.wiki_context_provider or WikiContextProvider(
                repository, vault_root=self.vault_root
            )
            pack = provider.build_context(
                project_id=self.project_id,
                task_constraints=task_constraints,
            )
            governed = self._published_documents(repository, pack)
            operational_state = self._operational_state(repository)
        finally:
            if owns_repository:
                repository.close()
        documents = [*governed, *working["documents"]][: PBOSVaultContextBuilder.MAX_DOCUMENTS]
        refs = list(dict.fromkeys(
            [
                str(reference)
                for document in documents
                for reference in [
                    document.get("ref"),
                    *(document.get("supporting_refs") or []),
                ]
                if str(reference)
            ]
        ))
        return {
            "availability": "available" if documents else (
                "no_governed_context" if pack is not None else working["availability"]
            ),
            "documents": documents,
            "refs": refs,
            "governed_wiki": {
                "available": pack is not None,
                "revision": pack.revision if pack is not None else "",
                "page_ids": list(pack.page_ids) if pack is not None else [],
                "source_ids": list(pack.source_ids) if pack is not None else [],
                "retrieval_refs": list(pack.retrieval_refs) if pack is not None else [],
            },
            "operational_state": operational_state,
        }

    def _operational_state(self, repository: WikiRepository) -> dict[str, Any]:
        """Report bounded operational facts without loading evidence bodies.

        A planner needs to know whether the evidence mirror and the weekly
        handoff already exist. Treating that state as implicit lets a model
        repeatedly recommend setup work that has already finished. This
        projection is intentionally metadata-only: source content, titles,
        origins, and user notes do not leave their authorities here.
        """
        sources = repository.list_sources(self.project_id)
        lifecycle_counts: dict[str, int] = {}
        recorded_mirrors = 0
        for source in sources:
            status = str(source.get("status") or "unknown")[:64]
            lifecycle_counts[status] = lifecycle_counts.get(status, 0) + 1
            metadata = source.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("obsidian_source_mirror"), dict):
                recorded_mirrors += 1

        mirror_root = self.project_root / "01_Sources" / "bsc-evidence"
        mirror_files, mirror_truncated = self._managed_file_count(mirror_root)
        latest_handoff = self.working_context._latest_weekly_context()
        handoff_path = ""
        if latest_handoff is not None:
            try:
                handoff_path = latest_handoff.resolve().relative_to(self.project_root).as_posix()
            except ValueError:
                handoff_path = ""
        pages = repository.list_pages(self.project_id)
        plugin_bridges = self._plugin_bridges(sources)
        mirror_available = bool(mirror_files and recorded_mirrors)
        return {
            "source_lifecycle_counts": dict(sorted(lifecycle_counts.items())),
            "managed_source_mirror": {
                "state": "available" if mirror_available else "awaiting_projection",
                "path": "01_Sources/bsc-evidence",
                "file_count": mirror_files,
                "file_count_truncated": mirror_truncated,
                "recorded_source_count": recorded_mirrors,
            },
            "published_wiki": {"page_count": len(pages)},
            "weekly_handoff": {
                "state": "available" if handoff_path else "unavailable",
                "path": handoff_path,
            },
            "plugin_bridges": plugin_bridges,
        }

    def _plugin_bridges(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        """Project installed bridge readiness without exposing plugin settings.

        A configured plugin route is useful planning context: PBOS should ask
        for a real export, not repeat installation or destination setup. The
        manifest's public status deliberately contains more UI-oriented data,
        so this projection keeps only the identifiers and finite state needed
        by the compiler. In particular, it excludes paths, settings values,
        trust actors, timestamps, observed filenames, and evidence bodies.
        """
        status = ObsidianPluginManifest.load(self.project_root).public_status(
            sources,
            project_root=self.project_root,
            vault_root=self.vault_root,
        )
        routes: list[dict[str, str]] = []
        for plugin in status.get("plugins", []):
            if not isinstance(plugin, dict):
                continue
            plugin_id = str(plugin.get("id") or "").strip()[:80]
            adapter = str(plugin.get("adapter") or "").strip()[:48]
            if not plugin_id or not adapter:
                continue
            route_state = self._plugin_route_state(plugin)
            capture_state = str(plugin.get("capture_state") or "").strip()
            if capture_state not in {
                "awaiting_trust",
                "trust_stale",
                "trust_unavailable",
                "captured",
                "registered_output",
                "files_detected_pending_registration",
                "files_detected_pending_capture",
                "ready_for_first_output",
                "ready_for_first_export",
                "route_unavailable",
            }:
                capture_state = "route_unavailable"
            routes.append(
                {
                    "id": plugin_id,
                    "adapter": adapter,
                    "route_state": route_state,
                    "capture_state": capture_state,
                }
            )
        routes.sort(key=lambda item: item["id"])
        routes = routes[:12]
        return {
            "ready_route_count": sum(item["route_state"] != "not_ready" for item in routes),
            "routes": routes,
        }

    @staticmethod
    def _plugin_route_state(plugin: dict[str, Any]) -> str:
        """Normalize manifest status into a small, planning-safe state set."""
        status = str(plugin.get("status") or "")
        runtime = plugin.get("runtime_configuration")
        runtime_state = str(runtime.get("state") or "") if isinstance(runtime, dict) else ""
        if status == "captured":
            return "captured"
        if status == "registered_output":
            return "registered_output"
        if status == "awaiting_export" and runtime_state == "configured":
            return "configured_awaiting_export"
        if status == "awaiting_output" and runtime_state == "configured":
            return "configured_awaiting_output"
        return "not_ready"

    @staticmethod
    def _managed_file_count(root: Path, limit: int = 10_000) -> tuple[int, bool]:
        """Count managed evidence pages safely, with a fixed planning bound."""
        if not root.is_dir():
            return 0, False
        count = 0
        try:
            for candidate in root.rglob("*"):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                count += 1
                if count >= limit:
                    return count, True
        except OSError:
            return count, True
        return count, False

    def _published_documents(self, repository: WikiRepository, pack: Any) -> list[dict[str, Any]]:
        if pack is None:
            return []
        page_ids: list[str] = []
        for reference in pack.section_refs:
            kind, separator, page_id = str(reference).partition(":")
            if separator and kind in {"page", "decision"} and page_id not in page_ids:
                page_ids.append(page_id)
        # The rendered context reserves enough room for at least one primary
        # source. A long source can therefore displace a retrieved Wiki page
        # from ``section_refs`` even though retrieval selected it for this
        # task. Retain those selected *published* pages as immutable planning
        # references; never fall back to arbitrary Vault files.
        retrieved_paths = {
            str(reference)
            for reference in pack.retrieval_refs
            if str(reference).startswith("wiki/") or str(reference) == "AGENTS.md"
        }
        if retrieved_paths:
            for page in repository.list_pages(self.project_id):
                page_id = str(page.get("id") or "")
                if (
                    page_id
                    and str(page.get("path") or "") in retrieved_paths
                    and page.get("status") == "published"
                    and page_id not in page_ids
                ):
                    page_ids.append(page_id)
        documents: list[dict[str, Any]] = []
        for page_id in page_ids:
            page = repository.get_page(self.project_id, page_id)
            revision = repository.get_page_content(self.project_id, page_id)
            if not page or not revision or page.get("status") != "published":
                continue
            supporting_refs = [
                self._source_ref(repository, citation["source_id"])
                for citation in repository.list_citations(self.project_id, page_id)
            ]
            content = str(revision["content"])
            documents.append(
                {
                    "ref": f"wiki:{page_id}@{revision['content_hash']}",
                    "path": str(page["path"]),
                    "title": str(page.get("title") or page["path"]),
                    "excerpt": self.working_context._excerpt(content),
                    "sha256": str(revision["content_hash"]),
                    "kind": "published_wiki",
                    "supporting_refs": [reference for reference in supporting_refs if reference],
                }
            )
        return documents

    def _source_ref(self, repository: WikiRepository, source_id: str) -> str:
        source = repository.get_source(self.project_id, source_id)
        if not source or source.get("status") != "processed":
            return ""
        return f"source:{source_id}@{source['content_hash']}"
