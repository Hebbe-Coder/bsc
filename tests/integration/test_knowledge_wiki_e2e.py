from datetime import datetime, timezone

from app.knowledge.knowledge_graph import KnowledgeGraphService
from app.knowledge.proposal_gate import ProposalGate
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_bootstrap import WikiBootstrapService
from app.knowledge.wiki_compiler import WikiCompiler
from app.knowledge.wiki_contracts import SourceStatus
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import HorizonSignal, SourceCaptureService
from app.knowledge.wiki_sync import ObsidianSyncService


class FakeCompilerProvider:
    def __init__(self, response):
        self.response = response

    def compile_wiki(self, _prompt):
        return self.response


def _page_snapshots(repository, project_id):
    snapshots = []
    for page in repository.list_pages(project_id):
        content = repository.get_page_content(project_id, page["id"])
        if content:
            snapshots.append({**page, "content": content["content"]})
    return snapshots


def test_filesystem_wiki_lifecycle_is_source_backed_and_atomic(tmp_path, monkeypatch):
    project_id = "project-a"
    root = tmp_path / "vault"
    root.mkdir()
    (root / "research.md").write_text("# Research\nHuman approval is mandatory.", encoding="utf-8")
    repository = WikiRepository(db_path=str(tmp_path / "knowledge.db"))
    project_root = root / "clients" / "acme"
    project_root.mkdir(parents=True)
    user_rules = build_default_agents_rules(project_id) + "\n# Acme review note\nHuman approval is mandatory.\n"
    (project_root / "AGENTS.md").write_text(user_rules, encoding="utf-8")
    monkeypatch.setattr("app.knowledge.wiki_bootstrap.settings.OBSIDIAN_VAULT_ROOT", str(root))
    try:
        repository.configure_vault(project_id, "clients/acme")
        bootstrap = WikiBootstrapService(repository).initialize(project_id=project_id)
        assert set(bootstrap["created"]) == {"README.md", "wiki/overview.md", "wiki/index.md", "wiki/log.md"}
        assert (project_root / "AGENTS.md").read_text(encoding="utf-8") == user_rules

        sync_report = ObsidianSyncService(repository, root).sync(project_id=project_id)
        note = repository.list_sources(project_id)[0]
        horizon = SourceCaptureService(repository).capture(
            HorizonSignal(
                project_id=project_id,
                url="https://news.example.com/radar/42",
                title="Approval controls mature",
                summary="Human approval remains a required control.",
                published_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
                tags=["governance"],
            ).to_source_input()
        ).source
        capture = SourceCaptureService(repository)
        capture.transition_source(project_id, note["id"], target=SourceStatus.ELIGIBLE)
        capture.transition_source(project_id, horizon["id"], target=SourceStatus.ELIGIBLE)

        provider = FakeCompilerProvider(
            {
                "rationale": "Record the project approval control from both sources.",
                "operations": [
                    {
                        "operation": "create",
                        "path": "wiki/decisions/human-approval.md",
                        "content": (
                            "---\ntitle: Human Approval\nkind: decision\n---\n"
                            f"Human approval is mandatory. [source:{note['id']}] [source:{horizon['id']}]"
                        ),
                        "source_ids": [note["id"], horizon["id"]],
                    }
                ],
            }
        )
        compiler = WikiCompiler(repository, provider)
        compiled = compiler.compile_maintenance(
            project_id=project_id,
            source_ids=[note["id"], horizon["id"]],
            trigger="integration",
            rules_text=user_rules,
            page_snapshots=_page_snapshots(repository, project_id),
        )
        WikiEvaluator(repository).save_case(
            project_id=project_id,
            case_id="approval-citations",
            case_type="citation",
            expected={"source_ids": [note["id"], horizon["id"]]},
        )

        vault = FilesystemWikiVault(root, project_id, "clients/acme")
        published = ProposalGate(repository, vault).publish(proposal=compiler_result_to_proposal(compiled.proposal), rules_text=user_rules)

        assert sync_report == {"scanned": 1, "created": 1, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0}
        assert published["status"] == "published"
        assert (project_root / "wiki" / "decisions" / "human-approval.md").is_file()
        assert {page["path"] for page in repository.list_pages(project_id)} >= {
            "AGENTS.md", "wiki/overview.md", "wiki/index.md", "wiki/log.md", "wiki/decisions/human-approval.md"
        }
        decision = next(page for page in repository.list_pages(project_id) if page["path"] == "wiki/decisions/human-approval.md")
        assert {citation["source_id"] for citation in repository.list_citations(project_id, decision["id"])} == {note["id"], horizon["id"]}
        assert {source["status"] for source in repository.list_sources(project_id)} == {"processed"}
        assert {edge["edge_type"] for edge in KnowledgeGraphService(repository).list_edges(project_id)} >= {
            "wiki_cites_source", "wiki_links_to", "proposal_changes_page"
        }
        assert repository.get_proposal(project_id, compiled.proposal["id"])["status"] == "published"
    finally:
        repository.close()


def compiler_result_to_proposal(record):
    from app.knowledge.wiki_contracts import WikiProposal

    return WikiProposal.model_validate({field: record[field] for field in WikiProposal.model_fields})
