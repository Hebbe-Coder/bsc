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
from exporters.html_exporter import generate_html
from exporters.ppt_spec_exporter import generate_ppt_spec
from exporters.markdown_exporter import MarkdownExporter


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


def _bs_with(metrics):
    return {
        "business_domain": "D",
        "report": {"executive_summary": "S"},
        "objectives": [{"objective": "O", "target": "T", "priority": "high"}],
        "workflow": [{"step": 1, "name": "N", "action": "A"}],
        "metrics": metrics,
        "risks": [{"risk": "R", "severity": "high", "mitigation": "M"}],
    }


def test_generate_html_basic():
    html = generate_html(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]), {})
    assert "<html>" in html and "业务目标" in html and "<table>" in html


def test_generate_html_skips_failing_component():
    ctx = DegradeContext()
    from exporters.canonical import normalize
    report = normalize(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    report.metrics = [{"no_name": 1}]  # 渲染时 m.name 抛错，区块被跳过
    html = generate_html(report, {}, ctx)
    assert "<html>" in html
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "metrics"


def test_generate_ppt_spec_basic():
    spec = generate_ppt_spec(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    assert "slides" in spec and spec["slide_count"] >= 1


def test_generate_ppt_spec_skips_failing_component():
    ctx = DegradeContext()
    from exporters.canonical import normalize
    report = normalize(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    report.metrics = [{"no_name": 1}]  # 渲染时 m.name 抛错，区块被跳过
    spec = generate_ppt_spec(report, ctx)
    assert "slides" in spec
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "metrics"


def test_markdown_skips_failing_component():
    ctx = DegradeContext()
    from exporters.canonical import normalize
    report = normalize(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    report.objectives = [{"objective": "x"}]  # 缺 priority_label → 渲染抛错被跳过
    md = MarkdownExporter().export(report, ctx)
    assert md.startswith("# ")
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "objectives"


def test_markdown_without_ctx_unchanged():
    bs = _bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}])
    md = MarkdownExporter().export(bs)  # 无 ctx 行为不变
    assert md.startswith("# ")
    assert "业务目标" in md


import exporters.orchestrator as orchestrator
from exporters.orchestrator import run_export, ExportOutcome
from exporters.errors import ExportDependencyError


def _bs():
    return {"business_domain": "D", "report": {"executive_summary": "S"}}


def test_run_export_substitutes_pptx_to_ppt(monkeypatch):
    def fake_produce(fmt, bs, canonical, result, ctx):
        if fmt == "pptx":
            raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx")
        if fmt == "ppt":
            return {"slides": []}
        raise AssertionError("unexpected fmt " + fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["pptx"], {})
    assert out.formats_status[0] == {"format": "pptx", "status": "substituted", "source_format": "ppt"}
    assert "ppt" in out.exports


def test_run_export_drops_unimplemented(monkeypatch):
    def fake_produce(fmt, bs, canonical, result, ctx):
        raise AssertionError("xlsx 不应进入 _produce")
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["xlsx"], {})
    st = out.formats_status[0]
    assert st["status"] == "dropped"
    assert st["reason"] == "unimplemented"


def test_run_export_drops_dependency_missing(monkeypatch):
    def fake_produce(fmt, bs, canonical, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["word"], {})
    st = out.formats_status[0]
    assert st["status"] == "dropped"
    assert st["reason"] == "dependency_missing"
    assert st["missing_package"] == "python-docx"


def test_run_export_component_failures_attached(monkeypatch):
    def fake_produce(fmt, bs, canonical, result, ctx):
        with ctx.component("metrics"):
            raise ValueError("bad metric")
        return f"content-{fmt}"
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["html"], {})
    st = out.formats_status[0]
    assert st["status"] == "produced"
    assert st["components_degraded"][0]["type"] == "component_failed"
    assert st["components_degraded"][0]["component"] == "metrics"


def test_run_export_zero_produced_all_dropped(monkeypatch):
    def fake_produce(fmt, bs, canonical, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise RuntimeError("no")
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["word"], {})
    assert all(s["status"] == "dropped" for s in out.formats_status)
    assert "word" not in out.exports


from fastapi.testclient import TestClient
import exporters.orchestrator as orchestrator_mod


def _client():
    from app.main import app
    return TestClient(app)


_FAKE_BS = {"business_domain": "D", "report": {"executive_summary": "S"}}


def _req(output_types, bs=None):
    body = {"output_types": output_types}
    if bs is not None:
        body["business_system"] = bs
    else:
        body["input"] = "# PRD\n业务目标：提升内容安全准确率到 99%。"
    return body


def test_export_pptx_substituted_to_ppt(monkeypatch):
    def fake(fmt, bs, canonical, result, ctx):
        if fmt == "pptx":
            raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx")
        if fmt == "ppt":
            return {"slides": []}
        if fmt == "html":
            return "<html></html>"
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator_mod, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["pptx", "html"], bs=_FAKE_BS))
    assert r.json()["code"] == 207, r.text
    data = r.json()["data"]
    by_fmt = {s["format"]: s for s in data["formats_status"]}
    assert by_fmt["pptx"]["status"] == "substituted"
    assert by_fmt["pptx"]["source_format"] == "ppt"
    assert by_fmt["html"]["status"] == "produced"


def test_export_word_dep_missing_substituted_to_html(monkeypatch):
    def fake(fmt, bs, canonical, result, ctx):
        if fmt in ("word", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        if fmt == "html":
            return "<html></html>"
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator_mod, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["word"], bs=_FAKE_BS))
    assert r.json()["code"] == 207, r.text
    st = r.json()["data"]["formats_status"][0]
    assert st["status"] == "substituted" and st["source_format"] == "html"


def test_export_zero_produced_returns_422(monkeypatch):
    def fake(fmt, bs, canonical, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise RuntimeError("no")
    monkeypatch.setattr(orchestrator_mod, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["word"], bs=_FAKE_BS))
    assert r.json()["code"] == 422, r.text
    assert r.json()["data"]["formats_status"][0]["status"] == "dropped"


def test_export_unknown_format_400():
    r = _client().post("/bsc/export", json=_req(["zzz"], bs=_FAKE_BS))
    assert r.json()["code"] == 400, r.text


def test_export_component_degraded_reported(monkeypatch):
    orig = orchestrator_mod._produce

    def fake(fmt, bs, canonical, result, ctx):
        if fmt == "html":
            with ctx.component("metrics"):
                raise ValueError("bad metric")
            return "<html></html>"
        return orig(fmt, bs, canonical, result, ctx)
    monkeypatch.setattr(orchestrator_mod, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["html"], bs=_FAKE_BS))
    assert r.json()["code"] == 207, r.text
    st = r.json()["data"]["formats_status"][0]
    assert st["status"] == "produced"
    assert st["components_degraded"][0]["component"] == "metrics"
