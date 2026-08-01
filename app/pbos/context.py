"""Bounded Obsidian context for PBOS planning.

PBOS may use working context and governed knowledge, but never treats raw
captures as personal experience or sends the full Vault to a plan compiler.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from app.knowledge.context_pack import WikiContextProvider
from app.knowledge.generation_provenance import sanitize_untrusted_text
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.wiki_repository import WikiRepository
from app.pbos.text_integrity import is_unreadable_legacy_text


class PBOSVaultContextBuilder:
    """Return a compact, reviewable context pack from the project memory layer."""

    ALLOWED_ROOTS = (
        "03_Projects/active",
        "02_Assets/curated",
        "methods",
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

    The active project handoff is the primary planning input. Published pages
    remain B-layer authority and retain their evidence lineage, but navigation
    pages must not displace the current delivery brief from a bounded prompt.
    """

    MAX_WORKING_DOCUMENTS = 4
    MAX_VERIFIED_OUTPUTS = 2
    MAX_ADMITTED_EVIDENCE_DOCUMENTS = 1
    MIN_GOVERNED_DOCUMENTS = 2
    MAX_PROCESSED_GROWTH_FEEDBACK = 3

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
            admitted_evidence = self._admitted_evidence_documents(repository, pack, provider)
            operational_state = self._operational_state(repository)
            verified_outputs = self._verified_output_documents(repository)
            growth_feedback = self._processed_growth_feedback(repository)
        finally:
            if owns_repository:
                repository.close()
        documents = self._prioritized_documents(
            working["documents"],
            verified_outputs,
            admitted_evidence,
            governed,
        )
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
        context_integrity = self._context_integrity(documents)
        return {
            "availability": "available" if documents else (
                "no_governed_context" if pack is not None else working["availability"]
            ),
            "documents": documents,
            "refs": refs,
            "context_integrity": context_integrity,
            "governed_wiki": {
                "available": pack is not None,
                "revision": pack.revision if pack is not None else "",
                "page_ids": list(pack.page_ids) if pack is not None else [],
                "source_ids": list(pack.source_ids) if pack is not None else [],
                "retrieval_refs": list(pack.retrieval_refs) if pack is not None else [],
            },
            "growth_feedback": growth_feedback,
            "operational_state": operational_state,
        }

    def _processed_growth_feedback(self, repository: WikiRepository) -> dict[str, Any]:
        """Expose only directional output feedback after its governed route ran.

        A registered plugin output remains excluded from planning context. Its
        explicit feedback can guide a later PBOS plan only after the Growth
        feedback router has durably processed it. This preserves the distinction
        between an unreviewed model response, a user's direction, and verified
        personal learning evidence.
        """
        growth = GrowthRepository.borrow(repository)
        items: list[dict[str, str]] = []
        for feedback in growth.list_feedback(self.project_id, limit=100):
            if str(feedback.get("status") or "") != "processed":
                continue
            feedback_id = str(feedback.get("id") or "").strip()
            output_id = str(feedback.get("output_id") or "").strip()
            statement = str(feedback.get("correction") or feedback.get("comment") or "").strip()
            feedback_type = str(feedback.get("feedback_type") or "").strip()
            if (
                not feedback_id
                or not output_id
                or not statement
                or not feedback_type
                or is_unreadable_legacy_text(statement)
            ):
                continue
            items.append(
                {
                    "ref": f"growth-feedback:{feedback_id}",
                    "output_ref": f"output:{output_id}",
                    "source": f"growth_output_feedback:{feedback_type[:64]}",
                    "statement": statement[:1_200],
                }
            )
            if len(items) >= self.MAX_PROCESSED_GROWTH_FEEDBACK:
                break
        return {
            "state": "processed_direction_available" if items else "none",
            "items": items,
        }

    @classmethod
    def _prioritized_documents(
        cls,
        working: list[dict[str, Any]],
        verified_outputs: list[dict[str, Any]],
        admitted_evidence: list[dict[str, Any]],
        governed: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fit planning inputs into the prompt without losing governed knowledge.

        ``PBOSVaultContextBuilder`` places the latest weekly handoff before
        active project briefs. Preserve that ordering, then include accepted
        outputs. One retrieval-selected A-layer evidence excerpt and two
        retrieved published pages are reserved whenever present. This prevents
        a large active directory from silently removing the actual research
        input or evidence-governed knowledge layer from a personal plan.
        """
        limit = PBOSVaultContextBuilder.MAX_DOCUMENTS
        selections = (
            (working, cls.MAX_WORKING_DOCUMENTS - min(len(admitted_evidence), cls.MAX_ADMITTED_EVIDENCE_DOCUMENTS)),
            (verified_outputs, cls.MAX_VERIFIED_OUTPUTS),
            (admitted_evidence, cls.MAX_ADMITTED_EVIDENCE_DOCUMENTS),
            (governed, cls.MIN_GOVERNED_DOCUMENTS),
        )
        documents: list[dict[str, Any]] = []
        seen_refs: set[str] = set()

        def append(items: list[dict[str, Any]]) -> None:
            for document in items:
                if len(documents) >= limit:
                    return
                reference = str(document.get("ref") or "")
                identity = reference or str(document.get("path") or "")
                if identity in seen_refs:
                    continue
                seen_refs.add(identity)
                documents.append(document)

        # Fixed initial allocations preserve the intended priority while
        # retaining room for accepted outputs and governed Wiki evidence.
        for items, allocation in selections:
            append(items[:allocation])

        # Backfill unused budget in the same planning order. Each document is
        # still bounded and independently checked by its source adapter.
        for items, allocation in selections:
            append(items[allocation:])
        return documents

    def _admitted_evidence_documents(
        self,
        repository: WikiRepository,
        pack: Any,
        provider: WikiContextProvider,
    ) -> list[dict[str, Any]]:
        """Expose only retrieval-selected, admitted A-layer evidence to PBOS.

        Source text remains untrusted input. The document is bounded and
        sanitized before the plan compiler sees it, while its source and local
        extraction identifiers remain auditable. It is not a Capability,
        Experience, Strategy Genome, or verified output.
        """
        if pack is None:
            return []
        documents: list[dict[str, Any]] = []
        for source_id in tuple(getattr(pack, "source_ids", ())):
            source = repository.get_source(self.project_id, str(source_id))
            if not source or str(source.get("status") or "") not in {"eligible", "processed"}:
                continue
            view = provider.source_context_view(self.project_id, source)
            content = str(view.get("raw_content") or "").strip()
            if not content:
                continue
            extraction_id = str(view.get("extraction_context_id") or "").strip()
            documents.append(
                {
                    "ref": f"source:{source_id}@{source['content_hash']}",
                    "path": f"evidence/{source_id}",
                    "title": str(source.get("origin") or f"Evidence {source_id}")[:200],
                    "excerpt": self.working_context._excerpt(
                        sanitize_untrusted_text(content, data_kind="admitted_evidence", ref_id=str(source_id))
                    ),
                    "sha256": str(source["content_hash"]),
                    "kind": "admitted_evidence",
                    "origin": "admitted_evidence",
                    "supporting_refs": [
                        f"extraction:{extraction_id}"
                    ] if extraction_id else [],
                }
            )
            if len(documents) >= self.MAX_ADMITTED_EVIDENCE_DOCUMENTS:
                break
        return documents

    @staticmethod
    def _context_integrity(documents: list[dict[str, Any]]) -> dict[str, Any]:
        """Expose output-boundary facts derived from the actual selected inputs."""
        raw_plugin_output = False
        raw_copilot_output = False
        unreviewed_managed_output = False
        verified_output_count = 0
        for document in documents:
            path = str(document.get("path") or "").replace("\\", "/").lower()
            origin = str(document.get("origin") or "")
            if path.startswith("04_outputs/"):
                raw_plugin_output = True
                if path.startswith("04_outputs/copilot/"):
                    raw_copilot_output = True
            if path.startswith("outputs/"):
                if origin == "verified_output":
                    verified_output_count += 1
                else:
                    unreviewed_managed_output = True
        return {
            "raw_plugin_output_context_consumed": raw_plugin_output,
            "raw_copilot_context_consumed": raw_copilot_output,
            "unreviewed_managed_output_consumed": unreviewed_managed_output,
            "verified_output_context_count": verified_output_count,
        }

    def _verified_output_documents(self, repository: WikiRepository) -> list[dict[str, Any]]:
        """Expose only hash-valid accepted D-layer prose as PBOS working context.

        Plugin exports under ``04_Outputs`` and managed files under ``outputs``
        must never become planning context merely because they exist on disk.
        The output lifecycle record is the authority: only accepted/filed text
        whose current managed copy still matches its registered hash may be read.
        """
        outputs = GrowthRepository.borrow(repository).list_outputs(self.project_id, limit=100)
        documents: list[dict[str, Any]] = []
        for output in outputs:
            if str(output.get("status") or "") not in {"accepted", "filed"}:
                continue
            if not str(output.get("mime_type") or "").startswith("text/"):
                continue
            document = self._verified_output_document(output)
            if document is not None:
                documents.append(document)
            if len(documents) >= self.MAX_VERIFIED_OUTPUTS:
                break
        return documents

    def _verified_output_document(self, output: dict[str, Any]) -> dict[str, Any] | None:
        relative_path = str(output.get("vault_path") or "").replace("\\", "/")
        relative = PurePosixPath(relative_path)
        if (
            not relative.parts
            or relative.parts[0] != "outputs"
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            return None
        candidate = (self.project_root / relative).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError:
            return None
        try:
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or candidate.stat().st_size > PBOSVaultContextBuilder.MAX_FILE_BYTES
            ):
                return None
            payload = candidate.read_bytes()
            if not hmac.compare_digest(
                hashlib.sha256(payload).hexdigest(),
                str(output.get("content_hash") or "").lower(),
            ):
                return None
            text = payload.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        output_id = str(output.get("id") or "").strip()
        content_hash = str(output.get("content_hash") or "").strip()
        if not output_id or not content_hash:
            return None
        return {
            "ref": f"output:{output_id}@{content_hash}",
            "path": relative.as_posix(),
            "title": str(output.get("title") or output.get("kind") or "Verified output")[:200],
            "excerpt": self.working_context._excerpt(text),
            "sha256": content_hash,
            "origin": "verified_output",
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
        plugin_bridges = self._plugin_bridges(repository, sources)
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

    def _plugin_bridges(
        self,
        repository: WikiRepository,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Project installed bridge readiness without exposing plugin settings.

        A configured plugin route is useful planning context: PBOS should ask
        for a real export, not repeat installation or destination setup. The
        manifest's public status deliberately contains more UI-oriented data,
        so this projection keeps only the identifiers and finite state needed
        by the compiler. In particular, it excludes paths, settings values,
        trust actors, timestamps, observed filenames, and evidence bodies.
        """
        # D-layer registrations are the authority for agent/plugin output
        # state. Omitting them made a registered output look like an empty
        # route and invited the planner to repeat setup work.
        outputs = GrowthRepository.borrow(repository).list_outputs(self.project_id)
        status = ObsidianPluginManifest.load(self.project_root).public_status(
            sources,
            outputs,
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
        path_status = str(plugin.get("path_status") or "")
        runtime = plugin.get("runtime_configuration")
        runtime_state = str(runtime.get("state") or "") if isinstance(runtime, dict) else ""
        if status == "captured":
            return "captured"
        if status == "registered_output":
            return "registered_output"
        route_configured = path_status == "ready" and runtime_state in {
            "configured",
            "declared_only",
            "agent_workspace",
            "interactive_destination",
        }
        if status == "awaiting_export" and route_configured:
            return "configured_awaiting_export"
        if status == "awaiting_output" and route_configured:
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
