from app.knowledge.knowledge_graph import KnowledgeGraphService
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


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


def test_graph_visualization_returns_only_persisted_entity_nodes(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "visualization.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="Evidence", trust_level="trusted")
    ).source
    try:
        repo.record_publication(
            project_id="project-a",
            contents={"wiki/overview.md": "# Overview\n[source:%s]\n" % source["id"]},
            source_ids=[],
        )
        payload = KnowledgeGraphService(repo).visualization(project_id="project-a")

        assert {node["node_type"] for node in payload["nodes"]} == {"page", "source"}
        assert payload["edges"][0]["edge_type"] == "wiki_cites_source"
    finally:
        repo.close()


def test_publication_graph_evidence_edges_keep_citation_and_source_revision_lineage(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "citation-lineage.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="evidence/brief.md",
            raw_content="Immutable evidence revision.",
            trust_level="trusted",
        )
    ).source
    try:
        repo.record_publication(
            project_id="project-a",
            contents={"wiki/overview.md": f"# Overview\nEvidence-backed conclusion. [source:{source['id']}]\n"},
            source_ids=[source["id"]],
        )
        page = repo.list_pages("project-a")[0]
        citation = repo.list_citations("project-a", page["id"])[0]
        evidence_edges = [
            edge for edge in repo.list_graph_edges("project-a")
            if edge["edge_type"] in {"wiki_cites_source", "decision_uses_evidence"}
        ]

        assert len(evidence_edges) == 1
        evidence = evidence_edges[0]["metadata"]["evidence"]
        assert evidence["citation_id"] == citation["id"]
        assert evidence["source_id"] == source["id"]
        assert evidence["source_content_hash"] == source["content_hash"]
        assert evidence["page_content_hash"] == page["content_hash"]
        assert evidence["page_version"] == page["version"]
        assert evidence["extraction_method"] == "explicit_source_marker_v1"
        assert "raw_content" not in evidence
    finally:
        repo.close()


def test_graph_queries_are_bounded_and_expose_project_scoped_backlinks(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "graph-bounded.db"))
    try:
        repo.record_publication(
            project_id="project-a",
            contents={
                "wiki/index.md": "# Index\n- [[wiki/concepts/a.md]]\n",
                "wiki/concepts/a.md": "---\ntitle: A\nkind: concept\n---\n# A\n",
            },
            source_ids=[],
        )
        pages = {page["path"]: page for page in repo.list_pages("project-a")}
        graph = KnowledgeGraphService(repo)

        assert graph.backlinks(project_id="project-a", page_id=pages["wiki/concepts/a.md"]["id"])[0]["from_id"] == pages["wiki/index.md"]["id"]
        bounded = graph.visualization(project_id="project-a", limit=1)
        assert len(bounded["edges"]) == 1
        assert bounded["truncated"] is False
        assert graph.backlinks(project_id="project-b", page_id=pages["wiki/concepts/a.md"]["id"]) == []
    finally:
        repo.close()
