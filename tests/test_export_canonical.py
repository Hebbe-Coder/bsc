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


def test_markdown_consumes_canonical_and_includes_metrics():
    from exporters.markdown_exporter import MarkdownExporter
    r = normalize(RAW_CANONICAL)
    md = MarkdownExporter().export(r, None)
    assert "## 一、业务目标" in md
    assert "## 二、角色定义" in md
    assert "## 三、业务流程" in md
    assert "## 四、关键指标" in md          # 之前缺失，现在必须出现
    assert "## 五、风险分析" in md
    assert "## 六、战略建议" in md
    assert "🔴 高风险" in md                  # 规范标签，字节级统一
    assert "准确率" in md                     # metrics 内容


def test_html_consumes_canonical_and_uniform_labels():
    from exporters.html_exporter import generate_html
    r = normalize(RAW_CANONICAL)
    html = generate_html(r, {}, None)
    assert "内容安全平台" in html
    for marker in ["业务目标", "角色定义", "业务流程", "关键指标", "风险分析", "战略建议"]:
        assert marker in html, marker
    assert "🔴 高风险" in html
    assert "准确率" in html


def test_ppt_includes_roles_and_uniform_severity():
    from exporters.ppt_spec_exporter import generate_ppt_spec
    r = normalize(RAW_CANONICAL)
    spec = generate_ppt_spec(r, None)
    titles = [s["title"] for s in spec["slides"]]
    assert "角色定义" in titles          # 之前缺失
    risk_slide = next(s for s in spec["slides"] if s["title"] == "风险分析")
    assert any("🔴 高风险" in it for it in risk_slide["items"])
