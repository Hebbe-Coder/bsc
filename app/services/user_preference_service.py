"""
用户偏好服务 - UserPreferenceService

管理用户偏好的高级服务：
1. 获取/设置用户偏好
2. 学习用户使用习惯
3. 预测用户偏好
4. 管理用户模板偏好
5. 提供个性化建议

设计原则：
- 基于使用频率的偏好学习
- 支持多种偏好类别（template/format/style/behavior）
- 与SQLite数据库集成
- 提供预测API
"""
from __future__ import annotations
import logging
from typing import Dict, Any, List

from app.core.preference_db import get_preference_db

logger = logging.getLogger(__name__)


class UserPreferenceService:
    """用户偏好服务"""
    
    DEFAULT_PREFERENCES = {
        "template": {
            "preferred_sections": ["business_objectives", "core_features", "user_roles"],
            "default_template": "general",
            "section_order": ["business_objectives", "core_features", "user_roles", 
                             "business_process", "performance_requirements", 
                             "non_functional_requirements", "risk_assessment",
                             "data_model", "api_design", "release_plan"],
        },
        "format": {
            "output_format": "html",
            "include_visuals": True,
            "language": "zh",
        },
        "style": {
            "color_scheme": "professional",
            "font_size": "medium",
            "layout": "modern",
        },
        "behavior": {
            "auto_save": True,
            "auto_complete": True,
            "suggestion_enabled": True,
            "default_depth": "medium",
        },
    }
    
    def __init__(self):
        self.db = get_preference_db()
    
    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户所有偏好
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户偏好字典
        """
        stored = self.db.get_all_preferences(user_id)
        
        preferences = {}
        for category, defaults in self.DEFAULT_PREFERENCES.items():
            key = f"pref_{category}"
            stored_category = stored.get(key, defaults)
            merged = {**defaults, **stored_category} if isinstance(stored_category, dict) else defaults
            preferences[category] = merged
        
        return preferences
    
    def get_preference(self, user_id: str, category: str, key: str = None) -> Any:
        """
        获取特定偏好
        
        Args:
            user_id: 用户ID
            category: 偏好类别（template/format/style/behavior）
            key: 偏好键（可选）
            
        Returns:
            偏好值
        """
        preferences = self.get_preferences(user_id)
        category_prefs = preferences.get(category, {})
        
        if key:
            return category_prefs.get(key)
        return category_prefs
    
    def set_preference(self, user_id: str, category: str, key: str, value: Any) -> bool:
        """
        设置用户偏好
        
        Args:
            user_id: 用户ID
            category: 偏好类别
            key: 偏好键
            value: 偏好值
            
        Returns:
            是否成功
        """
        preferences = self.get_preferences(user_id)
        
        if category not in preferences:
            preferences[category] = {}
        
        preferences[category][key] = value
        
        return self.db.set_preference(user_id, f"pref_{category}", preferences[category], category)
    
    def set_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """
        批量设置用户偏好
        
        Args:
            user_id: 用户ID
            preferences: 偏好字典
            
        Returns:
            是否成功
        """
        success = True
        for category, values in preferences.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    if not self.set_preference(user_id, category, key, value):
                        success = False
            else:
                if not self.db.set_preference(user_id, f"pref_{category}", values, category):
                    success = False
        
        return success
    
    def reset_preferences(self, user_id: str) -> bool:
        """
        重置用户偏好为默认值
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功
        """
        try:
            preferences = self.db.get_all_preferences(user_id)
            for key in preferences.keys():
                if key.startswith("pref_"):
                    self.db.delete_preference(user_id, key)
            return True
        except Exception as e:
            logger.error(f"Failed to reset preferences: {e}")
            return False
    
    def learn_preference(self, user_id: str, action_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        学习用户偏好
        
        Args:
            user_id: 用户ID
            action_type: 操作类型（select_template, add_section, export等）
            data: 操作数据
            
        Returns:
            预测的下次偏好
        """
        logger.info(f"Learning preference: user={user_id}, action={action_type}, data={data}")
        
        if action_type == "select_template":
            self._learn_template_selection(user_id, data)
        elif action_type == "add_section":
            self._learn_section_preference(user_id, data)
        elif action_type == "export":
            self._learn_export_format(user_id, data)
        elif action_type == "dialog_depth":
            self._learn_dialog_depth(user_id, data)
        elif action_type == "template_rating":
            self._learn_template_rating(user_id, data)
        
        return self.predict_next_preference(user_id)
    
    def _learn_template_selection(self, user_id: str, data: Dict[str, Any]):
        """学习模板选择偏好"""
        template_key = data.get("template_key")
        industry = data.get("industry")
        
        if template_key:
            current_prefs = self.get_preference(user_id, "template")
            current_prefs["default_template"] = template_key
            
            self.set_preferences(user_id, {"template": current_prefs})
            
            if industry:
                self.db.record_template_usage(user_id, template_key, industry, 
                                              data.get("sections", []))
    
    def _learn_section_preference(self, user_id: str, data: Dict[str, Any]):
        """学习章节偏好"""
        section_key = data.get("section_key")
        
        if section_key:
            current_prefs = self.get_preference(user_id, "template")
            preferred_sections = current_prefs.get("preferred_sections", [])
            
            if section_key not in preferred_sections:
                preferred_sections.insert(0, section_key)
                if len(preferred_sections) > 10:
                    preferred_sections = preferred_sections[:10]
            
            current_prefs["preferred_sections"] = preferred_sections
            self.set_preferences(user_id, {"template": current_prefs})
    
    def _learn_export_format(self, user_id: str, data: Dict[str, Any]):
        """学习导出格式偏好"""
        export_format = data.get("format")
        
        if export_format:
            current_prefs = self.get_preference(user_id, "format")
            current_prefs["output_format"] = export_format
            
            self.set_preferences(user_id, {"format": current_prefs})
    
    def _learn_dialog_depth(self, user_id: str, data: Dict[str, Any]):
        """学习对话深度偏好"""
        depth = data.get("depth")
        
        if depth:
            current_prefs = self.get_preference(user_id, "behavior")
            current_prefs["default_depth"] = depth
            
            self.set_preferences(user_id, {"behavior": current_prefs})
            
            self.db.update_user(user_id, default_depth=depth)
    
    def _learn_template_rating(self, user_id: str, data: Dict[str, Any]):
        """学习模板评分"""
        template_key = data.get("template_key")
        rating = data.get("rating")
        industry = data.get("industry")
        sections_used = data.get("sections_used", [])
        
        if template_key and rating:
            self.db.record_template_usage(user_id, template_key, industry, 
                                          sections_used, rating)
    
    def predict_next_preference(self, user_id: str) -> Dict[str, Any]:
        """
        预测用户下一次的偏好
        
        Args:
            user_id: 用户ID
            
        Returns:
            预测的偏好
        """
        preferences = self.get_preferences(user_id)
        
        usage_history = self.db.get_template_usage(user_id, limit=5)
        
        if usage_history:
            most_used_template = usage_history[0]["template_key"]
            preferences["template"]["default_template"] = most_used_template
        
        return preferences
    
    def recommend_template(self, user_id: str, industry: str = None) -> str:
        """
        推荐模板
        
        Args:
            user_id: 用户ID
            industry: 行业类型（可选）
            
        Returns:
            推荐的模板Key
        """
        preferences = self.get_preferences(user_id)
        default_template = preferences["template"]["default_template"]
        
        if industry:
            from app.engines.prd_analyzer import PRDTemplateManager
            recommended_by_industry = PRDTemplateManager.recommend_template(f"行业：{industry}")
            
            if recommended_by_industry != "general":
                usage_history = self.db.get_template_usage(user_id, limit=10)
                
                industry_usages = [u for u in usage_history if u["industry"] == industry]
                
                if industry_usages:
                    return industry_usages[0]["template_key"]
                
                return recommended_by_industry
        
        return default_template
    
    def get_personalized_template(self, user_id: str, industry: str = None) -> Dict[str, Any]:
        """
        获取个性化模板
        
        Args:
            user_id: 用户ID
            industry: 行业类型（可选）
            
        Returns:
            个性化模板
        """
        from app.engines.prd_analyzer import PRDTemplateManager
        
        template_key = self.recommend_template(user_id, industry)
        base_template = PRDTemplateManager.get_template(template_key)
        
        if not base_template:
            base_template = PRDTemplateManager.get_template("general")
        
        preferences = self.get_preferences(user_id)
        template_prefs = preferences["template"]
        
        personalized_template = {**base_template}
        
        if "section_order" in template_prefs:
            personalized_template["sections"] = self._reorder_sections(
                base_template.get("sections", []),
                template_prefs["section_order"]
            )
        
        if "preferred_sections" in template_prefs:
            preferred_keys = set(template_prefs["preferred_sections"])
            personalized_template["sections"] = [
                s for s in personalized_template["sections"]
                if s["key"] in preferred_keys
            ]
        
        return personalized_template
    
    def _reorder_sections(self, sections: List[Dict[str, Any]], 
                          order: List[str]) -> List[Dict[str, Any]]:
        """
        按偏好顺序重新排列章节
        
        Args:
            sections: 章节列表
            order: 偏好顺序
            
        Returns:
            重新排序后的章节列表
        """
        key_to_section = {s["key"]: s for s in sections}
        
        ordered = []
        for key in order:
            if key in key_to_section:
                ordered.append(key_to_section[key])
        
        for section in sections:
            if section["key"] not in order:
                ordered.append(section)
        
        return ordered
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户完整画像
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户画像
        """
        user = self.db.get_user(user_id)
        preferences = self.get_preferences(user_id)
        recent_sessions = self.db.get_user_dialog_sessions(user_id, limit=5)
        template_usage = self.db.get_template_usage(user_id, limit=5)
        
        return {
            "user_id": user_id,
            "name": user.get("name") if user else None,
            "email": user.get("email") if user else None,
            "default_depth": user.get("default_depth") if user else "medium",
            "preferences": preferences,
            "recent_sessions": recent_sessions,
            "template_usage": template_usage,
        }


__all__ = ["UserPreferenceService"]
