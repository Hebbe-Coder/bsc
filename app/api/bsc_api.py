"""BSC API - BSC Pipeline 唯一入口"""
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os

from app.api.response import ApiResponse
from app.core.config import settings

router = APIRouter(prefix="/bsc", tags=["BSC Pipeline"])

MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


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
    response_model=ApiResponse[Dict[str, Any]],
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

    pipeline = result.get("pipeline", {})
    stages = pipeline.get("stages", [])
    failed = []
    if isinstance(stages, list):
        failed = [s for s in stages if isinstance(s, dict) and s.get("status") == "failed"]
    if failed:
        agents = ", ".join(s.get("agent") or s.get("display") or "?" for s in failed)
        # 去除可能泄漏内部路径/堆栈的字段，仅保留阶段状态信息
        _LEAK_KEYS = ("traceback", "exception", "stack")
        safe_stages = [
            {k: v for k, v in s.items() if k not in _LEAK_KEYS}
            for s in stages if isinstance(s, dict)
        ]
        return ApiResponse(
            success=False,
            code=2001,
            message=f"编译有 {len(failed)} 个分析阶段失败：{agents}",
            data={"stages": safe_stages, "partial_business_system": bs},
        )

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
    response_model=ApiResponse[Dict[str, Any]],
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

    pipeline = result.get("pipeline", {})
    stages = pipeline.get("stages", [])
    failed = []
    if isinstance(stages, list):
        failed = [s for s in stages if isinstance(s, dict) and s.get("status") == "failed"]
    if failed:
        agents = ", ".join(s.get("agent") or s.get("display") or "?" for s in failed)
        _LEAK_KEYS = ("traceback", "exception", "stack")
        safe_stages = [
            {k: v for k, v in s.items() if k not in _LEAK_KEYS}
            for s in stages if isinstance(s, dict)
        ]
        return ApiResponse(
            success=False,
            code=2001,
            message=f"编译有 {len(failed)} 个分析阶段失败：{agents}",
            data={"stages": safe_stages, "partial_business_system": bs},
        )

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
    summary="导出结果（多格式，默认容错降级）",
    description="""导出编译结果为多种格式。任意格式无法产出时默认走降级：
先尝试替代格式，无替代或替代也失败则丢弃并返回其余成功格式。
响应 formats_status 逐格式说明 produced / substituted / dropped 及原因。

支持的输出格式：
- json / html / ppt / word / markdown / pdf（直接产出）
- pptx / xlsx（可请求，自动降级到可用替代格式）

未知格式名返回 400。可用 GET /bsc/exports/capabilities 预检依赖可用性。
""",
    response_description="导出结果，含逐格式状态表",
)
async def export_results(req: ExportRequest):
    """导出结果（多格式，默认容错降级）"""
    from app.core.bsc_pipeline import compile_to_business_system
    from exporters.orchestrator import run_export
    from exporters.degrade import VALID_OUTPUT_TYPES

    if req.business_system:
        bs = req.business_system
        result = {
            "business_system": bs,
            "summary": bs.get("report", {}).get("executive_summary", ""),
            "pipeline": {},
        }
    elif req.input:
        result = compile_to_business_system(req.input)
        bs = result["business_system"]
    else:
        return ApiResponse.error("请提供business_system或input参数", code=400)

    # 校验请求格式是否合法（未知格式名 → 400，不降级）
    unknown = [f for f in req.output_types if f not in VALID_OUTPUT_TYPES]
    if unknown:
        return ApiResponse.error(f"不支持的导出格式: {unknown}", code=400)

    # 保持原行为：始终尝试绑定 visuals
    output_types = list(req.output_types)
    if "visuals" not in output_types:
        output_types.append("visuals")

    outcome = run_export(bs, output_types, result)

    payload = {
        "exports": outcome.exports,
        "formats": list(outcome.exports.keys()),
        "formats_status": outcome.formats_status,
        "summary": result["summary"],
        "errors": outcome.errors,
    }

    def _is_degraded(s: dict) -> bool:
        return s["status"] in ("substituted", "dropped") or bool(s.get("components_degraded"))

    any_produced = any(s["status"] in ("produced", "substituted") for s in outcome.formats_status)
    any_degraded = any(_is_degraded(s) for s in outcome.formats_status)

    if not any_produced:
        return ApiResponse.error("所有请求格式均无法产出", code=422).model_copy(
            update={"data": payload}
        )
    if any_degraded:
        return ApiResponse.partial(payload, message="部分格式经降级/替换处理", errors=outcome.errors)
    return ApiResponse.ok(payload)


@router.get(
    "/exports/capabilities",
    summary="导出能力自检",
    description="返回各导出格式当前是否可用及缺失依赖的安装命令。",
)
async def export_capabilities():
    from exporters.capabilities import EXPORT_CAPABILITIES
    return ApiResponse.ok({"capabilities": EXPORT_CAPABILITIES})
