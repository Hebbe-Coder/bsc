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
