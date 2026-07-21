"""Safe minimal project Wiki initialization for a configured Obsidian Vault."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_index import WikiSearchIndex


class WikiBootstrapError(ValueError):
    """Raised when the project cannot be initialized inside its configured Vault."""


class WikiBootstrapService:
    """Create only missing managed Wiki files; existing user content remains authoritative."""

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
        if created:
            vault.commit(snapshot)
        # User-owned rule edits are authoritative, but still need a revision ledger.
        # The complete snapshot prevents unrelated Wiki pages from being archived.
        self.repository.record_publication(project_id=project_id, contents=snapshot, source_ids=[])
        indexing = self.search_index.sync_wiki_snapshot(project_id=project_id, contents=snapshot)
        return {
            "project_id": project_id,
            "created": created,
            "status": "initialized" if created else "already_initialized",
            "indexing": indexing,
        }

    @staticmethod
    def _defaults(project_id: str) -> dict[str, str]:
        return {
            "AGENTS.md": build_default_agents_rules(project_id),
            "wiki/overview.md": (
                "---\ntitle: Project Overview\nkind: brief\nstatus: draft\n---\n"
                "# Project Overview\n\nThis page is the project knowledge hub. Add only evidence-backed synthesis through governed proposals.\n"
            ),
            "wiki/index.md": "# Wiki Index\n\n- [[wiki/overview.md]]\n",
            "wiki/log.md": "# Wiki Maintenance Log\n\n- Project Wiki initialized.\n",
        }
