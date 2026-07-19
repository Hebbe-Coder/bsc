"""Template API - 模板系统CRUD接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateCreateRequest(BaseModel):
    """创建模板请求"""
    name: str = Field(..., description="模板名称", min_length=1)
    category: str = Field("analysis", description="模板分类")
    industry: str = Field("general", description="所属行业")
    config: Dict[str, Any] = Field({}, description="模板配置")
    description: str = Field("", description="模板描述")
    sort_order: int = Field(0, description="排序优先级")


class TemplateUpdateRequest(BaseModel):
    """更新模板请求"""
    name: Optional[str] = Field(None, description="模板名称")
    category: Optional[str] = Field(None, description="模板分类")
    industry: Optional[str] = Field(None, description="所属行业")
    config: Optional[Dict[str, Any]] = Field(None, description="模板配置")
    description: Optional[str] = Field(None, description="模板描述")
    sort_order: Optional[int] = Field(None, description="排序优先级")
    is_active: Optional[bool] = Field(None, description="是否启用")


class TemplateDuplicateRequest(BaseModel):
    """复制模板请求"""
    new_name: str = Field(..., description="新模板名称", min_length=1)


class IndustryDetectRequest(BaseModel):
    """行业检测请求"""
    text: str = Field(..., description="待检测的文本内容")


@router.get("/", summary="获取所有模板")
async def list_templates(category: Optional[str] = None, industry: Optional[str] = None):
    """获取所有模板列表，支持按分类和行业筛选"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    if category:
        templates = tm.get_templates_by_category(category)
    elif industry:
        templates = tm.get_templates_by_industry(industry)
    else:
        templates = tm.get_all_templates()

    return {"success": True, "data": templates, "count": len(templates)}


@router.get("/{template_id}", summary="获取单个模板")
async def get_template(template_id: str):
    """根据ID获取模板详情"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()
    template = tm.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail={"success": False, "error": "模板不存在"})

    return {"success": True, "data": template}


@router.post("/", summary="创建自定义模板")
async def create_template(req: TemplateCreateRequest):
    """创建新的自定义模板"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    try:
        template_id = tm.create_template(
            name=req.name,
            config=req.config,
            category=req.category,
            industry=req.industry,
            description=req.description,
            sort_order=req.sort_order
        )
        template = tm.get_template(template_id)
        return {"success": True, "data": template}
    except Exception as e:
        logger.error(f"创建模板失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.put("/{template_id}", summary="更新模板")
async def update_template(template_id: str, req: TemplateUpdateRequest):
    """更新自定义模板"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    try:
        update_data = {}
        if req.name is not None:
            update_data["name"] = req.name
        if req.category is not None:
            update_data["category"] = req.category
        if req.industry is not None:
            update_data["industry"] = req.industry
        if req.config is not None:
            update_data["config"] = req.config
        if req.description is not None:
            update_data["description"] = req.description
        if req.sort_order is not None:
            update_data["sort_order"] = req.sort_order
        if req.is_active is not None:
            update_data["is_active"] = req.is_active

        success = tm.update_template(template_id, **update_data)
        if success:
            template = tm.get_template(template_id)
            return {"success": True, "data": template}
        return {"success": False, "error": "未更新任何字段"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"success": False, "error": str(e)})
    except Exception as e:
        logger.error(f"更新模板失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.delete("/{template_id}", summary="删除模板")
async def delete_template(template_id: str):
    """删除自定义模板（软删除）"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    try:
        tm.delete_template(template_id)
        return {"success": True, "message": "模板已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"success": False, "error": str(e)})
    except Exception as e:
        logger.error(f"删除模板失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/{template_id}/duplicate", summary="复制模板")
async def duplicate_template(template_id: str, req: TemplateDuplicateRequest):
    """复制现有模板创建新模板"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    try:
        new_id = tm.duplicate_template(template_id, req.new_name)
        template = tm.get_template(new_id)
        return {"success": True, "data": template}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"success": False, "error": str(e)})
    except Exception as e:
        logger.error(f"复制模板失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/detect", summary="检测行业")
async def detect_industry(req: IndustryDetectRequest):
    """根据文本自动检测所属行业并推荐模板"""
    from app.templates.template_manager import get_template_manager

    tm = get_template_manager()

    try:
        template_id, template = tm.detect_industry(req.text)
        return {
            "success": True,
            "data": {
                "template_id": template_id,
                "template": template,
                "industry": template.get("industry", "general"),
                "industry_name": template.get("name", "通用业务"),
            }
        }
    except Exception as e:
        logger.error(f"行业检测失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/categories", summary="获取模板分类")
async def get_categories():
    """获取所有模板分类"""
    from app.templates.template_manager import TEMPLATE_CATEGORIES
    return {"success": True, "data": TEMPLATE_CATEGORIES}


@router.get("/types", summary="获取模板类型")
async def get_types():
    """获取所有模板类型"""
    from app.templates.template_manager import TEMPLATE_TYPES
    return {"success": True, "data": TEMPLATE_TYPES}
