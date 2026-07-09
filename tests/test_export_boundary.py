import io
from docx import Document
from exporters.canonical import normalize
from exporters.boundary import MAX_LIST_ITEMS, MAX_TEXT_LEN
from exporters.html_exporter import generate_html


def test_normalize_huge_list_capped():
    bs = {"objectives": [{"objective": f"o{i}", "priority": "high"} for i in range(500)]}
    r = normalize(bs)
    # 封顶 MAX_LIST_ITEMS 条真实数据 + 1 条"已省略"合成条目
    assert len(r.objectives) == MAX_LIST_ITEMS + 1
    assert any("其余" in o.objective and "已省略" in o.objective for o in r.objectives)


def test_normalize_long_text_truncated():
    bs = {"business_domain": "x" * (MAX_TEXT_LEN + 100)}
    r = normalize(bs)
    assert "已截断" in r.title


def test_normalize_none_field_becomes_placeholder():
    bs = {"roles": [{"role": "CEO", "department": None}]}
    r = normalize(bs)
    assert r.roles[0].department == "—"


def test_normalize_type_error_coerced():
    bs = {"metrics": [{"name": 12345, "formula": "x", "target": "y"}]}
    r = normalize(bs)
    assert r.metrics[0].name == "12345"


def test_normalize_control_chars_stripped():
    bs = {"business_domain": "a" + chr(0) + "b" + chr(31) + "c"}
    r = normalize(bs)
    assert chr(0) not in r.title and chr(31) not in r.title


def test_normalize_bom_stripped():
    bs = {"business_domain": chr(0xFEFF) + "项目"}
    r = normalize(bs)
    assert chr(0xFEFF) not in r.title


def test_normalize_empty_input_safe():
    r = normalize({})
    assert r.title == "业务系统分析报告"
    assert r.objectives == []


def test_html_injection_escaped():
    bs = {"business_domain": "<script>alert(1)</script>",
          "objectives": [{"objective": "<img src=x onerror=alert(1)>", "priority": "high"}]}
    r = normalize(bs)
    html = generate_html(r, {}, None)
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
