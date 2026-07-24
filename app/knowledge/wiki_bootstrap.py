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
        "02_Assets",
        "02_Assets/curated",
        "03_Projects",
        "03_Projects/active",
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
        "05_Archive",
        "05_Archive/reviewed",
        "06_Skills",
        "06_Skills/candidates",
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
            "00-Workspace.md": (
                "# \u77e5\u8bc6\u5de5\u4f5c\u53f0\n\n"
                "Obsidian \u662f\u9605\u8bfb\u3001\u8fde\u63a5\u4e0e\u4fee\u6539\u7684\u77e5\u8bc6 IDE\uff1bBSC \u662f\u7f16\u6392\u3001\u5ba1\u6838\u3001\u8bc4\u6d4b\u4e0e\u8ffd\u6eaf\u7cfb\u7edf\u3002\u76ee\u5f55\u662f\u5de5\u4f5c\u6d41\u8bed\u4e49\uff0c\u4e0d\u662f\u5355\u7eaf\u5b58\u50a8\u4f4d\u7f6e\u3002\n\n"
                "## \u5de5\u4f5c\u6d41\u5165\u53e3\n\n"
                "| \u9700\u8981 | Obsidian \u4f4d\u7f6e | BSC \u5982\u4f55\u5904\u7406 |\n"
                "| --- | --- | --- |\n"
                "| \u60f3\u6cd5\u3001\u526a\u85cf\u3001\u5f85\u5904\u7406\u539f\u6599 | `00_Inbox/` \u548c `inbox/` | \u4f5c\u4e3a\u7075\u611f\u4e0e\u5019\u9009\u8bc1\u636e\u91c7\u96c6\uff0c\u7b49\u5f85\u5206\u8bca\u3002 |\n"
                "| \u5916\u90e8\u8d44\u6599\u3001\u6587\u6863\u5bfc\u5165 | `01_Sources/` \u548c `raw/` | \u4fdd\u7559\u539f\u59cb\u8bc1\u636e\u53ca\u6765\u6e90\uff0c\u4e0d\u88ab\u6539\u5199\u3002 |\n"
                "| \u4f60\u5df2\u6574\u7406\u7684\u8d44\u4ea7 | `02_Assets/` | \u4f5c\u4e3a\u7ecf\u7528\u6237\u6574\u7406\u7684\u7d22\u5f15\u4e0e\u5019\u9009\u77e5\u8bc6\uff0c\u4ecd\u7ecf\u8fc7\u8bc1\u636e\u4e0e\u63d0\u6848\u95e8\u7981\u3002 |\n"
                "| \u6b63\u5728\u505a\u7684\u4e8b | `03_Projects/active/` | \u4f5c\u4e3a\u4efb\u52a1\u80cc\u666f\u3001\u7ea6\u675f\u548c\u51b3\u7b56\u7eaa\u5f55\u540c\u6b65\uff0c\u7528\u4e8e\u5b9a\u5236 SOP \u4e0e\u4e0a\u4e0b\u6587\u5305\u3002 |\n"
                "| \u5df2\u53d1\u5e03\u77e5\u8bc6 | `wiki/` | \u53ea\u63a5\u6536\u7ecf\u63d0\u6848\u3001lint\u3001\u8bc4\u6d4b\u548c\u53d1\u5e03\u540e\u7684\u7ed3\u679c\u3002 |\n"
                "| \u53ef\u590d\u7528\u7684\u5904\u7406\u65b9\u6cd5 | `06_Skills/candidates/` \u4e0e `methods/` | \u524d\u8005\u662f\u5019\u9009\u65b9\u6cd5\uff0c\u540e\u8005\u53ea\u5b58\u653e\u5df2\u8bc1\u660e\u7684\u7248\u672c\u3002 |\n"
                "| \u5b9e\u9645\u4ea7\u51fa | `04_Outputs/` \u4e0e `outputs/` | \u767b\u8bb0\u3001\u8bc4\u4f30\u540e\u8fdb\u5165\u53cd\u9988\u56de\u6d41\u3002 |\n"
                "| \u6682\u4e0d\u4f7f\u7528\u7684\u6750\u6599 | `05_Archive/` | \u4ec5\u4f9b\u4eba\u5de5\u4fdd\u5b58\uff0c\u4e0d\u4f1a\u88ab\u5b9a\u65f6\u4efb\u52a1\u81ea\u52a8\u91cd\u65b0\u6444\u5165\u3002 |\n\n"
                "## \u65e5\u5e38\u95ed\u73af\n\n"
                "1. \u628a\u65b0\u4fe1\u606f\u653e\u5165\u7075\u611f\u6216\u8d44\u6e90\u5c42\uff0c\u4e0d\u5148\u5199\u7ed3\u8bba\u3002\n"
                "2. \u5728 `03_Projects/active/` \u5199\u6e05\u5f53\u524d\u4efb\u52a1\u7684\u76ee\u6807\u3001\u8bfb\u8005\u3001\u7ea6\u675f\u3001\u98ce\u9669\u4e0e\u9a8c\u6536\uff0c\u8ba9\u751f\u6210\u7684 SOP \u6709\u9879\u76ee\u4e0a\u4e0b\u6587\u3002\n"
                "3. \u5728 BSC \u5ba1\u67e5 Wiki \u548c\u65b9\u6cd5\u63d0\u6848\uff0c\u4ece Obsidian \u9605\u8bfb\u5df2\u53d1\u5e03\u7684\u7ed3\u679c\u3002\n"
                "4. \u628a\u771f\u5b9e\u4ea7\u51fa\u653e\u5165\u58f0\u660e\u7684\u8f93\u51fa\u76ee\u5f55\uff0c\u5728\u6bcf\u5468\u84b8\u998f\u4e2d\u53cd\u9988\u6709\u6548\u4e0e\u65e0\u6548\u7684\u505a\u6cd5\u3002\n\n"
                "## \u5bfc\u822a\n\n"
                "- [[wiki/index]]\n"
                "- [[wiki/overview]]\n"
                "- [[wiki/log]]\n"
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
