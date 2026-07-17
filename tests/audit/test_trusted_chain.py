"""方案 E 可信审计内核测试：构建、独立验证、防篡改、空态降级。"""
from __future__ import annotations

from app.audit import build_trusted_audit, verify_trusted_audit, collect_source_refs


def _state_with_refs() -> dict:
    return {
        "sop": {
            "sops": [
                {"id": "s1", "source_ref": ["c1", "c2"]},
                {"id": "s2", "source_ref": ["c2", "c3"]},
            ],
            "_citation_coverage": {"coverage": 1.0, "covered": 2, "total": 2, "flagged": []},
        },
        "business_model": {
            "flows": [{"id": "f1", "source_ref": ["c3"]}],
            "roles": [{"id": "r1", "source_ref": []}],
            "rules": [{"id": "ru1", "source_ref": ["c1"]}],
        },
        "risk": {
            "overall_score": "medium",
            "gate": {"decision": "warn", "reasons": ["x"]},
            "coverage": {"total": 3, "covered": 2, "coverage_pct": 67, "uncovered_ids": ["r3"]},
            "risks": [],
        },
    }


def test_collect_source_refs_dedup_ordered():
    refs = collect_source_refs(_state_with_refs())
    assert refs == ["c1", "c2", "c3"]


def test_build_happy_path():
    rec = build_trusted_audit(_state_with_refs())
    assert rec["verified"] is True
    assert rec["source_refs"] == ["c1", "c2", "c3"]
    assert len(rec["audit"]) == 2
    assert isinstance(rec["chain_hash"], str) and len(rec["chain_hash"]) == 64
    assert rec["coverage"]["coverage_pct"] == 67
    assert rec["coverage"]["gate_decision"] == "warn"
    # 独立验证应通过
    assert verify_trusted_audit(rec) is True


def test_verify_fails_on_entry_tamper():
    rec = build_trusted_audit(_state_with_refs())
    # 模拟存储/传输中篡改链节点的 output_hash → 重放哈希不吻合
    rec["audit"][0]["output_hash"] = "deadbeef" * 8
    assert verify_trusted_audit(rec) is False


def test_verify_fails_on_convenience_field_tamper():
    rec = build_trusted_audit(_state_with_refs())
    # 模拟单独篡改展示用便捷字段，而链本身未动
    rec["source_refs"] = ["c1", "c2", "c3", "FAKE"]
    assert verify_trusted_audit(rec) is False


def test_empty_state_graceful():
    rec = build_trusted_audit({})
    assert rec["source_refs"] == []
    assert rec["verified"] is True
    assert rec["coverage"]["coverage_pct"] is None
    assert len(rec["audit"]) == 2
    assert verify_trusted_audit(rec) is True
