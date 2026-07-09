"""跨格式一致性：归一化层 + 四渲染器一致性测试。"""
import pytest

from exporters.canonical import normalize, CanonicalReport


RAW_CANONICAL = {
    "business_domain": "内容安全平台",
    "generated_at": "2026-07-09",
    "report": {"executive_summary": "保障内容安全。"},
    "objectives": [{"objective": "内容安全", "target": "99%准确率", "priority": "high"}],
    "roles": [{"role": "审核员", "department": "运营", "level": "L2", "headcount": 10}],
    "workflow": [{"step": 1, "name": "接入", "action": "接收内容", "role": "网关"}],
    "metrics": [{"name": "准确率", "formula": "tp/(tp+fp)", "target": "99%"}],
    "risks": [{"risk": "误杀", "severity": "high", "mitigation": "人工复核", "impact": "体验"}],
    "strategy": {
        "recommendations": ["引入大模型"],
        "growth_opportunities": [{"opportunity": "出海", "potential": "高"}],
        "strategic_path": ["试点", "推广"],
    },
}


def test_normalize_basic_fields():
    r = normalize(RAW_CANONICAL)
    assert isinstance(r, CanonicalReport)
    assert r.title == "内容安全平台"
    assert r.executive_summary == "保障内容安全。"
    assert len(r.objectives) == 1
    assert len(r.roles) == 1
    assert len(r.workflow) == 1
    assert len(r.metrics) == 1
    assert len(r.risks) == 1
    assert r.strategy.recommendations == ["引入大模型"]
    assert r.strategy.growth_opportunities == [{"opportunity": "出海", "potential": "高"}]
    assert r.strategy.roadmap == ["试点", "推广"]


def test_normalize_field_aliases():
    legacy = {
        "business_domain": "X",
        "kpi": [{"name": "a", "formula": "f", "target": "t"}],
        "process_flow": [{"step": 1, "name": "s"}],
        "risk": [{"risk": "r", "level": "high"}],
    }
    r = normalize(legacy)
    assert len(r.metrics) == 1 and r.metrics[0].name == "a"
    assert len(r.workflow) == 1 and r.workflow[0].name == "s"
    assert len(r.risks) == 1 and r.risks[0].severity == "high"


def test_normalize_severity_variants():
    for raw in ["high", "高", "🔴", {"severity": "high"}, {"level": "high"}]:
        sev_src = raw if isinstance(raw, dict) else {"severity": raw}
        r = normalize({"risks": [{"risk": "x", **sev_src}]})
        assert r.risks[0].severity == "high", f"raw={raw}"
        assert r.risks[0].severity_label == "🔴 高风险"


def test_normalize_missing_section_safe():
    r = normalize({"business_domain": "X"})
    assert r.objectives == [] and r.risks == [] and r.metrics == []
    assert r.strategy.recommendations == []
