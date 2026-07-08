"""
真实 LLM 端到端 happy-path 冒烟测试
====================================

固化「真实 LLM（deepseek/doubao）→ business_system JSON → 6 种报告格式」这条链路。

默认 **跳过**：本测试会调用真实付费 API（deepseek + doubao），因此不会在普通
`pytest` 运行中自动执行。当且仅当以下条件同时满足时才运行：

  1. 环境变量 BSC_REAL_E2E 为真（如 BSC_REAL_E2E=1）
  2. DEEPSEEK_API_KEY 已配置且不是占位符
  3. DOUBAO_API_KEY 已配置且不是占位符

本地 .env 中 DOUBAO_API_KEY 目前是占位符，因此该测试会跳过；当补齐真实
doubao key 并设 BSC_REAL_E2E=1 后，可一键验证整条链路。

运行方式：
    BSC_REAL_E2E=1 pytest tests/test_real_e2e.py -v
"""
import os
import sys
import tempfile

import pytest

# 确保项目根目录在 sys.path 中（exporters 包位于项目根）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.core.config import settings  # noqa: E402

PLACEHOLDER_VALUES = {"", "your_doubao_api_key_here", "your_deepseek_api_key_here", "sk-your-key-here"}


def _real_key(value: str) -> bool:
    return bool(value) and value.strip() not in PLACEHOLDER_VALUES


_RUN_REAL = (
    os.environ.get("BSC_REAL_E2E", "").strip() in {"1", "true", "yes", "on"}
    and _real_key(settings.DEEPSEEK_API_KEY)
    and _real_key(settings.DOUBAO_API_KEY)
)

skip_reason = (
    "需要 BSC_REAL_E2E=1 且 DEEPSEEK_API_KEY / DOUBAO_API_KEY 均为真实 key（当前跳过）"
)
pytestmark = pytest.mark.skipif(not _RUN_REAL, reason=skip_reason)


PRD = (
    "# Online Education Platform PRD\n"
    "Objective: deliver interactive courses to university students. "
    "The tutor grades student assignments. Students enroll and submit homework. "
    "Target 85% course completion. Low engagement is a major risk."
)


def test_real_llm_compile_structure():
    """真实 LLM 编译出的 business_system 应具备核心字段。"""
    from app.core.bsc_pipeline import compile_to_business_system

    result = compile_to_business_system(PRD)
    bs = result["business_system"]

    assert isinstance(bs, dict)
    assert bs.get("business_domain"), "business_domain 不应为空"
    assert len(bs.get("objectives", [])) >= 1, "objectives 不应为空"
    assert len(bs.get("workflow", [])) >= 1, "workflow 不应为空"
    assert len(bs.get("risks", [])) >= 1, "risks 不应为空"

    # 真实 LLM 应产出与 PRD 领域相关（在线教育）的内容，而非 mock 占位
    assert "教育" in bs.get("business_domain", "") or "education" in bs.get("business_domain", "").lower()


def test_real_llm_export_six_formats():
    """真实 LLM business_system → 6 种报告格式，全部非空。"""
    from app.core.bsc_pipeline import compile_to_business_system
    from exporters import export_html, export_xlsx, export_impeccable
    from exporters.markdown_exporter import MarkdownExporter
    from exporters.word_exporter import WordExporter
    from exporters.pdf_exporter import PDFExporter

    bs = compile_to_business_system(PRD)["business_system"]

    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "report.html")
        xlsx_path = os.path.join(tmp, "report.xlsx")
        ppt_path = os.path.join(tmp, "report.pptx")
        md_path = os.path.join(tmp, "report.md")
        docx_path = os.path.join(tmp, "report.docx")
        pdf_path = os.path.join(tmp, "report.pdf")

        export_html(bs, html_path)
        export_xlsx(bs, xlsx_path)
        export_impeccable(bs, ppt_path)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(MarkdownExporter().export(bs))
        with open(docx_path, "wb") as f:
            f.write(WordExporter().export(bs))
        with open(pdf_path, "wb") as f:
            f.write(PDFExporter().export(bs))

        for label, path in [
            ("HTML", html_path),
            ("XLSX", xlsx_path),
            ("PPT", ppt_path),
            ("MD", md_path),
            ("Word", docx_path),
            ("PDF", pdf_path),
        ]:
            assert os.path.exists(path), f"{label} 文件未生成"
            assert os.path.getsize(path) > 0, f"{label} 文件为空"
