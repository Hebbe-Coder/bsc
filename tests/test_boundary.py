from exporters.boundary import (
    MAX_TEXT_LEN, MAX_LIST_ITEMS, coerce_str, strip_control,
    truncate_text, cap_list, normalize_text, escape_html,
)


def test_coerce_str_none_becomes_placeholder():
    assert coerce_str(None) == "—"


def test_coerce_str_int_becomes_str():
    assert coerce_str(123) == "123"


def test_coerce_str_bytes_decoded():
    assert coerce_str(b"hello") == "hello"


def test_strip_control_removes_invisible():
    s = "a" + chr(0) + "b" + chr(13) + "c" + chr(31) + "d" + chr(9) + "ez"
    # chr(0) \r chr(31) 删除；\t(chr(9)) 保留 → a b c d \t e z
    assert strip_control(s) == "abcd" + chr(9) + "ez"


def test_strip_control_removes_bom():
    assert strip_control(chr(0xFEFF) + "x") == "x"


def test_truncate_text_short_unchanged():
    assert truncate_text("hello") == "hello"


def test_truncate_text_long_gets_marker():
    long = "x" * (MAX_TEXT_LEN + 50)
    out = truncate_text(long)
    assert out.startswith("x" * MAX_TEXT_LEN)
    assert "已截断" in out
    assert "已截断，原文" in out


def test_truncate_text_none_coerced():
    assert truncate_text(None) == "—"


def test_cap_list_under_limit_unchanged():
    items = list(range(10))
    capped, omitted = cap_list(items)
    assert capped == items and omitted == 0


def test_cap_list_over_limit_capped_with_count():
    items = list(range(MAX_LIST_ITEMS + 25))
    capped, omitted = cap_list(items)
    assert len(capped) == MAX_LIST_ITEMS
    assert omitted == 25


def test_normalize_text_decodes_bytes_and_strips():
    assert normalize_text(b"\x00abc") == "abc"


def test_escape_html_quotes_angle_brackets():
    out = escape_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_escape_html_preserves_text():
    assert escape_html("正常 文本") == "正常 文本"
