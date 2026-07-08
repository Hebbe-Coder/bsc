"""BSC API - BSC Pipeline 唯一入口"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import html
import os

from app.api.response import ApiResponse

router = APIRouter(prefix="/bsc", tags=["BSC Pipeline"])


class CompileRequest(BaseModel):
    """编译请求模型"""
    input: str = Field(
        ...,
        min_length=10,
        description="PRD文本内容或文件路径",
        json_schema_extra={
            "example": """# 内容审核系统PRD

## 1. 业务目标
- 建立完善的内容审核体系
- 确保平台内容合规性
- 提升审核效率至90%以上

## 2. 核心功能
- 图片审核
- 视频审核
- 文本审核
- 实时监控

## 3. 性能要求
- 单条审核响应时间 < 2秒
- 日均处理量 100万条+
"""
        },
    )
    output_types: List[str] = Field(
        default=["html", "ppt", "json"],
        description="输出格式，可选值: html, ppt, json",
        json_schema_extra={"example": ["html", "json"]},
    )
    template_id: Optional[str] = Field(
        None,
        description="模板ID，可选值: builtin_content_moderation, builtin_ecommerce, builtin_finance等",
        json_schema_extra={"example": "builtin_content_moderation"},
    )


class StageRequest(BaseModel):
    """阶段执行请求模型"""
    input: str = Field(
        ...,
        description="PRD文本内容",
        json_schema_extra={"example": "# PRD内容..."},
    )
    stage_key: str = Field(
        ...,
        description="阶段key，可选值: business_understanding, sop, risk, strategy, optimization, composer",
        json_schema_extra={"example": "business_understanding"},
    )


class ExportRequest(BaseModel):
    """导出请求模型"""
    input: str = Field(
        "",
        description="PRD文本（可选，为空时使用business_system）",
        json_schema_extra={"example": ""},
    )
    output_types: List[str] = Field(
        default=["html", "json"],
        description="输出格式，可选值: json, html, ppt, word, markdown, pdf",
        json_schema_extra={"example": ["json", "word"]},
    )
    business_system: Optional[dict] = Field(
        None,
        description="已编译的业务系统数据（跳过编译直接导出）",
        json_schema_extra={
            "example": {
                "business_domain": "内容安全",
                "objectives": [{"objective": "内容安全", "target": "99%准确率"}],
                "workflow": [{"step": 1, "name": "请求接收"}],
            }
        },
    )


class CompileResponse(BaseModel):
    """编译响应模型"""
    pipeline: Dict[str, Any] = Field(..., description="Pipeline执行信息")
    business_system: Dict[str, Any] = Field(..., description="业务系统数据")
    composed: Dict[str, Any] = Field(..., description="组合结果")
    workspace: Dict[str, Any] = Field(..., description="工作空间数据")
    visuals: List[Dict[str, Any]] = Field(..., description="可视化数据")
    summary: str = Field(..., description="执行摘要")
    output_types: List[str] = Field(..., description="输出格式")
    parallel: bool = Field(default=True, description="是否并行执行")


@router.post(
    "/compile",
    response_model=ApiResponse[CompileResponse],
    summary="BSC Pipeline - 完整流程入口（异步并行模式）",
    description="""将PRD文本编译为完整的业务系统分析报告。默认使用异步并行模式，性能提升约50%。

流程步骤：
1. **Business Understanding** - 业务理解，识别业务领域和核心目标
2. **Planner** - 根据PRD内容动态规划Agent执行链
3. **SOP + Risk + Strategy + Optimization** - 并行执行分析Agent
4. **Business Composer** - 组装最终报告

并行策略：
- Business Understanding → 串行（必须先执行）
- SOP + Risk + Strategy + Optimization → 并行（无依赖）
- Business Composer → 串行（依赖所有分析结果）

示例输入：PRD文档文本
示例输出：包含业务系统、流程设计、风险分析、战略机会、优化建议的完整报告
""",
    response_description="编译成功，返回完整的业务系统分析结果（并行执行）",
)
async def compile_prd(req: CompileRequest):
    """BSC Pipeline - 完整流程入口（异步并行模式，默认）"""
    from app.core.async_pipeline import compile_to_business_system_async

    result = await compile_to_business_system_async(req.input, template_id=req.template_id)
    bs = result["business_system"]

    visuals = []
    if "html" in req.output_types or "json" in req.output_types:
        try:
            from app.engines.visual_binding import bind_visuals
            visual_result = bind_visuals(bs)
            visuals = visual_result.get("visuals", []) if isinstance(visual_result, dict) else visual_result
        except Exception:
            pass

    return ApiResponse.ok({
        "pipeline": result["pipeline"],
        "business_system": bs,
        "composed": bs.get("composed", {}),
        "workspace": result.get("workspace", {}),
        "visuals": visuals,
        "summary": result["summary"],
        "output_types": req.output_types,
        "parallel": result.get("pipeline", {}).get("parallel", True),
    })


@router.post(
    "/compile/sync",
    response_model=ApiResponse[CompileResponse],
    summary="BSC Pipeline - 同步流程入口",
    description="""同步串行执行模式。适用于需要确定性执行顺序或调试场景。

流程步骤：
1. **Business Understanding** - 业务理解，识别业务领域和核心目标
2. **Planner** - 根据PRD内容动态规划Agent执行链
3. **SOP + Risk + Strategy + Optimization** - 按顺序执行分析Agent
4. **Business Composer** - 组装最终报告

注意：同步模式性能低于异步并行模式，建议生产环境使用默认的/compile端点
""",
    response_description="编译成功，返回完整的业务系统分析结果（串行执行）",
)
async def compile_prd_sync(req: CompileRequest):
    """BSC Pipeline - 同步流程入口（串行执行模式）"""
    from app.core.bsc_pipeline import compile_to_business_system

    result = compile_to_business_system(req.input)
    bs = result["business_system"]

    visuals = []
    if "html" in req.output_types or "json" in req.output_types:
        try:
            from app.engines.visual_binding import bind_visuals
            visual_result = bind_visuals(bs)
            visuals = visual_result.get("visuals", []) if isinstance(visual_result, dict) else visual_result
        except Exception:
            pass

    return ApiResponse.ok({
        "pipeline": result["pipeline"],
        "business_system": bs,
        "composed": bs.get("composed", {}),
        "workspace": result.get("workspace", {}),
        "visuals": visuals,
        "summary": result["summary"],
        "output_types": req.output_types,
        "parallel": False,
    })


from app.core.config import settings
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024

_ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt", ".png", ".jpg", ".jpeg"}
_ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
}


@router.post(
    "/compile/files",
    summary="BSC Pipeline - 文件上传入口",
    description="""上传文档文件进行编译。

支持的文件类型：
- .docx - Word文档
- .pdf - PDF文档（支持图片/OCR识别）
- .txt - 纯文本文件
- .png/.jpg/.jpeg - 图片文件（OCR识别）

文件大小限制：{max_size}MB

处理流程：
1. 解析上传的文件内容
2. 图片文件自动进行OCR识别
3. 合并所有内容为PRD文本
4. 调用BSC Pipeline进行编译
""".format(max_size=settings.MAX_FILE_SIZE_MB),
    response_description="编译成功，返回完整的业务系统分析结果",
)
async def compile_files(
    files: List[UploadFile] = File(
        None,
        description="上传的文档文件（支持.docx/.pdf/.txt/.png/.jpg/.jpeg）",
    ),
    text: str = "",
    output_types: List[str] = ["html", "ppt", "json"],
):
    """BSC Pipeline - 完整流程入口（文件上传）"""
    from app.core.bsc_pipeline import compile_to_business_system
    from app.core.document_parser import get_thread_local_parser
    from app.services.llm_service import LLMService

    llm_service = LLMService()
    parser = get_thread_local_parser(llm_service)

    prd_content = text.strip()
    parsed_files = []
    errors = []

    if files and len(files) > 0:
        try:
            file_list = []
            for file in files:
                ext = os.path.splitext(file.filename)[1].lower()
                if ext not in _ALLOWED_EXTENSIONS:
                    errors.append(f"文件 {file.filename} 类型不支持，仅支持: {', '.join(_ALLOWED_EXTENSIONS)}")
                    continue
                
                content_type = file.content_type
                if content_type and content_type not in _ALLOWED_MIME_TYPES:
                    errors.append(f"文件 {file.filename} MIME类型不匹配: {content_type}")
                    continue
                
                if file.size is not None and file.size > MAX_FILE_SIZE:
                    errors.append(f"文件 {file.filename} 超过大小限制({MAX_FILE_SIZE//1024//1024}MB)")
                    continue
                file_bytes = await file.read()
                if len(file_bytes) > MAX_FILE_SIZE:
                    errors.append(f"文件 {file.filename} 超过大小限制({MAX_FILE_SIZE//1024//1024}MB)")
                    continue
                file_list.append({"bytes": file_bytes, "filename": file.filename})

            parse_result = parser.parse_multiple(file_list)
            parsed_files = parse_result["files"]
            errors = parse_result["errors"]

            if parse_result["combined_text"]:
                if prd_content:
                    prd_content = f"{prd_content}\n\n=== 文件内容 ===\n\n{parse_result['combined_text']}"
                else:
                    prd_content = parse_result["combined_text"]
        except ImportError as e:
            errors.append(f"文档解析依赖未安装: {str(e)}")
        except Exception as e:
            errors.append(f"文件解析失败: {str(e)}")

    if not prd_content:
        return ApiResponse.error("请提供文本内容或上传文件", code=400)

    result = compile_to_business_system(prd_content)
    bs = result["business_system"]

    visuals = []
    if "html" in output_types or "json" in output_types:
        try:
            from app.engines.visual_binding import bind_visuals
            visual_result = bind_visuals(bs)
            visuals = visual_result.get("visuals", []) if isinstance(visual_result, dict) else visual_result
        except Exception:
            pass

    return ApiResponse.ok({
        "pipeline": result["pipeline"],
        "business_system": bs,
        "composed": bs.get("composed", {}),
        "workspace": result.get("workspace", {}),
        "visuals": visuals,
        "summary": result["summary"],
        "output_types": output_types,
        "files": parsed_files,
        "errors": errors,
    })


@router.post(
    "/stage",
    summary="单独执行某个阶段",
    description="""单独执行BSC Pipeline的某个阶段。

可用阶段：
- **business_understanding** - 业务理解
- **sop** - SOP流程设计
- **risk** - 风险分析
- **strategy** - 战略分析
- **optimization** - 优化建议
- **composer** - 结果组装

注意：composer阶段需要提供完整的Agent结果作为上下文
""",
    response_description="阶段执行成功，返回阶段数据",
)
async def execute_stage(req: StageRequest):
    """单独执行某个阶段"""
    from app.core.bsc_pipeline import BSC_PIPELINE

    chunks = [{"chunk_id": "001", "content": req.input}]

    try:
        result = BSC_PIPELINE.execute_stage(req.stage_key, chunks)
        return ApiResponse.ok({"stage": req.stage_key, "data": result})
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)


@router.get(
    "/stages",
    summary="获取所有阶段信息",
    description="获取BSC Pipeline的所有阶段及其配置信息",
    response_description="返回阶段列表",
)
async def list_stages():
    """获取所有阶段信息"""
    from app.core.bsc_pipeline import BSC_PIPELINE
    return ApiResponse.ok({"stages": BSC_PIPELINE.get_stage_info()})


@router.get(
    "/health",
    summary="健康检查",
    description="检查BSC服务状态，包括LLM服务和Pipeline配置",
    response_description="返回服务健康状态",
)
async def health():
    """健康检查"""
    from app.services.llm_service import get_llm_service
    from app.core.bsc_pipeline import BSC_PIPELINE

    llm_service = get_llm_service()
    return ApiResponse.ok({
        "pipeline": "BSC Pipeline v2",
        "llm": llm_service.status(),
        "stages": BSC_PIPELINE.get_stage_info(),
        "flow": ["business_understanding", "sop", "risk", "strategy", "optimization", "report"],
    })


@router.post(
    "/export",
    summary="导出结果（多格式）",
    description="""导出编译结果为多种格式。

支持的输出格式：
- **json** - JSON格式的业务系统数据
- **html** - HTML报告页面
- **ppt** - PPT幻灯片规格（JSON格式）
- **word** - Word文档（Base64编码）
- **markdown** - Markdown格式报告
- **pdf** - PDF文档（Base64编码）

使用方式：
1. 提供input参数，先编译再导出
2. 直接提供business_system参数，跳过编译直接导出
""",
    response_description="导出成功，返回各格式的导出数据",
)
async def export_results(req: ExportRequest):
    """导出结果（多格式）"""
    from app.core.bsc_pipeline import compile_to_business_system

    if req.business_system:
        bs = req.business_system
        result = {"business_system": bs, "summary": bs.get("report", {}).get("executive_summary", ""), "pipeline": {}}
    elif req.input:
        result = compile_to_business_system(req.input)
        bs = result["business_system"]
    else:
        return ApiResponse.error("请提供business_system或input参数", code=400)

    exports = {}
    errors = []

    if "json" in req.output_types:
        exports["json"] = bs

    if "html" in req.output_types:
        exports["html"] = _generate_html(bs, result.get("pipeline", {}))

    if "ppt" in req.output_types:
        exports["ppt"] = _generate_ppt_spec(bs)

    if "word" in req.output_types:
        try:
            from exporters.word_exporter import WordExporter
            word_bytes = WordExporter().export(bs)
            exports["word"] = {"content_base64": word_bytes.hex(), "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        except Exception as e:
            errors.append(f"Word导出失败: {str(e)}")

    if "markdown" in req.output_types:
        try:
            from exporters.markdown_exporter import MarkdownExporter
            exports["markdown"] = MarkdownExporter().export(bs)
        except Exception as e:
            errors.append(f"Markdown导出失败: {str(e)}")

    if "pdf" in req.output_types:
        try:
            from exporters.pdf_exporter import PDFExporter
            pdf_bytes = PDFExporter().export(bs)
            exports["pdf"] = {"content_base64": pdf_bytes.hex(), "mime_type": "application/pdf"}
        except Exception as e:
            errors.append(f"PDF导出失败: {str(e)}")

    try:
        from app.engines.visual_binding import bind_visuals
        exports["visuals"] = bind_visuals(bs)
    except Exception:
        exports["visuals"] = []

    return ApiResponse.ok({
        "exports": exports,
        "formats": list(exports.keys()),
        "summary": result["summary"],
        "errors": errors,
    })


def _generate_html(business_system: dict, pipeline_info: dict) -> str:
    """生成HTML报告"""
    from datetime import datetime

    sections = []
    sections.append(f"<h1>{html.escape(business_system.get('business_domain', '业务系统分析'))}</h1>")
    sections.append(f"<p class='summary'>{html.escape(business_system.get('report', {}).get('executive_summary', ''))}</p>")

    if business_system.get("objectives"):
        sections.append("<h2>业务目标</h2>")
        sections.append("<ul>")
        for obj in business_system["objectives"]:
            priority = obj.get("priority", "medium")
            sections.append(f"<li><strong>{html.escape(obj.get('objective', ''))}</strong>: {html.escape(obj.get('target', ''))} ({html.escape(priority)})</li>")
        sections.append("</ul>")

    if business_system.get("workflow"):
        sections.append("<h2>流程步骤</h2>")
        sections.append("<ol>")
        for step in business_system["workflow"]:
            sections.append(f"<li><strong>步骤{html.escape(str(step.get('step', '')))}: {html.escape(step.get('name', ''))}</strong><br>{html.escape(step.get('action', ''))}</li>")
        sections.append("</ol>")

    if business_system.get("metrics"):
        sections.append("<h2>关键指标</h2>")
        sections.append("<table>")
        sections.append("<tr><th>指标</th><th>公式</th><th>目标</th><th>负责人</th></tr>")
        for kpi in business_system["metrics"]:
            sections.append(f"<tr><td>{html.escape(kpi.get('name', ''))}</td><td>{html.escape(kpi.get('formula', ''))}</td><td>{html.escape(kpi.get('target', ''))}</td><td>{html.escape(kpi.get('owner', ''))}</td></tr>")
        sections.append("</table>")

    if business_system.get("risks"):
        sections.append("<h2>风险分析</h2>")
        sections.append("<ul>")
        for risk in business_system["risks"]:
            sections.append(f"<li><strong>{html.escape(risk.get('risk', ''))}</strong> ({html.escape(risk.get('severity', ''))}) - {html.escape(risk.get('mitigation', ''))}</li>")
        sections.append("</ul>")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>业务系统分析报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #12161A; color: #E8E8E8; }}
        h1 {{ color: #C9A84C; }}
        h2 {{ color: #5A9E96; margin-top: 30px; }}
        .summary {{ font-size: 1.1em; color: #B8B8B8; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
        th, td {{ border: 1px solid #2E3338; padding: 10px; text-align: left; }}
        th {{ background: #1C2024; color: #C9A84C; }}
        ul, ol {{ line-height: 1.8; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
{''.join(sections)}
<p style='margin-top: 40px; color: #8A8A86; font-size: 0.9em;'>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body>
</html>"""

    return html_content


def _generate_ppt_spec(business_system: dict) -> dict:
    """生成PPT规格"""
    slides = []

    slides.append({
        "slide_type": "title",
        "title": business_system.get("business_domain", "业务系统分析"),
        "subtitle": "基于PRD的业务系统分析报告",
    })

    if business_system.get("objectives"):
        slides.append({
            "slide_type": "list",
            "title": "业务目标",
            "items": [f"{obj.get('objective', '')}: {obj.get('target', '')}" for obj in business_system["objectives"]],
        })

    if business_system.get("workflow"):
        slides.append({
            "slide_type": "flow",
            "title": "流程设计",
            "steps": [step.get("name", "") for step in business_system["workflow"]],
        })

    if business_system.get("metrics"):
        slides.append({
            "slide_type": "table",
            "title": "关键指标",
            "headers": ["指标", "公式", "目标"],
            "data": [[kpi.get("name", ""), kpi.get("formula", ""), kpi.get("target", "")] for kpi in business_system["metrics"]],
        })

    if business_system.get("risks"):
        slides.append({
            "slide_type": "list",
            "title": "风险分析",
            "items": [f"{risk.get('risk', '')} ({risk.get('severity', '')})" for risk in business_system["risks"][:5]],
        })

    if business_system.get("strategy"):
        ops = business_system["strategy"].get("growth_opportunities", [])
        slides.append({
            "slide_type": "list",
            "title": "战略机会",
            "items": [f"{op.get('opportunity', '')}: {op.get('potential', '')}" for op in ops],
        })

    if business_system.get("report"):
        slides.append({
            "slide_type": "content",
            "title": "执行摘要",
            "content": business_system["report"].get("executive_summary", ""),
        })

    return {"slides": slides, "theme": "dark", "slide_count": len(slides)}