# tests/evaluation/test_compiler_evaluator.py
"""编译器产物评测器（方案 C Phase 1）单元测试。

规则维度确定性、无 LLM 依赖；全走 venv 解释器。
"""
from app.evaluation import CompilerOutputEvaluator


def _good_state():
    return {
        "sop": {
            "sops": [{"id": "s1", "title": "步骤一"}],
            "_citation_coverage": {"coverage": 1.0, "covered": 2, "total": 2, "flagged": []},
        },
        "business_model": {
            "flows": [{"id": "f1"}],
            "roles": [{"id": "r1"}],
            "rules": [{"id": "ru1"}],
            "_citation_coverage": {"coverage": 1.0, "covered": 3, "total": 3, "flagged": []},
        },
        "risk": {
            "gate": {"decision": "pass", "reason": "ok"},
            "coverage": {"total": 5, "covered": 5, "coverage_pct": 100, "uncovered_ids": []},
            "risks": [{"id": "k1"}],
        },
    }


def test_full_score_passes():
    ev = CompilerOutputEvaluator()
    # 提供已算好的可信审计（verified=True）
    trusted = {"verified": True, "chain_hash": "abc"}
    rep = ev.evaluate(_good_state(), trusted_audit=trusted)
    assert rep.overall_score == 100
    assert rep.is_passed is True
    assert rep.improvement_points == 0
    names = {d.name for d in rep.dimensions}
    assert names == {"方法论采用度", "约束覆盖率", "风险门禁健康", "审计完整性", "结构完整度"}


def test_missing_fields_degrade_gracefully():
    ev = CompilerOutputEvaluator()
    # 只有审计完整（verified=True），其余维度缺字段 -> 应降级为 0 分，不崩
    state = {
        "sop": {},
        "business_model": {},
        "risk": {},
    }
    rep = ev.evaluate(state, trusted_audit={"verified": True})
    # 仅审计维度 100*0.15 = 15
    assert rep.overall_score == 15
    assert rep.is_passed is False
    assert rep.improvement_points == 4  # 方法论/约束/门禁/结构 均 <60
    # 缺字段的维度 feedback 应标注「未提供」
    by_name = {d.name: d for d in rep.dimensions}
    assert "未提供" in by_name["方法论采用度"].feedback
    assert "未提供" in by_name["约束覆盖率"].feedback
    assert "未提供" in by_name["风险门禁健康"].feedback


def test_empty_state_no_crash():
    ev = CompilerOutputEvaluator()
    # 空 state：build_trusted_audit({}) 链自洽 -> verified=True（审计 100），其余 0
    rep = ev.evaluate({})
    assert rep.overall_score == 15
    assert rep.is_passed is False
    assert "编译器产物综合评分" in rep.summary


def test_audit_tampered_drops_score():
    ev = CompilerOutputEvaluator()
    # 真实构建一条审计链，再把 verified 篡改成 False -> 审计维度应得 0
    trusted = {"verified": False, "chain_hash": "deadbeef"}
    rep = ev.evaluate(_good_state(), trusted_audit=trusted)
    by_name = {d.name: d for d in rep.dimensions}
    assert by_name["审计完整性"].score == 0
    # 总分 = 100*(0.25+0.20+0.20+0) + 100*0.15(审计被改)？审计 0 -> 仅 0.15 没了
    # 实际：方法论100*0.25 + 约束100*0.20 + 门禁100*0.20 + 审计0*0.15 + 结构100*0.20 = 85
    assert rep.overall_score == 85


def test_gate_health_mapping():
    ev = CompilerOutputEvaluator()
    for decision, expect in [("pass", 100), ("warn", 70), ("block", 40)]:
        state = {"risk": {"gate": {"decision": decision}}}
        rep = ev.evaluate(state, trusted_audit={"verified": True})
        by_name = {d.name: d for d in rep.dimensions}
        assert by_name["风险门禁健康"].score == expect


def test_structure_completeness_partial():
    ev = CompilerOutputEvaluator()
    # 仅 SOP 有内容 -> 结构 1/3 -> 33
    state = {"sop": {"sops": [{"id": "s1"}]}}
    rep = ev.evaluate(state, trusted_audit={"verified": True})
    by_name = {d.name: d for d in rep.dimensions}
    assert by_name["结构完整度"].score == 33
