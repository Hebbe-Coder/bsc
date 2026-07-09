"""导出层依赖与可用性测试。"""
import pytest


def test_export_dependency_error_fields():
    from exporters.errors import ExportDependencyError
    err = ExportDependencyError("word", "python-docx", "pip install python-docx")
    assert err.format == "word"
    assert err.missing_package == "python-docx"
    assert err.pip_install == "pip install python-docx"
    msg = str(err)
    assert "word" in msg
    assert "python-docx" in msg
    assert "pip install python-docx" in msg


def test_capabilities_zero_dep_formats_available():
    from exporters.capabilities import EXPORT_CAPABILITIES, format_available
    for fmt in ("json", "html", "ppt", "markdown"):
        assert EXPORT_CAPABILITIES[fmt]["available"] is True
        assert format_available(fmt) is True


def test_capabilities_probe_reflects_installed_state():
    import importlib.util
    from exporters.capabilities import EXPORT_CAPABILITIES
    expected = importlib.util.find_spec("openpyxl") is not None
    assert EXPORT_CAPABILITIES["xlsx"]["available"] is expected


def test_unavailable_formats_shape():
    from exporters.capabilities import unavailable_formats
    result = unavailable_formats(["json", "html"])
    assert result == []


def test_package_imports_without_pptx(monkeypatch):
    import sys, importlib
    monkeypatch.setitem(sys.modules, "pptx", None)
    for name in [n for n in list(sys.modules) if n == "exporters" or n.startswith("exporters.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    pkg = importlib.import_module("exporters")
    assert callable(getattr(pkg, "export_html"))
    wmod = importlib.import_module("exporters.word_exporter")
    assert hasattr(wmod, "WordExporter")


def test_pptx_exporter_missing_dep_raises_structured(monkeypatch):
    import sys, importlib
    monkeypatch.setitem(sys.modules, "pptx", None)
    for name in [n for n in list(sys.modules) if n == "exporters" or n.startswith("exporters.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    mod = importlib.import_module("exporters.ppt_exporter")
    from exporters.errors import ExportDependencyError
    with pytest.raises(ExportDependencyError) as ei:
        mod.PPTExporter()
    assert ei.value.missing_package == "python-pptx"


def test_word_exporter_missing_dep_raises_structured(monkeypatch):
    import sys
    from exporters.errors import ExportDependencyError
    monkeypatch.setitem(sys.modules, "docx", None)
    from exporters.word_exporter import WordExporter
    exp = WordExporter()
    with pytest.raises(ExportDependencyError) as ei:
        exp.export({})
    assert ei.value.missing_package == "python-docx"
    assert "pip install python-docx" in ei.value.pip_install


def test_apiresponse_partial():
    from app.api.response import ApiResponse
    resp = ApiResponse.partial(
        data={"exports": {}}, message="部分格式失败",
        errors=[{"format": "word", "missing_package": "python-docx"}],
    )
    assert resp.success is False
    assert resp.code == 207
    assert resp.message == "部分格式失败"
    assert resp.errors and resp.errors[0]["format"] == "word"


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_capabilities_endpoint():
    resp = _client().get("/bsc/exports/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    caps = body["data"]["capabilities"] if "data" in body else body["capabilities"]
    assert caps["json"]["available"] is True
    assert "word" in caps


def test_export_dep_missing_zero_produced_returns_422(monkeypatch):
    import exporters.orchestrator as orchestrator
    from exporters.errors import ExportDependencyError

    def fake(fmt, bs, canonical, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise RuntimeError("no")
    monkeypatch.setattr(orchestrator, "_produce", fake)
    resp = _client().post("/bsc/export", json={
        "business_system": {"business_domain": "x"},
        "output_types": ["word"],
    })
    body = resp.json()
    # 依赖缺失不再硬 422 门禁，而是走降级；此处 word 及其候补均失败 → 零产出 → 422
    assert body["code"] == 422
    st = body["data"]["formats_status"][0]
    assert st["status"] == "dropped"
    assert st["reason"] == "dependency_missing"
    assert st["missing_package"] == "python-docx"
