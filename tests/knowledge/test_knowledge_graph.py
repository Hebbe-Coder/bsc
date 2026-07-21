from app.knowledge.knowledge_graph import KnowledgeGraphService
from app.knowledge.wiki_repository import WikiRepository


def test_graph_rebuilds_project_scoped_page_and_evidence_edges_idempotently(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "graph.db"))
    graph = KnowledgeGraphService(repo)
    pages = [
        {
            "id": "page-decision",
            "project_id": "project-a",
            "path": "wiki/decisions/approval.md",
            "page_kind": "decision",
            "content": "# Approval\n[[wiki/concepts/review.md]] [source:source-a]",
        },
        {
            "id": "page-review",
            "project_id": "project-a",
            "path": "wiki/concepts/review.md",
            "page_kind": "concept",
            "content": "# Review",
        },
    ]
    try:
        first = graph.rebuild(project_id="project-a", pages=pages, proposal_id="proposal-a")
        second = graph.rebuild(project_id="project-a", pages=pages, proposal_id="proposal-a")

        assert {(edge["from_id"], edge["to_id"], edge["edge_type"]) for edge in first} == {
            ("page-decision", "page-review", "wiki_links_to"),
            ("page-decision", "source-a", "wiki_cites_source"),
            ("page-decision", "source-a", "decision_uses_evidence"),
            ("proposal-a", "page-decision", "proposal_changes_page"),
            ("proposal-a", "page-review", "proposal_changes_page"),
        }
        assert second == first
        assert graph.list_edges("project-b") == []
    finally:
        repo.close()
