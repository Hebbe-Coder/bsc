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
                path="wiki/log.md",
                content="\n- Added approval concept. [source:source-a]\n",
                source_ids=["source-a"],
            ),
        ),
        rules=parse_project_rules(build_default_agents_rules("project-a")),
        source_ids={"source-a"},
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
    assert {"missing_frontmatter", "unknown_source", "dangling_page_link", "missing_index_update", "missing_log_update"} <= codes
