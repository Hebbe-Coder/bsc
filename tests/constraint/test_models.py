from app.constraint.models import (Constraint, ElementCoverage, CoverageReport,
                                    AuditEntry, GateDecision, RiskItem, ConstraintResult)


def test_constraint_result_defaults():
    r = ConstraintResult()
    assert r.overall_score == "medium"
    assert r.coverage.coverage_pct == 0
    assert r.gate.decision == "pass"
    assert r.audit == []


def test_element_coverage_flag():
    ec = ElementCoverage(element_type="flow", element_id="f1", element_name="受理",
                         governed_by=["r1"], covered=True)
    assert ec.covered is True


def test_audit_entry_fields():
    a = AuditEntry(seq=0, agent="x", action="y", input_hash="i", output_hash="o",
                   hash="h", prev_hash="p")
    assert a.seq == 0 and a.hash == "h"
