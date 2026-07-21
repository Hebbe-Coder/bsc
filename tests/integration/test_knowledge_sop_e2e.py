"""End-to-end proof that SOP generation consumes only the active project Wiki."""

from __future__ import annotations

from app.knowledge.context_pack import WikiContextProvider
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.orchestrator.agents.sop_builder import SopBuilderAgent
from app.orchestrator.methodology import MethodologyBridge


class EmptyMethodologyService:
    def retrieve(self, **_kwargs):
        return []


class RecordingLLM:
    def __init__(self) -> None:
        self.prompt = ""

    def chat(self, _system_prompt, user_prompt, **_kwargs):
        self.prompt = user_prompt
        return {"sop": {"sops": []}}


class StaticSopEngine:
    def generate_full_sop_report(self, *_args, **_kwargs):
        return {"workflow": [], "roles": [], "sla": []}


def _seed_project(repository: WikiRepository, root, project_id: str, secret: str):
    vault = FilesystemWikiVault(root, project_id, f"projects/{project_id}")
    contents = {
        "AGENTS.md": build_default_agents_rules(project_id),
        "wiki/decisions/control.md": (
            "---\ntitle: Project Control\nkind: decision\n---\n"
            f"{secret} [source:source-{project_id}]\n"
        ),
    }
    vault.commit(contents)
    repository.configure_vault(project_id, f"projects/{project_id}")
    source = SourceCaptureService(repository).capture(
        CapturedSourceInput(
            project_id=project_id,
            source_type="manual_upload",
            origin=f"{project_id}.md",
            raw_content=f"# Evidence\n{secret}",
            trust_level="trusted",
        )
    ).source
    # The human-readable citation is intentionally updated with the real immutable ID.
    contents["wiki/decisions/control.md"] = contents["wiki/decisions/control.md"].replace(
        f"source-{project_id}", source["id"]
    )
    vault.commit(contents)
    repository.record_publication(project_id=project_id, contents=contents, source_ids=[source["id"]])
    return source


def test_prd_to_sop_uses_only_active_project_wiki_context(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repository = WikiRepository(db_path=str(tmp_path / "knowledge-sop.db"))
    source_a = _seed_project(repository, root, "project-a", "A requires a two-person approval gate.")
    _seed_project(repository, root, "project-b", "B requires a separate market-review policy.")
    provider = WikiContextProvider(repository, vault_root=root, max_characters=4_000)
    llm = RecordingLLM()
    agent = SopBuilderAgent(
        llm_service=llm,
        bridge=MethodologyBridge(
            service=EmptyMethodologyService(), wiki_context_provider=provider, wiki_enabled=True
        ),
    )
    try:
        result = agent.run(
            {"name": "Project A launch PRD", "flows": [{"name": "approval"}]},
            _engine=StaticSopEngine(),
            project_id="project-a",
        )

        context = result["sop"]["_knowledge_context"]
        assert context["knowledge_context_used"] is True
        assert source_a["id"] in context["source_ids"]
        assert "A requires a two-person approval gate." in llm.prompt
        assert "B requires a separate market-review policy." not in llm.prompt
        assert "project-b" not in llm.prompt

        no_vault = MethodologyBridge(
            service=EmptyMethodologyService(), wiki_context_provider=provider, wiki_enabled=True
        ).retrieve_wiki_context("project-without-vault", "legacy compatibility")
        assert no_vault["knowledge_context_used"] is False
    finally:
        repository.close()
