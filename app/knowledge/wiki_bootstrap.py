"""Safe minimal project Wiki initialization for a configured Obsidian Vault."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.knowledge.proposal_gate import ProposalGateError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_index import WikiSearchIndex


class WikiBootstrapError(ValueError):
    """Raised when the project cannot be initialized inside its configured Vault."""


class WikiBootstrapService:
    """Create only missing managed Wiki files; existing user content remains authoritative."""

    _MANAGED_DIRECTORIES = (
        "00_Inbox",
        "00_Inbox/auto-capture",
        "00_Inbox/readwise",
        "00_Inbox/web-clipper",
        "00_Inbox/social",
        "01_Sources",
        "01_Sources/feishu",
        "01_Sources/docxer",
        "01_Sources/importer",
        "raw",
        "raw/web",
        "raw/papers",
        "raw/meetings",
        "raw/media",
        "raw/imports",
        "inbox",
        "inbox/horizon",
        "inbox/manual",
        "wiki",
        "wiki/concepts",
        "wiki/entities",
        "wiki/decisions",
        "wiki/research",
        "wiki/playbooks",
        "methods",
        "outputs",
        "04_Outputs",
        "04_Outputs/articles",
        "04_Outputs/hyperframes",
        "reviews",
        "reviews/failures",
        "reviews/corrections",
        "distillations",
        "distillations/每周蒸馏",
        "attachments",
        ".bsc",
    )

    def __init__(self, repository: WikiRepository, *, search_index=None) -> None:
        self.repository = repository
        self.search_index = search_index or WikiSearchIndex(repository)

    def initialize(self, *, project_id: str, actor_id: str = "") -> dict:
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise WikiBootstrapError("project Vault mapping is not configured")
        if not settings.OBSIDIAN_VAULT_ROOT:
            raise WikiBootstrapError("OBSIDIAN_VAULT_ROOT is not configured")
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
        snapshot = dict(vault.contents)
        defaults = self._defaults(project_id)
        created = []
        for path, content in defaults.items():
            if path not in snapshot:
                snapshot[path] = content
                created.append(path)
        created_directories = [
            directory
            for directory in self.managed_directories()
            if not (vault.project_root / directory).is_dir()
        ]
        if created or created_directories:
            try:
                vault.commit(snapshot, directories=self.managed_directories())
            except (OSError, ProposalGateError) as exc:
                raise WikiBootstrapError("unable to write the configured project Vault") from exc
        # User-owned rule edits are authoritative, but still need a revision ledger.
        # The complete snapshot prevents unrelated Wiki pages from being archived.
        self.repository.record_publication(project_id=project_id, contents=snapshot, source_ids=[])
        indexing = self.search_index.sync_wiki_snapshot(project_id=project_id, contents=snapshot)
        return {
            "project_id": project_id,
            "created": created,
            "created_directories": created_directories,
            "status": "initialized" if created or created_directories else "already_initialized",
            "indexing": indexing,
        }

    @classmethod
    def managed_directories(cls) -> tuple[str, ...]:
        return cls._MANAGED_DIRECTORIES

    @staticmethod
    def _defaults(project_id: str) -> dict[str, str]:
        return {
            "AGENTS.md": build_default_agents_rules(project_id),
            "README.md": (
                f"# {project_id} Knowledge Workspace\n\n"
                "This is an operational boundary for one project, not a pre-filled knowledge base. "
                "BSC creates the structure; evidence, decisions, methods, and outputs are added only through real work.\n\n"
                "## A-layer evidence\n\n"
                "- `00_Inbox/` receives declared tool exports such as Horizon, Readwise, Web Clipper, and social imports.\n"
                "- `01_Sources/` holds explicit Feishu, Docxer, and Importer exports.\n"
                "- `raw/` and `inbox/` remain compatible project-local capture roots.\n\n"
                "## Governed knowledge loop\n\n"
                "- `wiki/` contains evidence-backed, reviewable B-layer synthesis.\n"
                "- `methods/` contains only approved, versioned C-layer methods and Skills.\n"
                "- `outputs/` and `04_Outputs/` hold D-layer deliverables before their evaluation and feedback route.\n"
                "- `reviews/` records corrections and failures; `distillations/每周蒸馏/` stores managed daily and weekly review artifacts.\n\n"
                "## First working loop\n\n"
                "1. Declare actual export folders in Studio.\n"
                "2. Capture sources and inspect triage before synthesis.\n"
                "3. Review Wiki and method proposals before publication.\n"
                "4. Register, evaluate, and route real outputs back into the next review.\n"
            ),
            "wiki/overview.md": (
                "---\ntitle: Project Overview\nkind: brief\nstatus: draft\n---\n"
                "# Project Overview\n\nThis page is the project knowledge hub. Add only evidence-backed synthesis through governed proposals. "
                "The workspace starts without factual claims so that project knowledge grows from captured evidence rather than a template.\n"
            ),
            "wiki/index.md": (
                "# Wiki Index\n\n"
                "- [[wiki/overview.md]]\n"
                "- `wiki/concepts/` for durable concepts\n"
                "- `wiki/decisions/` for decision records and rationale\n"
                "- `wiki/research/` for open questions and evidence gaps\n"
                "- `wiki/playbooks/` for published project playbooks\n"
            ),
            "wiki/log.md": "# Wiki Maintenance Log\n\n- Project Wiki initialized.\n",
        }
