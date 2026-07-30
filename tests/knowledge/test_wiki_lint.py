import hashlib

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


def test_lint_allows_a_replacement_without_overview_churn_when_navigation_already_exists():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.REPLACE,
                path="wiki/concepts/approval.md",
                content="---\ntitle: Approval\nkind: concept\n---\nApproval remains required. [source:source-a]",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/index.md",
                content="\n- [[wiki/concepts/approval.md]] revised\n",
                source_ids=["source-a"],
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Revised approval concept. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
        existing_paths={"wiki/concepts/approval.md", "wiki/index.md", "wiki/overview.md", "wiki/log.md"},
        existing_contents={"wiki/overview.md": "# Overview\n- [[wiki/concepts/approval.md]]\n"},
    )

    assert report.findings == ()


def test_lint_allows_an_uncited_overview_audit_append_for_archive_only_repairs():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.ARCHIVE,
                path="wiki/concepts/unrecoverable.md",
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/index.md",
                content="\n- Removed an unrecoverable page.\n",
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/overview.md",
                content="\n- Governance repair removed an unrecoverable page.\n",
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Removed an unrecoverable page from the published Wiki.\n",
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids=set(),
        existing_paths={"wiki/concepts/unrecoverable.md", "wiki/index.md", "wiki/overview.md", "wiki/log.md"},
    )

    assert report.findings == ()


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


def test_lint_allows_a_versioned_complete_agents_rules_replacement_with_audit_log():
    current_rules = build_default_agents_rules("project-a")
    next_rules = current_rules.replace(
        "Write concise, factual, audience-appropriate material.",
        "Write concise, factual, audience-appropriate material for the project audience.",
    )
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.REPLACE,
                path="AGENTS.md",
                content=next_rules,
                expected_content_hash=hashlib.sha256(current_rules.encode("utf-8")).hexdigest(),
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Updated project rules. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(current_rules),
        source_ids={"source-a"},
        existing_paths={"AGENTS.md", "wiki/log.md"},
    )

    assert report.findings == ()


def test_lint_rejects_unversioned_or_partial_agents_rules_edits():
    report = WikiLint().lint_proposal(
        _proposal(
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="AGENTS.md",
                content="\n## Unreviewed change\n",
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Attempted rules update. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
        existing_paths={"AGENTS.md", "wiki/log.md"},
    )

    codes = {finding.code for finding in report.findings}
    assert {"agents_not_replace", "agents_missing_revision", "invalid_agents_rules"} <= codes


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
    assert {"orphan_page", "stale_page", "missing_source_citation", "invalid_publication_status"} <= codes
    assert all(finding.remediation for finding in report.findings)
