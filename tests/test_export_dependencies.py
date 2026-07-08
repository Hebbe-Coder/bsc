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
