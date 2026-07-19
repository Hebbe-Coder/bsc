"""PM Report API - 产品经理专业报告接口"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
import logging
import uuid
import json

from app.api.response import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pm-report", tags=["PM Report"])


class CoreObjective(BaseModel):
    objective: str = Field(..., min_length=1, description="目标名称")
    target: str = Field("", description="目标值")
    priority: str = Field("medium", description="优先级")


class WorkflowStep(BaseModel):
    step: int = Field(..., ge=1, description="步骤编号")
    name: str = Field(..., min_length=1, description="步骤名称")
    action: str = Field("", description="动作描述")
    role: str = Field("", description="负责角色")


class BusinessSystemBase(BaseModel):
    business_understanding: Optional[Dict[str, Any]] = Field(
        default=None,
        description="业务理解数据",
    )
    sop: Optional[Dict[str, Any]] = Field(
        default=None,
        description="SOP流程数据",
    )
    risk: Optional[Dict[str, Any]] = Field(
        default=None,
        description="风险分析数据",
    )
    strategy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="战略分析数据",
    )
    optimization: Optional[Dict[str, Any]] = Field(
        default=None,
        description="优化建议数据",
    )
    
    @field_validator("business_understanding")
    def validate_business_understanding(cls, v):
        if v is not None:
            objectives = v.get("core_objectives", [])
            for obj in objectives:
                if not isinstance(obj, dict) or not obj.get("objective"):
                    raise ValueError("core_objectives 中的每个目标必须包含 objective 字段")
        return v
    
    @field_validator("sop")
    def validate_sop(cls, v):
        if v is not None:
            workflow = v.get("workflow", [])
            for step in workflow:
                if not isinstance(step, dict) or not step.get("name"):
                    raise ValueError("workflow 中的每个步骤必须包含 name 字段")
        return v


class GenerateReportRequest(BaseModel):
    business_system: Union[BusinessSystemBase, Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )
    sections: List[str] = Field(
        default=["rtm", "priority", "stakeholder", "timeline", "risk", "kpi"],
        description="要生成的报告章节",
    )
    
    @field_validator("sections")
    def validate_sections(cls, v):
        valid_sections = {"rtm", "priority", "stakeholder", "timeline", "risk", "kpi"}
        for section in v:
            if section not in valid_sections:
                raise ValueError(f"无效的章节名称: {section}，可选值: {', '.join(valid_sections)}")
        return v


class ExportRequest(BaseModel):
    business_system: Union[BusinessSystemBase, Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )
    format: str = Field("html", description="导出格式：html, markdown")
    sections: List[str] = Field(
        default=["rtm", "priority", "stakeholder", "timeline", "risk", "kpi"],
        description="要生成的报告章节",
    )
    
    @field_validator("format")
    def validate_format(cls, v):
        if v not in {"html", "markdown"}:
            raise ValueError(f"无效的导出格式: {v}，可选值: html, markdown")
        return v
    
    @field_validator("sections")
    def validate_sections(cls, v):
        valid_sections = {"rtm", "priority", "stakeholder", "timeline", "risk", "kpi"}
        for section in v:
            if section not in valid_sections:
                raise ValueError(f"无效的章节名称: {section}，可选值: {', '.join(valid_sections)}")
        return v


class BusinessSystemRequest(BaseModel):
    business_system: Union[BusinessSystemBase, Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )


class PersonalizedReportRequest(BaseModel):
    """个性化报告请求"""
    user_id: str = Field(..., description="用户ID")
    business_system: Union[BusinessSystemBase, Dict[str, Any]] = Field(
        ...,
        description="已编译的业务系统数据",
    )
    format: Optional[str] = Field(None, description="导出格式（可选，使用用户偏好）")


@router.post("/generate/personalized", summary="生成个性化PM报告")
async def generate_personalized_report(req: PersonalizedReportRequest):
    """
    根据用户偏好生成个性化PM报告
    
    使用用户历史偏好自动选择：
    - 报告格式（HTML/Markdown）
    - 章节顺序和内容
    - 输出样式
    
    用户偏好来源：
    - 之前使用的报告格式
    - 常用的报告章节
    - 个性化样式设置
    """
    from app.services.user_preference_service import UserPreferenceService
    from app.engines.pm_report_engine import PMReportEngine
    
    service = UserPreferenceService()
    preferences = service.get_preferences(req.user_id)
    
    format_prefs = preferences.get("format", {})
    output_format = req.format or format_prefs.get("output_format", "html")
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    report = engine.generate_full_pm_report(bs_data)
    
    if output_format == "markdown":
        content = engine.export_to_markdown(report)
        media_type = "text/markdown"
    else:
        content = engine.export_to_html(report)
        media_type = "text/html"
    
    service.learn_preference(req.user_id, "export", {"format": output_format})
    
    return ApiResponse.ok({
        "report": report,
        "content": content,
        "format": output_format,
        "media_type": media_type,
        "preferences_used": format_prefs,
    })


@router.post("/generate", summary="生成PM专业报告")
async def generate_pm_report(req: GenerateReportRequest):
    """
    生成产品经理专业报告
    
    报告章节：
    - rtm: 需求追踪矩阵
    - priority: 功能优先级矩阵
    - stakeholder: 干系人地图
    - timeline: 项目时间线
    - risk: 风险登记册
    - kpi: KPI仪表盘
    
    每个章节基于业务系统数据自动生成专业内容：
    - RTM: 需求与功能、流程的映射关系
    - 优先级矩阵: 基于价值/复杂度的功能排序
    - 干系人地图: 基于权力/利益矩阵的分析
    - 时间线: 项目阶段和里程碑规划
    - 风险登记册: 风险识别和应对措施
    - KPI仪表盘: 关键业务指标和目标
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    report = engine.generate_full_pm_report(bs_data)
    
    filtered_sections = []
    section_key_map = {
        "rtm": "需求追踪矩阵",
        "priority": "功能优先级矩阵",
        "stakeholder": "干系人地图",
        "timeline": "项目时间线",
        "risk": "风险登记册",
        "kpi": "KPI仪表盘",
    }
    
    for section in report["sections"]:
        for key, title in section_key_map.items():
            if key in req.sections and section["title"] == title:
                filtered_sections.append(section)
                break
    
    report["sections"] = filtered_sections
    
    return ApiResponse.ok(report)


@router.post("/export", summary="导出PM专业报告")
async def export_pm_report(req: ExportRequest):
    """
    导出产品经理专业报告
    
    支持的格式：
    - html: 专业排版的HTML报告
    - markdown: 版本控制友好的Markdown格式
    
    导出文件包含：
    - 需求追踪矩阵
    - 功能优先级矩阵
    - 干系人地图
    - 项目时间线
    - 风险登记册
    - KPI仪表盘
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    report = engine.generate_full_pm_report(bs_data)
    
    if req.format == "markdown":
        content = engine.export_to_markdown(report)
        media_type = "text/markdown"
        filename = f"pm_report_{uuid.uuid4().hex[:8]}.md"
    elif req.format == "html":
        content = engine.export_to_html(report)
        media_type = "text/html"
        filename = f"pm_report_{uuid.uuid4().hex[:8]}.html"
    else:
        raise HTTPException(status_code=400, detail=ApiResponse.error("不支持的导出格式", code=400).dict())
    
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": media_type,
        },
    )


@router.post("/rtm", summary="生成需求追踪矩阵")
async def generate_rtm(req: BusinessSystemRequest):
    """
    生成需求追踪矩阵 (RTM)
    
    RTM结构：
    - 需求ID、需求描述、功能模块、关联SOP步骤、状态、优先级、验收标准
    
    用途：
    - 跟踪需求从提出到实现的全过程
    - 确保每个需求都有对应的功能实现
    - 支持需求变更管理
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    rtm = engine.generate_requirement_traceability_matrix(bs_data)
    
    return ApiResponse.ok(rtm)


@router.post("/priority", summary="生成功能优先级矩阵")
async def generate_priority_matrix(req: BusinessSystemRequest):
    """
    生成功能优先级矩阵
    
    基于价值/复杂度矩阵进行优先级排序：
    - P0: 高价值/低复杂度，紧急优先
    - P1: 高价值/中复杂度，重要优先
    - P2: 中价值/中复杂度，一般优先级
    - P3: 低价值/高复杂度，低优先级
    
    用途：
    - 帮助产品经理进行功能排期决策
    - 优化资源分配
    - 最大化项目价值
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    matrix = engine.generate_feature_priority_matrix(bs_data)
    
    return ApiResponse.ok(matrix)


@router.post("/stakeholder", summary="生成干系人地图")
async def generate_stakeholder_map(req: BusinessSystemRequest):
    """
    生成干系人地图
    
    基于权力/利益矩阵识别关键干系人：
    - 高权力/高利益：重点管理
    - 高权力/低利益：保持满意
    - 低权力/高利益：保持告知
    - 低权力/低利益：最小关注
    
    用途：
    - 识别项目关键干系人
    - 制定干系人管理策略
    - 确保项目获得足够支持
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    map_data = engine.generate_stakeholder_map(bs_data)
    
    return ApiResponse.ok(map_data)


@router.post("/timeline", summary="生成项目时间线")
async def generate_timeline(req: BusinessSystemRequest):
    """
    生成项目时间线
    
    基于战略分析中的阶段规划生成时间线：
    - 里程碑
    - 交付物
    - 时间节点
    
    用途：
    - 展示项目整体规划
    - 跟踪项目进度
    - 与团队和 stakeholders 沟通项目计划
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    timeline = engine.generate_project_timeline(bs_data)
    
    return ApiResponse.ok(timeline)


@router.post("/risk", summary="生成风险登记册")
async def generate_risk_register(req: BusinessSystemRequest):
    """
    生成风险登记册
    
    整合所有风险分析结果：
    - 风险描述
    - 严重程度
    - 概率
    - 风险评分
    - 优先级
    - 应对措施
    
    用途：
    - 识别项目潜在风险
    - 评估风险影响
    - 制定风险应对策略
    - 跟踪风险状态
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    register = engine.generate_risk_register(bs_data)
    
    return ApiResponse.ok(register)


@router.post("/kpi", summary="生成KPI仪表盘")
async def generate_kpi_dashboard(req: BusinessSystemRequest):
    """
    生成KPI仪表盘数据
    
    整合所有关键指标：
    - SLA指标
    - KPI指标
    - 自动化指标
    
    用途：
    - 监控业务表现
    - 跟踪目标达成情况
    - 支持数据驱动决策
    """
    from app.engines.pm_report_engine import PMReportEngine
    
    engine = PMReportEngine()
    bs_data = req.business_system.dict() if hasattr(req.business_system, 'dict') else req.business_system
    dashboard = engine.generate_kpi_dashboard(bs_data)
    
    return ApiResponse.ok(dashboard)


@router.get("/preview", summary="预览PM报告")
async def preview_report(business_system: Optional[str] = None, section: str = "rtm"):
    """
    预览报告章节
    
    参数：
    - business_system: 业务系统JSON字符串（可选，使用mock数据）
    - section: 章节名称（rtm/priority/stakeholder/timeline/risk/kpi）
    
    返回指定章节的HTML预览内容
    """
    from app.engines.pm_report_engine import PMReportEngine
    from app.services.llm_service import LLMService
    
    engine = PMReportEngine()
    
    valid_sections = {"rtm", "priority", "stakeholder", "timeline", "risk", "kpi"}
    if section not in valid_sections:
        raise HTTPException(status_code=400, detail=ApiResponse.error(f"未知的章节名称: {section}", code=400).dict())
    
    if business_system:
        try:
            bs = json.loads(business_system)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=ApiResponse.error("无效的JSON格式", code=400).dict())
    else:
        llm = LLMService(provider="mock")
        bs = llm._mock("你是Business Understanding Agent", "零售电商系统PRD")
        bs["sop"] = llm._mock("你是SOP Agent", "")
        bs["risk"] = llm._mock("你是Risk Agent", "")
        bs["strategy"] = llm._mock("你是Strategy Agent", "")
        bs["optimization"] = llm._mock("你是Optimization Agent", "")
    
    section_map = {
        "rtm": engine.generate_requirement_traceability_matrix,
        "priority": engine.generate_feature_priority_matrix,
        "stakeholder": engine.generate_stakeholder_map,
        "timeline": engine.generate_project_timeline,
        "risk": engine.generate_risk_register,
        "kpi": engine.generate_kpi_dashboard,
    }
    
    section_data = section_map[section](bs)
    
    report = {
        "title": f"预览 - {section_data['title']}",
        "generated_at": "",
        "sections": [section_data],
    }
    
    html_content = engine.export_to_html(report)
    
    return StreamingResponse(
        iter([html_content]),
        media_type="text/html",
    )
