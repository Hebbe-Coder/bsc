# tests/orchestrator/test_schemas.py
import pytest
from app.orchestrator.schemas import validate_segment, ValidationError


def test_validate_business_model_ok():
    data = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    assert validate_segment("business_model", data).flows[0].id == "f1"


def test_validate_business_model_missing_required():
    with pytest.raises(ValidationError):
        validate_segment("business_model", {"flows": []})  # 缺 roles/rules


def test_validate_review_loopback():
    data = {"approved": False, "gaps": [{"severity": "high", "type": "sla",
            "desc": "缺 SLA", "suggested_fix": "加 SLA", "target": "sop"}],
            "loopback_target": "sop", "summary": "需补 SLA"}
    out = validate_segment("review", data)
    assert out.loopback_target == "sop"
