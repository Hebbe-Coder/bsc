from app.knowledge.wiki_contracts import WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules


def _proposal(*operations):
    return WikiProposal(project_id="project-a", source_ids=["source-a"], operations=list(operations))


def test_lint_accepts_cited_pages_with_index_and_append_only_log():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.CREATE,
                path="wiki/concepts/approval.md",
                content="---\ntitle: Approval\nkind: concept\n---\n# Approval\nHuman approval is required. [source:source-a]",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/index.md",
                content="\n- [[wiki/concepts/approval.md]]\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/overview.md",
                content="---\ntitle: Overview\nkind: brief\n---\n- [[wiki/concepts/approval.md]] [source:source-a]\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Added approval concept. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
    )

    assert report.findings == ()


def test_lint_allows_a_frontmatter_free_append_to_an_existing_page():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/overview.md",
                content="\n- Evidence-backed update. [source:source-a]\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/index.md",
                content="\n- Overview updated\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Overview updated. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
        existing_paths={"wiki/overview.md", "wiki/index.md", "wiki/log.md"},
    )

    assert report.valid is True


def test_lint_reports_invalid_metadata_citations_links_and_maintenance_updates():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.CREATE,
                path="wiki/concepts/approval.md",
                content="# Approval\nUnsupported claim [source:missing] and [[wiki/concepts/absent.md]].",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
    )

    codes = {finding.code for finding in report.findings}
    assert {"missing_frontmatter", "unknown_source", "dangling_page_link", "missing_overview_update", "missing_index_update", "missing_log_update"} <= codes


def test_lint_rejects_a_substantive_update_without_an_inline_source_citation():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.CREATE,
                path="wiki/concepts/approval.md",
                content="---\ntitle: Approval\nkind: concept\n---\n\nUnsupported claim.",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/index.md",
                content="\n- [[wiki/concepts/approval.md]]\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/overview.md",
                content="\n- Updated. [source:source-a]\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Updated. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
    )

    assert "missing_source_citation" in {finding.code for finding in report.findings}


def test_project_lint_reports_orphan_stale_and_uncited_pages():
    from datetime import datetime, timezone

    report = WikiLint().lint_project(
        project_id="project-a",
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        pages=[
            {"id": "index", "project_id": "project-a", "path": "wiki/index.md", "content": "# Index\n", "updated_at": "2026-07-21T00:00:00+00:00"},
            {"id": "old", "project_id": "project-a", "path": "wiki/concepts/old.md", "content": "---\ntitle: Old\nkind: concept\n---\nUncited claim.", "updated_at": "2025-01-01T00:00:00+00:00"},
        ],
        sources=[],
        now=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )

    codes = {finding.code for finding in report.findings}
    assert {"orphan_page", "stale_page", "missing_source_citation"} <= codes
    assert all(finding.remediation for finding in report.findings)
