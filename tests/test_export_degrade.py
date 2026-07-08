import pytest
from exporters.degrade import (
    DEGRADATION_RULES,
    IMPLEMENTED_FORMATS,
    VALID_OUTPUT_TYPES,
    is_implemented,
    classify_failure,
)
from exporters.errors import ExportDependencyError
from exporters._degrade_ctx import DegradeContext


def test_degradation_rules_present():
    assert DEGRADATION_RULES["pptx"] == ["ppt", "html", "markdown"]
    assert DEGRADATION_RULES["word"] == ["html", "markdown"]
    assert DEGRADATION_RULES["pdf"] == ["html", "markdown"]
    assert DEGRADATION_RULES["xlsx"] == []          # 默认 unimplemented
    assert DEGRADATION_RULES["ppt"] == []
    assert DEGRADATION_RULES["json"] == []


def test_is_implemented():
    assert is_implemented("html") is True
    assert is_implemented("word") is True
    assert is_implemented("visuals") is True
    assert is_implemented("pptx") is False          # 可请求但需降级
    assert is_implemented("xlsx") is False


def test_valid_output_types_includes_degradable():
    assert "pptx" in VALID_OUTPUT_TYPES
    assert "xlsx" in VALID_OUTPUT_TYPES
    assert "html" in VALID_OUTPUT_TYPES
    assert "zzz" not in VALID_OUTPUT_TYPES


def test_classify_dependency_missing():
    err = ExportDependencyError("word", "python-docx", "pip install python-docx")
    r = classify_failure("word", err)
    assert r["type"] == "dependency_missing"
    assert r["missing_package"] == "python-docx"
    assert r["pip_install"] == "pip install python-docx"


def test_classify_runtime_error():
    r = classify_failure("html", ValueError("boom"))
    assert r["type"] == "runtime_error"
    assert r["message"] == "boom"


def test_component_failure_is_captured_not_raised():
    ctx = DegradeContext()
    with ctx.component("chart"):
        raise ValueError("chart broke")
    assert ctx.component_failures == [
        {"type": "component_failed", "component": "chart", "message": "chart broke"}
    ]


def test_component_success_no_failure():
    ctx = DegradeContext()
    with ctx.component("table"):
        pass
    assert ctx.component_failures == []
