import pytest
from pydantic import ValidationError

from app.knowledge.wiki_contracts import (
    ProposalStatus,
    SourceRecord,
    SourceStatus,
    WikiOperation,
    WikiProposal,
    WikiOperationType,
    can_transition_source,
)


def test_wiki_operation_rejects_paths_outside_project_vault():
    with pytest.raises(ValidationError):
        WikiOperation(
            operation=WikiOperationType.CREATE,
            path="../wiki/escape.md",
            content="# invalid",
            source_ids=["src-1"],
        )

    with pytest.raises(ValidationError):
        WikiOperation(
            operation=WikiOperationType.CREATE,
            path="C:/outside.md",
            content="# invalid",
            source_ids=["src-1"],
        )


def test_proposal_requires_operations_and_source_provenance():
    with pytest.raises(ValidationError):
        WikiProposal(project_id="project-a", source_ids=["src-1"], operations=[])

    with pytest.raises(ValidationError):
        WikiProposal(
            project_id="project-a",
            operations=[
                WikiOperation(
                    operation=WikiOperationType.CREATE,
                    path="wiki/concepts/test.md",
                    content="# Test",
                )
            ],
        )


def test_source_status_transitions_are_explicit():
    assert can_transition_source(SourceStatus.CAPTURED, SourceStatus.VALIDATED)
    assert can_transition_source(SourceStatus.VALIDATED, SourceStatus.ELIGIBLE)
    assert not can_transition_source(SourceStatus.PROCESSED, SourceStatus.ELIGIBLE)

    source = SourceRecord(
        id="src-1",
        project_id="project-a",
        source_type="obsidian_file",
        origin="notes/customer.md",
        content_hash="a" * 64,
        raw_content="Immutable customer note",
    )

    assert source.status is SourceStatus.CAPTURED
    assert ProposalStatus.DRAFT.value == "draft"
