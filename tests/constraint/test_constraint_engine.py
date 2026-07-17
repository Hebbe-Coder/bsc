from app.constraint.engine import evaluate


def test_full_coverage_passes():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [{"id": "r1", "name": "审核员"}],
          "rules": [{"id": "ru1", "statement": "审核员必须复核"}]}
    reqs = [{"id": "r1", "text": "审核员负责受理", "priority": "high"},
            {"id": "ru1", "text": "复核规则", "priority": "mid"}]
    res = evaluate(bm, sop={"sops": []}, requirements=reqs)
    assert res.coverage.coverage_pct == 100
    assert res.gate.decision == "pass"
    assert res.audit  # 审计链已写入


def test_uncovered_high_priority_blocks():
    bm = {"flows": [{"id": "f1", "name": "支付"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "支付风控", "priority": "high"}]  # 无元素匹配 r1
    res = evaluate(bm, sop={"sops": []}, requirements=reqs)
    assert res.coverage.coverage_pct < 100
    assert res.gate.decision == "block"
    assert any("高危" in r for r in res.gate.reasons)


def test_sop_covers_constraint():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "受理 SOP", "priority": "mid"}]
    sop = {"sops": [{"id": "s1", "title": "受理", "covers_constraints": ["r1"]}]}
    res = evaluate(bm, sop=sop, requirements=reqs)
    assert res.coverage.coverage_pct == 100


def test_risk_list_propagates_from_payload():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "受理约束", "priority": "mid"}]
    risk_payload = {"overall_score": "high", "risks": [
        {"id": "rk1", "category": "compliance", "description": "缺合规",
         "likelihood": "low", "impact": "medium", "mitigation": "补审计", "owner_role": "法务"}]}
    res = evaluate(bm, sop={"sops": []}, requirements=reqs, risk_payload=risk_payload)
    assert res.overall_score == "high"
    assert res.gate.decision == "block"  # high 风险直接 block
    assert len(res.risks) == 1
    assert res.risks[0].id == "rk1"
