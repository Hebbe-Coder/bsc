import pytest

from app.knowledge.wiki_rules import (
    REQUIRED_RULE_SECTIONS,
    RuleValidationError,
    build_default_agents_rules,
    parse_project_rules,
)


def test_default_agents_rules_are_complete_and_stably_revisioned():
    text = build_default_agents_rules("project-a")

    first = parse_project_rules(text)
    second = parse_project_rules(text)

    assert set(REQUIRED_RULE_SECTIONS).issubset(first.sections)
    assert first.project_id == "project-a"
    assert first.allowed_page_kinds == ("concept", "decision", "brief", "sop", "index")
    assert first.revision == second.revision


def test_rules_keep_user_text_and_reject_missing_required_sections():
    text = build_default_agents_rules("project-a") + "\n## User Notes\nKeep this wording intact.\n"
    parsed = parse_project_rules(text)

    assert "Keep this wording intact." in parsed.body

    broken = text.replace("## Citation Convention", "## Citation Style")
    with pytest.raises(RuleValidationError, match="Citation Convention"):
        parse_project_rules(broken)


def test_rules_reject_invalid_page_kind_policy_and_forbidden_write_path():
    invalid_kinds = build_default_agents_rules("project-a").replace(
        "page_kinds: [concept, decision, brief, sop, index]",
        "page_kinds: [concept, ../escape]",
    )
    with pytest.raises(RuleValidationError, match="page_kinds"):
        parse_project_rules(invalid_kinds)

    invalid_path = build_default_agents_rules("project-a").replace(
        "write_root: wiki/",
        "write_root: raw/",
    )
    with pytest.raises(RuleValidationError, match="write_root"):
        parse_project_rules(invalid_path)


def test_rules_accept_windows_crlf_without_changing_their_revision_identity():
    windows_text = build_default_agents_rules("project-a").replace("\n", "\r\n")

    parsed = parse_project_rules(windows_text)

    assert parsed.project_id == "project-a"
    assert set(REQUIRED_RULE_SECTIONS).issubset(parsed.sections)
    assert parsed.revision != parse_project_rules(build_default_agents_rules("project-a")).revision
