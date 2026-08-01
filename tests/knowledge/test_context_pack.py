import pytest

from app.knowledge.context_pack import ContextPackBuilder
from app.knowledge.wiki_contracts import ExtractionArtifact, ExtractionStatus, MediaAsset, SourceRecord, SourceStatus
from app.knowledge.wiki_index import WikiSearchIndex
from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules


def test_context_pack_keeps_priority_and_records_omitted_complete_sections():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=1_800).build(
        project_id="project-a",
        rules=rules,
        task_constraints=["The SOP must respect the customer's review cadence."],
        decisions=[{"id": "decision-1", "project_id": "project-a", "content": "Use a human approval gate."}],
        pages=[{"id": "page-1", "project_id": "project-a", "content": "# Existing decision\nApproval stays manual."}],
        sources=[
            {"id": "source-1", "project_id": "project-a", "raw_content": "Evidence claim with citation context."},
            {"id": "source-2", "project_id": "project-a", "raw_content": "x" * 1_000},
        ],
        weekly_distillation={"id": "week-30", "project_id": "project-a", "content": "Weekly signal."},
    )

    assert "[rules:project-a]" in pack.rendered
    assert "[constraint:constraint-1]" in pack.rendered
    assert "source-1" in pack.source_ids
    assert "source-2" in pack.omitted_refs
    assert pack.character_count <= pack.character_budget
    assert pack.revision


def test_context_pack_rejects_cross_project_records():
    rules = parse_project_rules(build_default_agents_rules("project-a"))

    with pytest.raises(ValueError, match="project scoped"):
        ContextPackBuilder().build(
            project_id="project-a",
            rules=rules,
            sources=[{"id": "source-b", "project_id": "project-b", "raw_content": "leak"}],
        )


def test_context_pack_keeps_a_bounded_source_excerpt_when_pages_consume_the_budget():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=2_000).build(
        project_id="project-a",
        rules=rules,
        pages=[{
            "id": "bootstrap-page",
            "project_id": "project-a",
            "content": "Published guidance. " * 120,
        }],
        sources=[{
            "id": "large-prd",
            "project_id": "project-a",
            "raw_content": "Opening requirement. " + ("Detailed requirement. " * 500) + "Closing acceptance criterion.",
        }],
    )

    assert pack.character_count <= pack.character_budget
    assert pack.source_ids == ("large-prd",)
    assert "[source:large-prd] Evidence" in pack.rendered
    assert "[CONTEXT_EXCERPT: content truncated; consult the immutable source]" in pack.rendered
    assert "Opening requirement." in pack.rendered
    assert "Closing acceptance criterion." in pack.rendered
    assert pack.rendered.split("[CONTEXT_EXCERPT", 1)[0].rstrip().endswith(".")
    assert "large-prd:excerpted_for_budget" in pack.omitted_refs


def test_context_pack_can_prioritize_full_source_evidence_over_derived_pages():
    rules = parse_project_rules(build_default_agents_rules("project-a"))
    pack = ContextPackBuilder(max_characters=1_800).build(
        project_id="project-a",
        rules=rules,
        pages=[{
            "id": "page-a",
            "project_id": "project-a",
            "content": "Derived context. " * 120,
        }],
        sources=[{
            "id": "source-a",
            "project_id": "project-a",
            "raw_content": "Primary evidence must remain visible before older derived pages are considered. " * 8,
        }],
        sources_first=True,
    )

    assert pack.source_ids == ("source-a",)
    assert "Primary evidence must remain visible" in pack.rendered
    assert "page-a" in pack.omitted_refs


class CandidateRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, *, project_id, top_k, rerank):
        self.calls.append((query, project_id, top_k, rerank))
        return [
            {"source": "evidence://project-a/source-relevant", "doc_format": "evidence/manual_upload"},
            {"source": "wiki://project-a/wiki/decisions/relevant.md", "doc_format": "wiki_markdown"},
        ]


def test_context_provider_uses_hybrid_retrieval_to_bound_candidate_records(tmp_path):
    from app.knowledge.context_pack import WikiContextProvider
    from app.knowledge.vault import FilesystemWikiVault
    from app.knowledge.wiki_repository import WikiRepository
    from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService

    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "context-retrieval.db"))
    repo.configure_vault("project-a", "projects/project-a")
    vault = FilesystemWikiVault(root, "project-a")
    vault.commit({"AGENTS.md": build_default_agents_rules("project-a")})
    source_index = type("Index", (), {"project_source": lambda self, source: {"status": "ingested"}})()
    relevant = SourceCaptureService(repo, search_index=source_index).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Relevant evidence", trust_level="trusted")
    ).source
    irrelevant = SourceCaptureService(repo, search_index=source_index).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", raw_content="Irrelevant evidence", trust_level="trusted")
    ).source
    repo._execute("UPDATE knowledge_sources SET id=? WHERE project_id=? AND id=?", ("source-relevant", "project-a", relevant["id"]))
    repo._execute("UPDATE knowledge_sources SET id=? WHERE project_id=? AND id=?", ("source-irrelevant", "project-a", irrelevant["id"]))
    repo._commit()
    repo.record_publication(
        project_id="project-a",
        contents={
            "wiki/decisions/relevant.md": "---\ntitle: Relevant\nkind: decision\n---\nRelevant decision.",
            "wiki/decisions/irrelevant.md": "---\ntitle: Irrelevant\nkind: decision\n---\nIrrelevant decision.",
        },
        source_ids=[],
    )
    retriever = CandidateRetriever()
    try:
        pack = WikiContextProvider(repo, vault_root=root, retrieval_service=retriever).build_context(
            project_id="project-a", task_constraints=["approval policy"]
        )

        assert retriever.calls == [("approval policy", "project-a", 24, True)]
        assert pack is not None
        assert "Relevant evidence" in pack.rendered
        assert "Irrelevant evidence" not in pack.rendered
        assert "Relevant decision" in pack.rendered
        assert "Irrelevant decision" not in pack.rendered
        assert set(pack.retrieval_refs) == {"source-relevant", "wiki/decisions/relevant.md"}
        assert pack.token_budget == pack.character_budget // 4
    finally:
        repo.close()


def test_context_provider_retrieves_completed_manual_extraction_with_original_source_identity(tmp_path):
    from app.knowledge.context_pack import WikiContextProvider
    from app.knowledge.vault import FilesystemWikiVault
    from app.knowledge.wiki_repository import WikiRepository

    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "context-extraction-retrieval.db"))
    repo.configure_vault("project-a", "projects/project-a")
    FilesystemWikiVault(root, "project-a").commit({"AGENTS.md": build_default_agents_rules("project-a")})
    try:
        source = repo.create_source(SourceRecord(
            id="manual-pdf-source",
            project_id="project-a",
            source_type="manual_upload",
            origin="projects/project-a/01_Sources/memgpt.pdf",
            vault_path="projects/project-a/01_Sources/memgpt.pdf",
            content_hash="a" * 64,
            raw_content="Unsupported format retained as provenance only.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            metadata={"sync": "obsidian", "extraction_status": "complete"},
        ))
        asset = repo.register_media_asset(MediaAsset(
            id="manual-pdf-asset",
            project_id="project-a",
            source_id=source["id"],
            mime_type="application/pdf",
            byte_hash="b" * 64,
            byte_size=42,
            storage_ref="projects/project-a/01_Sources/memgpt.pdf",
        ))
        extraction = repo.create_extraction_artifact(ExtractionArtifact(
            id="manual-pdf-extraction",
            project_id="project-a",
            source_id=source["id"],
            asset_id=asset["id"],
            extractor="pdf-text",
            extractor_revision="local-v2",
            input_hash="b" * 64,
            content_hash="c" * 64,
            content="MemGPT separates external archival memory from the prompt context for agent systems.",
            status=ExtractionStatus.COMPLETE,
        ))

        result = WikiSearchIndex(repo).sync_completed_extraction_projections(project_id="project-a")
        unchanged = WikiSearchIndex(repo).sync_completed_extraction_projections(project_id="project-a")
        pack = WikiContextProvider(repo, vault_root=root).build_context(
            project_id="project-a",
            task_constraints=["Design an agent memory system using archival memory."],
        )

        assert result == {"projected": 1, "unchanged": 0, "failed": 0, "skipped": 0}
        assert unchanged == {"projected": 0, "unchanged": 1, "failed": 0, "skipped": 0}
        assert pack is not None
        assert pack.source_ids == (source["id"],)
        assert source["id"] in pack.retrieval_refs
        assert "MemGPT separates external archival memory" in pack.rendered
        assert f"extraction={extraction['id']}" in pack.rendered
        assert repo.get_source("project-a", source["id"])["raw_content"] == "Unsupported format retained as provenance only."
    finally:
        repo.close()


def test_completed_extraction_index_is_bounded_without_mutating_the_artifact(tmp_path):
    from app.knowledge.vault import FilesystemWikiVault
    from app.knowledge.wiki_repository import WikiRepository

    class RecordingService:
        def __init__(self):
            self.calls = []

        def ingest_text(self, text, **kwargs):
            self.calls.append((text, kwargs))
            return {"status": "ingested", "doc_id": kwargs["doc_id"], "version": 1}

    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "bounded-extraction-index.db"))
    repo.configure_vault("project-a", "projects/project-a")
    FilesystemWikiVault(root, "project-a").commit({"AGENTS.md": build_default_agents_rules("project-a")})
    service = RecordingService()
    try:
        source = repo.create_source(SourceRecord(
            id="bounded-source", project_id="project-a", source_type="manual_upload",
            origin="projects/project-a/01_Sources/long.txt", vault_path="projects/project-a/01_Sources/long.txt",
            content_hash="d" * 64, raw_content="Immutable source descriptor.", trust_level="trusted",
            status=SourceStatus.ELIGIBLE, metadata={"sync": "obsidian", "extraction_status": "complete"},
        ))
        asset = repo.register_media_asset(MediaAsset(
            id="bounded-asset", project_id="project-a", source_id=source["id"], mime_type="text/plain",
            byte_hash="e" * 64, byte_size=128 * 1024, storage_ref="projects/project-a/01_Sources/long.txt",
        ))
        content = "useful first line\n" + ("x" * (WikiSearchIndex.MAX_EXTRACTION_INDEX_CHARS + 1_024))
        extraction = repo.create_extraction_artifact(ExtractionArtifact(
            id="bounded-extraction", project_id="project-a", source_id=source["id"], asset_id=asset["id"],
            extractor="utf8-text", extractor_revision="local-v2", input_hash="e" * 64,
            content_hash="f" * 64, content=content, status=ExtractionStatus.COMPLETE,
        ))

        result = WikiSearchIndex(repo, service=service).project_completed_extraction(
            source=source, extraction=extraction
        )

        assert result["status"] == "ingested"
        indexed, kwargs = service.calls[0]
        assert "truncated=true" in indexed
        assert len(indexed) <= WikiSearchIndex.MAX_EXTRACTION_INDEX_CHARS + 160
        assert kwargs["doc_id"] == WikiSearchIndex.source_doc_id(source["id"])
        assert repo.get_extraction_content("project-a", extraction["id"])["content"] == content
    finally:
        repo.close()


def test_context_provider_excludes_untriaged_horizon_evidence_even_when_retrieval_hits_it(tmp_path):
    from app.knowledge.context_pack import WikiContextProvider
    from app.knowledge.vault import FilesystemWikiVault
    from app.knowledge.wiki_repository import WikiRepository

    root = tmp_path / "vault"
    root.mkdir()
    repo = WikiRepository(db_path=str(tmp_path / "context-triage-boundary.db"))
    repo.configure_vault("project-a", "projects/project-a")
    FilesystemWikiVault(root, "project-a").commit({"AGENTS.md": build_default_agents_rules("project-a")})
    try:
        source = repo.create_source(SourceRecord(
            id="horizon-pending",
            project_id="project-a",
            source_type="horizon_signal",
            content_hash="a" * 64,
            raw_content="Unreviewed discovery signal must not become plan context.",
            trust_level="reviewed",
            status=SourceStatus.ELIGIBLE,
            metadata={"admission_gate": "project_triage"},
        ))

        class Retrieval:
            def retrieve(self, *_args, **_kwargs):
                return [{"source": f"evidence://project-a/{source['id']}"}]

        pack = WikiContextProvider(repo, vault_root=root, retrieval_service=Retrieval()).build_context(
            project_id="project-a", task_constraints=["Analyze the latest research signal."]
        )

        assert pack is not None
        assert pack.source_ids == ()
        assert "Unreviewed discovery signal" not in pack.rendered
        assert source["id"] in pack.retrieval_refs
    finally:
        repo.close()
