from app.orchestrator.schemas import validate_segment, RiskModel


def test_validate_risk_segment():
    data = {
        "overall_score": "low",
        "risks": [{"id": "rk1", "category": "compliance", "description": "x",
                   "likelihood": "low", "impact": "low", "mitigation": "y",
                   "owner_role": "法务"}],
        "coverage": {"total": 1, "covered": 1, "coverage_pct": 100, "uncovered_ids": []},
        "gate": {"decision": "pass", "reasons": []},
        "audit": [{"seq": 0, "agent": "risk", "action": "coverage",
                   "input_hash": "i", "output_hash": "o", "hash": "h",
                   "prev_hash": "0" * 64}],
    }
    m = validate_segment("risk", data)
    assert isinstance(m, RiskModel)
    assert m.gate.decision == "pass"
    assert m.coverage.coverage_pct == 100


def test_risk_segment_preserves_element_coverage():
    # 经 RiskModel 校验后，per-element 覆盖明细不应被丢弃
    data = {
        "overall_score": "low",
        "coverage": {
            "total": 1, "covered": 0, "coverage_pct": 0, "uncovered_ids": ["r1"],
            "elements": [
                {"element_type": "flow", "element_id": "f1", "element_name": "受理",
                 "governed_by": [], "covered": False},
            ],
        },
        "gate": {"decision": "warn", "reasons": ["1 个约束未被任何业务元素满足"]},
        "audit": [],
    }
    m = validate_segment("risk", data)
    assert len(m.coverage.elements) == 1
    assert m.coverage.elements[0].element_id == "f1"
    assert m.coverage.elements[0].covered is False
