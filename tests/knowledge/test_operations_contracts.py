from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.knowledge.operations_contracts import (
    OperationalAction,
    OperationsFreshness,
    OperationsInterval,
    OperationsMetricState,
    OperationsProjectMetrics,
    OperationsProjectSummary,
    OperationsScope,
)


def test_operations_scope_is_tenant_bound_and_deduplicates_project_ids():
    scope = OperationsScope(
        tenant_id="tenant-a",
        role="admin",
        project_ids=["project-b", "project-a", "project-a"],
    )

    assert scope.project_ids == ("project-a", "project-b")
    assert scope.is_portfolio is True


def test_operations_scope_rejects_an_invalid_selected_project():
    with pytest.raises(ValidationError, match="selected project"):
        OperationsScope(
            tenant_id="tenant-a",
            role="project_reader",
            project_ids=["project-a"],
            selected_project_id="project-b",
        )


def test_operational_action_is_metadata_only_and_has_a_stable_sort_key():
    action = OperationalAction(
        id="risk-1",
        project_id="project-a",
        kind="unresolved_risk",
        severity="critical",
        source_refs=["artifact-risk-1"],
        recommendation="Review mitigation before execution.",
        created_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        drilldown={"surface": "dbos", "entity_id": "artifact-risk-1"},
    )

    assert action.sort_key[:2] == (0, 0)
    with pytest.raises(ValidationError):
        OperationalAction(
            **action.model_dump(),
            raw_content="must never enter an operations projection",
        )


def test_project_summary_is_metadata_only_and_requires_explicit_freshness_state():
    action = OperationalAction(
        id="action-risk-1",
        project_id="project-a",
        kind="unresolved_risk",
        severity="high",
        source_refs=["artifact:risk-1"],
        recommendation="Review the durable risk record.",
        created_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        drilldown={"surface": "dbos", "entity_id": "risk-1", "mission_id": "mission-1"},
    )
    summary = OperationsProjectSummary(
        project_id="project-a",
        project_name="Project A",
        coverage={"state": "available", "record_count": 4},
        freshness=OperationsFreshness(
            state=OperationsMetricState.AVAILABLE,
            latest_activity_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            record_count=4,
        ),
        metrics=OperationsProjectMetrics(
            asset_count={"key": "asset_count", "state": "available", "value": 4},
            verified={"key": "verified", "state": "available", "value": 2},
            pending_validation={"key": "pending_validation", "state": "available", "value": 1},
            risk_debt={"key": "risk_debt", "state": "available", "value": 1},
            durable_references={"key": "durable_references", "state": "available", "value": 1},
        ),
        highest_priority_action=action,
    )

    assert summary.highest_priority_action is action
    with pytest.raises(ValidationError):
        OperationsProjectSummary(**summary.model_dump(), raw_source_body="must never enter the portfolio")


def test_interval_requires_an_ordered_utc_range():
    with pytest.raises(ValidationError, match="before"):
        OperationsInterval(
            start_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        )

    assert OperationsMetricState.INSUFFICIENT_SAMPLE.value == "insufficient_sample"
