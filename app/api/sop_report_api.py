"""SOP Report API - SOP汇报接口"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
import logging
import os
import uuid
import json

from app.api.response import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sop-report", tags=["SOP Report"])


class BusinessSystemRequest(BaseModel):
    business_system: Union[Dict[str, Any], Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )


class GenerateRequest(BusinessSystemRequest):
    enable_ai_analysis: bool = Field(False, description="是否启用AI分析功能")


class ExportRequest(BaseModel):
    business_system: Union[Dict[str, Any], Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )
    format: str = Field("html", description="导出格式：html, markdown, pptx")
    enable_ai_analysis: bool = Field(False, description="是否启用AI分析功能")
    
    @field_validator("format")
    def validate_format(cls, v):
        if v not in {"html", "markdown", "pptx"}:
            raise ValueError(f"无效的导出格式: {v}，可选值: html, markdown, pptx")
        return v


@router.post("/generate", summary="生成SOP汇报")
async def generate_sop_report(req: GenerateRequest):
    """
    生成完整的SOP汇报

    汇报内容包含：
    1. 流程概览 - 总步骤数、角色数量、是否含升级机制、预估总耗时
    2. 详细流程 - 每步的名称、动作、负责人、输入输出、SLA、风险点
    3. 角色职责 - 各角色负责的步骤、职责范围
    4. SLA汇总 - 各步骤SLA、总耗时预估
    5. 风险评估 - 各步骤风险点、缓解措施
    6. 流程图 - 可视化流程结构（支持泳道图）
    7. 关键成功因素 - 流程成功的关键要素
    8. 度量指标 - 效率、质量、成本衡量标准
    9. 里程碑规划 - 流程执行关键节点
    10. 成本估算 - 人力和时间成本预估
    11. 智能摘要 - LLM生成的汇报核心要点（需启用AI分析）
    12. AI优化建议 - LLM生成的改进建议（需启用AI分析）

    输入：业务系统数据（包含workflow、roles、objectives、sla、risks等）
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    report = engine.generate_full_sop_report(bs_data, enable_ai_analysis=req.enable_ai_analysis)
    
    return ApiResponse.ok(report)


@router.post("/export", summary="导出SOP汇报")
async def export_sop_report(req: ExportRequest):
    """
    导出SOP汇报

    支持的格式：
    - html: 专业排版的HTML报告
    - markdown: 版本控制友好的Markdown格式
    - pptx: 专业演示文稿格式

    导出文件包含完整的SOP汇报内容。
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    report = engine.generate_full_sop_report(bs_data, enable_ai_analysis=req.enable_ai_analysis)
    
    if req.format == "markdown":
        content = engine.export_to_markdown(report)
        media_type = "text/markdown"
        filename = f"sop_report_{uuid.uuid4().hex[:8]}.md"
        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": media_type,
            },
        )
    elif req.format == "html":
        content = engine.export_to_html(report)
        media_type = "text/html"
        filename = f"sop_report_{uuid.uuid4().hex[:8]}.html"
        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": media_type,
            },
        )
    elif req.format == "pptx":
        try:
            pptx_path = engine.export_to_pptx(report)
            
            with open(pptx_path, "rb") as f:
                pptx_bytes = f.read()
            
            import os
            os.remove(pptx_path)
            
            return StreamingResponse(
                iter([pptx_bytes]),
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                headers={
                    "Content-Disposition": f"attachment; filename=sop_report_{uuid.uuid4().hex[:8]}.pptx",
                    "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                },
            )
        except Exception as e:
            error_detail = str(e)
            error_code = 500
            
            from exporters.errors import ExportDependencyError
            if isinstance(e, ExportDependencyError):
                error_detail = f"{e.missing_package}依赖缺失，请执行: {e.pip_install}"
                error_code = 503
            
            raise HTTPException(
                status_code=error_code,
                detail=ApiResponse.error(error_detail, code=error_code).dict()
            )
    else:
        raise HTTPException(status_code=400, detail=ApiResponse.error("不支持的导出格式", code=400).dict())


@router.post("/overview", summary="生成流程概览")
async def generate_overview(req: BusinessSystemRequest):
    """
    生成流程概览

    包含：
    - 业务领域
    - 核心目标
    - 总步骤数
    - 角色数量
    - 是否含升级机制
    - 预估总耗时
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    overview = engine.generate_overview(bs_data)
    
    return ApiResponse.ok(overview)


@router.post("/workflow", summary="生成详细流程")
async def generate_workflow_detail(req: BusinessSystemRequest):
    """
    生成详细流程

    包含每个步骤的：
    - 步骤编号、名称、动作
    - 负责人/角色
    - 输入/输出
    - SLA
    - 风险点和缓解措施
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    workflow = engine.generate_workflow_detail(bs_data)
    
    return ApiResponse.ok(workflow)


@router.post("/roles", summary="生成角色职责")
async def generate_role_responsibilities(req: BusinessSystemRequest):
    """
    生成角色职责

    包含：
    - 角色名称、部门、级别、人数
    - 负责的步骤
    - 职责描述
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    roles = engine.generate_role_responsibilities(bs_data)
    
    return ApiResponse.ok(roles)


@router.post("/sla", summary="生成SLA汇总")
async def generate_sla_summary(req: BusinessSystemRequest):
    """
    生成SLA汇总

    包含：
    - 各指标的SLA目标
    - 负责人
    - 步骤级SLA
    - 总耗时预估
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    sla = engine.generate_sla_summary(bs_data)
    
    return ApiResponse.ok(sla)


@router.post("/risk", summary="生成风险评估")
async def generate_risk_assessment(req: BusinessSystemRequest):
    """
    生成风险评估

    包含：
    - 各风险项的描述
    - 严重程度
    - 概率
    - 缓解措施
    - 风险等级分布
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    risk = engine.generate_risk_assessment(bs_data)
    
    return ApiResponse.ok(risk)


@router.post("/flowchart", summary="生成流程图数据")
async def generate_flowchart(req: BusinessSystemRequest):
    """
    生成流程图数据（支持泳道图）

    包含：
    - 节点列表（步骤信息）
    - 连线列表
    - 泳道分组信息
    - 布局信息

    可用于前端渲染流程图。
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    flowchart = engine.generate_flowchart(bs_data)
    
    return ApiResponse.ok(flowchart)


@router.post("/csf", summary="生成关键成功因素")
async def generate_csf(req: BusinessSystemRequest):
    """
    生成关键成功因素(CSF)

    包含：
    - 关键成功因素列表
    - 影响程度（高/中/低）
    - 当前状态（已满足/部分满足/未满足）
    - 改进行动项
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    csf = engine.generate_csf(bs_data)
    
    return ApiResponse.ok(csf)


@router.post("/metrics", summary="生成度量指标")
async def generate_metrics(req: BusinessSystemRequest):
    """
    生成度量指标

    包含：
    - 效率指标（流程周期时间、步骤通过率、SLA达成率）
    - 质量指标（输出准确率、客户满意度、错误返工率）
    - 成本指标（单位流程成本、人力投入）
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    metrics = engine.generate_metrics(bs_data)
    
    return ApiResponse.ok(metrics)


@router.post("/milestones", summary="生成里程碑规划")
async def generate_milestones(req: BusinessSystemRequest):
    """
    生成里程碑规划

    包含：
    - 里程碑节点列表
    - 阶段名称
    - 步骤范围
    - 截止时间
    - 状态
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    milestones = engine.generate_milestones(bs_data)
    
    return ApiResponse.ok(milestones)


@router.post("/cost", summary="生成成本估算")
async def generate_cost_estimate(req: BusinessSystemRequest):
    """
    生成成本估算

    包含：
    - 总工时估算
    - 人力成本估算（FTE）
    - 成本明细（按角色）
    - 平均小时费率
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    cost = engine.generate_cost_estimate(bs_data)
    
    return ApiResponse.ok(cost)


@router.post("/gantt-chart", summary="生成甘特图数据")
async def generate_gantt_chart(req: BusinessSystemRequest):
    """
    生成甘特图数据

    包含：
    - 任务列表
    - 持续时间
    - 角色分配
    - 开始偏移
    - 状态
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    gantt = engine.generate_gantt_chart(bs_data)
    
    return ApiResponse.ok(gantt)


@router.post("/role-matrix", summary="生成角色职责矩阵")
async def generate_role_matrix(req: BusinessSystemRequest):
    """
    生成角色职责矩阵

    包含：
    - 角色列表
    - 步骤列表
    - 角色与步骤的对应关系
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    matrix = engine.generate_role_matrix(bs_data)
    
    return ApiResponse.ok(matrix)


@router.post("/risk-heatmap", summary="生成风险热力图数据")
async def generate_risk_heatmap(req: BusinessSystemRequest):
    """
    生成风险热力图数据

    包含：
    - 风险点列表
    - 概率和严重程度评分
    - 热力图矩阵（3x3）
    - 高风险项数量
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    heatmap = engine.generate_risk_heatmap(bs_data)
    
    return ApiResponse.ok(heatmap)


@router.post("/ai-summary", summary="生成智能摘要")
async def generate_ai_summary(req: BusinessSystemRequest):
    """
    生成智能摘要（LLM驱动）

    包含：
    - 执行摘要（一句话核心摘要）
    - 关键发现（3-5个）
    - 建议（2-3条）
    - 风险亮点（1-2个高风险点）
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    summary = engine.generate_ai_summary(bs_data)
    
    return ApiResponse.ok(summary)


@router.post("/ai-recommendations", summary="生成AI优化建议")
async def generate_ai_recommendations(req: BusinessSystemRequest):
    """
    生成AI优化建议（LLM驱动）

    包含：
    - 优化建议列表（4-5条）
    - 优先级（高/中/低）
    - 预估改进效果
    - 实施步骤
    - 优先级排序的行动项
    """
    from app.engines.sop_report_engine import SOPReportEngine
    
    engine = SOPReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    recommendations = engine.generate_ai_recommendations(bs_data)
    
    return ApiResponse.ok(recommendations)


@router.get("/preview", summary="预览SOP汇报")
async def preview_report(business_system: Optional[str] = None, enable_ai_analysis: bool = False):
    """
    预览SOP汇报

    参数：
    - business_system: 业务系统JSON字符串（可选，使用mock数据）
    - enable_ai_analysis: 是否启用AI分析功能

    返回完整SOP汇报的HTML预览内容。
    """
    from app.engines.sop_report_engine import SOPReportEngine
    from app.services.llm_service import LLMService
    
    engine = SOPReportEngine()
    
    if business_system:
        try:
            bs = json.loads(business_system)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=ApiResponse.error("无效的JSON格式", code=400).dict())
    else:
        llm = LLMService(provider="mock")
        bs = {
            "business_domain": "金融服务",
            "objectives": llm._mock("你是Business Understanding Agent", "金融风控系统PRD").get("core_objectives", []),
            "workflow": llm._mock("你是SOP Agent", "").get("workflow", []),
            "roles": llm._mock("你是SOP Agent", "").get("roles", []),
            "responsibilities": llm._mock("你是SOP Agent", "").get("responsibilities", []),
            "sla": llm._mock("你是SOP Agent", "").get("sla", []),
            "kpi": llm._mock("你是SOP Agent", "").get("kpi", []),
            "risks": llm._mock("你是Risk Agent", "").get("risks", []),
            "risk": llm._mock("你是Risk Agent", ""),
        }
    
    report = engine.generate_full_sop_report(bs, enable_ai_analysis=enable_ai_analysis)
    html_content = engine.export_to_html(report)
    
    return StreamingResponse(
        iter([html_content]),
        media_type="text/html",
    )
