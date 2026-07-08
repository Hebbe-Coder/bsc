"""Template Manager - 统一管理内置模板和自定义模板"""
import os
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.database import get_database_backend

logger = logging.getLogger(__name__)

TEMPLATE_TYPES = {
    "analysis": "分析模板",
    "display": "展示模板",
    "workflow": "流程模板",
    "report": "报告模板",
}

TEMPLATE_CATEGORIES = {
    "business_understanding": "业务理解",
    "sop": "SOP设计",
    "risk": "风险分析",
    "strategy": "战略规划",
    "optimization": "优化建议",
    "report": "报告生成",
}


class TemplateManager:
    """模板管理器"""

    def __init__(self):
        self._backend = get_database_backend()
        self._builtin_templates = self._load_builtin_templates()
        self._cache = {}

    def _load_builtin_templates(self) -> Dict[str, Dict[str, Any]]:
        """加载内置行业分析模板"""
        from app.core.prompt_loader import load_industries

        industries = load_industries()
        templates = {}

        for industry_key, profile in industries.items():
            template_id = f"builtin_{industry_key}"
            templates[template_id] = {
                "id": template_id,
                "name": profile.get("name", industry_key),
                "category": "analysis",
                "industry": industry_key,
                "type": "analysis",
                "config": {
                    "typical_roles": profile.get("typical_roles", []),
                    "typical_sla": profile.get("typical_sla", ""),
                    "typical_kpis": profile.get("typical_kpis", []),
                    "typical_risks": profile.get("typical_risks", []),
                    "process_patterns": profile.get("process_patterns", []),
                    "report_sections": profile.get("report_sections", []),
                    "keywords": profile.get("keywords", []),
                    "cn_keywords": profile.get("cn_keywords", []),
                },
                "description": f"{profile.get('name')}行业分析模板，包含典型角色、KPI指标、风险模型等配置",
                "is_builtin": True,
                "is_active": True,
                "sort_order": 0,
            }

        return templates

    def get_all_templates(self) -> List[Dict[str, Any]]:
        """获取所有模板（内置+自定义）"""
        all_templates = []

        for template in self._builtin_templates.values():
            all_templates.append(template)

        try:
            cursor = self._backend.execute(
                "SELECT * FROM templates WHERE is_active = 1 ORDER BY sort_order, created_at DESC"
            )
            custom_templates = self._backend.rows_to_list(cursor)
            self._backend.close()

            for tpl in custom_templates:
                try:
                    tpl["config"] = json.loads(tpl.get("config_json", "{}"))
                except json.JSONDecodeError:
                    tpl["config"] = {}
                tpl["is_builtin"] = False
                all_templates.append(tpl)

        except Exception as e:
            logger.warning(f"读取自定义模板失败: {e}")

        all_templates.sort(key=lambda x: (x.get("sort_order", 0), x.get("created_at", "")))
        return all_templates

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """获取单个模板"""
        if template_id in self._builtin_templates:
            return self._builtin_templates[template_id]

        try:
            cursor = self._backend.execute(
                "SELECT * FROM templates WHERE id = ? AND is_active = 1",
                (template_id,)
            )
            row = cursor.fetchone()
            self._backend.close()

            if row:
                tpl = dict(row)
                try:
                    tpl["config"] = json.loads(tpl.get("config_json", "{}"))
                except json.JSONDecodeError:
                    tpl["config"] = {}
                tpl["is_builtin"] = False
                return tpl
        except Exception as e:
            logger.warning(f"读取模板失败: {e}")

        return None

    def create_template(self, name: str, config: Dict[str, Any],
                        category: str = "analysis", industry: str = "general",
                        description: str = "", sort_order: int = 0) -> str:
        """创建自定义模板"""
        template_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        try:
            self._backend.execute(
                """
                INSERT INTO templates (id, name, category, industry, type,
                                      config_json, description, is_builtin,
                                      is_active, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
                """,
                (
                    template_id, name, category, industry, "custom",
                    json.dumps(config, ensure_ascii=False), description,
                    sort_order, now, now
                )
            )
            self._backend.commit()
            self._backend.close()
            logger.info(f"创建自定义模板: {name} ({template_id})")
            return template_id
        except Exception as e:
            self._backend.rollback()
            self._backend.close()
            logger.error(f"创建模板失败: {e}")
            raise

    def update_template(self, template_id: str, **kwargs) -> bool:
        """更新自定义模板"""
        if template_id.startswith("builtin_"):
            raise ValueError("内置模板不能修改")

        update_fields = []
        update_values = []

        if "name" in kwargs:
            update_fields.append("name = ?")
            update_values.append(kwargs["name"])
        if "category" in kwargs:
            update_fields.append("category = ?")
            update_values.append(kwargs["category"])
        if "industry" in kwargs:
            update_fields.append("industry = ?")
            update_values.append(kwargs["industry"])
        if "config" in kwargs:
            update_fields.append("config_json = ?")
            update_values.append(json.dumps(kwargs["config"], ensure_ascii=False))
        if "description" in kwargs:
            update_fields.append("description = ?")
            update_values.append(kwargs["description"])
        if "sort_order" in kwargs:
            update_fields.append("sort_order = ?")
            update_values.append(kwargs["sort_order"])
        if "is_active" in kwargs:
            update_fields.append("is_active = ?")
            update_values.append(1 if kwargs["is_active"] else 0)

        if not update_fields:
            return False

        update_fields.append("updated_at = ?")
        update_values.append(datetime.now().isoformat())
        update_values.append(template_id)

        try:
            self._backend.execute(
                f"UPDATE templates SET {', '.join(update_fields)} WHERE id = ?",
                tuple(update_values)
            )
            self._backend.commit()
            self._backend.close()
            logger.info(f"更新模板: {template_id}")
            return True
        except Exception as e:
            self._backend.rollback()
            self._backend.close()
            logger.error(f"更新模板失败: {e}")
            raise

    def delete_template(self, template_id: str) -> bool:
        """删除自定义模板"""
        if template_id.startswith("builtin_"):
            raise ValueError("内置模板不能删除")

        try:
            self._backend.execute(
                "UPDATE templates SET is_active = 0 WHERE id = ?",
                (template_id,)
            )
            self._backend.commit()
            self._backend.close()
            logger.info(f"删除模板: {template_id}")
            return True
        except Exception as e:
            self._backend.rollback()
            self._backend.close()
            logger.error(f"删除模板失败: {e}")
            raise

    def duplicate_template(self, template_id: str, new_name: str) -> str:
        """复制模板"""
        source = self.get_template(template_id)
        if not source:
            raise ValueError(f"模板不存在: {template_id}")

        config = source.get("config", {})
        category = source.get("category", "analysis")
        industry = source.get("industry", "general")
        description = source.get("description", "")

        return self.create_template(
            name=new_name,
            config=config,
            category=category,
            industry=industry,
            description=f"复制自: {source.get('name', '')}\n{description}"
        )

    def detect_industry(self, text: str) -> tuple[str, Dict[str, Any]]:
        """检测文本所属行业，返回行业模板"""
        from app.core.prompt_loader import detect_industry

        industry_key, profile = detect_industry(text)
        template_id = f"builtin_{industry_key}"
        template = self._builtin_templates.get(template_id)

        if not template:
            template_id = "builtin_general"
            template = self._builtin_templates.get(template_id)

        return template_id, template

    def get_templates_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类获取模板"""
        all_templates = self.get_all_templates()
        return [t for t in all_templates if t.get("category") == category]

    def get_templates_by_industry(self, industry: str) -> List[Dict[str, Any]]:
        """按行业获取模板"""
        all_templates = self.get_all_templates()
        return [t for t in all_templates if t.get("industry") == industry]


_template_manager_instance = None


def get_template_manager() -> TemplateManager:
    """获取模板管理器实例"""
    global _template_manager_instance
    if _template_manager_instance is None:
        _template_manager_instance = TemplateManager()
    return _template_manager_instance
