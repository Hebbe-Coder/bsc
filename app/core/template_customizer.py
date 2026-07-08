"""
模板定制引擎 - TemplateCustomizer

根据用户偏好和输入动态生成个性化PRD模板：
1. 基于行业选择基础模板
2. 融合用户偏好调整模板结构
3. 使用LLM增强模板内容
4. 支持模板进化和学习

设计原则：
- 动态生成：根据用户输入自动调整模板
- 行业深度定制：每个行业有专属要素
- 用户定制：记住用户偏好
- LLM增强：使用LLM生成更智能的模板内容
"""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class TemplateCustomizer:
    """模板定制引擎"""
    
    def __init__(self):
        self._preference_service = None
    
    @property
    def preference_service(self):
        """懒加载用户偏好服务"""
        if self._preference_service is None:
            from app.services.user_preference_service import UserPreferenceService
            self._preference_service = UserPreferenceService()
        return self._preference_service
    
    def generate_custom_template(self, user_id: str, industry: str, 
                                 input_text: str) -> Dict[str, Any]:
        """
        生成个性化模板
        
        Args:
            user_id: 用户ID
            industry: 行业类型
            input_text: 用户输入文本
            
        Returns:
            个性化模板字典
        """
        base_template = self._get_industry_template(industry)
        
        preferences = self.preference_service.get_preferences(user_id)
        
        merged_template = self._merge_preferences(base_template, preferences)
        
        enhanced_template = self._llm_enhance_template(merged_template, input_text, industry)
        
        return enhanced_template
    
    def _get_industry_template(self, industry: str) -> Dict[str, Any]:
        """
        获取行业基础模板
        
        Args:
            industry: 行业类型
            
        Returns:
            基础模板
        """
        from app.engines.prd_analyzer import PRDTemplateManager
        
        template_key = PRDTemplateManager.recommend_template(f"行业：{industry}")
        template = PRDTemplateManager.get_template(template_key)
        
        if not template:
            template = PRDTemplateManager.get_template("general")
        
        return template.copy()
    
    def _merge_preferences(self, template: Dict[str, Any], 
                           preferences: Dict[str, Any]) -> Dict[str, Any]:
        """
        融合用户偏好到模板
        
        Args:
            template: 基础模板
            preferences: 用户偏好
            
        Returns:
            融合后的模板
        """
        merged = {**template}
        
        template_prefs = preferences.get("template", {})
        
        if "preferred_sections" in template_prefs:
            preferred_keys = set(template_prefs["preferred_sections"])
            merged["sections"] = [
                s for s in merged.get("sections", [])
                if s["key"] in preferred_keys
            ]
        
        if "section_order" in template_prefs:
            merged["sections"] = self._reorder_sections(
                merged.get("sections", []),
                template_prefs["section_order"]
            )
        
        if "default_template" in template_prefs:
            merged["_preferred_template_key"] = template_prefs["default_template"]
        
        format_prefs = preferences.get("format", {})
        if format_prefs:
            merged["_format_preferences"] = format_prefs
        
        style_prefs = preferences.get("style", {})
        if style_prefs:
            merged["_style_preferences"] = style_prefs
        
        return merged
    
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
    
    def _llm_enhance_template(self, template: Dict[str, Any], 
                               input_text: str, industry: str) -> Dict[str, Any]:
        """
        使用LLM增强模板
        
        Args:
            template: 基础模板
            input_text: 用户输入
            industry: 行业类型
            
        Returns:
            增强后的模板
        """
        try:
            from app.services.llm_service import LLMService
            
            llm_service = LLMService(provider="mock")
            
            system_prompt = """你是一个专业的PRD模板设计师。请根据用户输入和基础模板，生成一个个性化的PRD模板。

要求：
1. 根据用户输入动态调整章节内容和示例
2. 添加符合业务场景的具体示例
3. 保持模板结构清晰
4. 使用中文输出
5. 只输出JSON格式，不要包含其他文本

用户输入：{input_text}
行业：{industry}

基础模板结构：
{template_structure}

输出格式：
{
  "sections": [
    {
      "key": "章节key",
      "name": "章节名称",
      "required": true/false,
      "description": "章节描述",
      "tips": "填写提示",
      "example": "示例内容"
    }
  ],
  "title_suggestion": "建议的PRD标题",
  "additional_notes": "额外说明"
}"""
            
            template_structure = json.dumps({
                "sections": template.get("sections", []),
                "name": template.get("name"),
                "industry": template.get("industry"),
            }, ensure_ascii=False, indent=2)
            
            user_prompt = system_prompt.format(
                input_text=input_text,
                industry=industry,
                template_structure=template_structure
            )
            
            response = llm_service.chat(system_prompt, user_prompt)
            
            if isinstance(response, dict):
                enhanced_sections = response.get("sections", [])
                
                if enhanced_sections:
                    template["sections"] = enhanced_sections
                
                if "title_suggestion" in response:
                    template["_title_suggestion"] = response["title_suggestion"]
                
                if "additional_notes" in response:
                    template["_additional_notes"] = response["additional_notes"]
            
            logger.info(f"LLM enhanced template for industry: {industry}")
            
        except Exception as e:
            logger.debug(f"LLM enhance template failed: {e}")
        
        return template
    
    def create_prd_from_template(self, template: Dict[str, Any], 
                                 user_inputs: Dict[str, str]) -> str:
        """
        根据模板和用户输入创建PRD
        
        Args:
            template: 模板
            user_inputs: 用户输入（章节key -> 内容）
            
        Returns:
            PRD文本
        """
        sections = template.get("sections", [])
        
        prd_sections = []
        
        for section in sections:
            key = section["key"]
            name = section["name"]
            content = user_inputs.get(key, "")
            
            if content:
                prd_sections.append(f"""## {name}

{content}""")
            elif section.get("example"):
                prd_sections.append(f"""## {name}

{section["example"]}""")
        
        title = template.get("_title_suggestion", "产品PRD")
        
        prd_text = f"""# {title}

## 基本信息
- 行业：{template.get("industry", "通用")}
- 模板：{template.get("name", "自定义模板")}

{chr(10).join(prd_sections)}"""
        
        return prd_text
    
    def evolve_template(self, user_id: str, template_key: str, 
                        feedback: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据用户反馈进化模板
        
        Args:
            user_id: 用户ID
            template_key: 模板Key
            feedback: 用户反馈
            
        Returns:
            更新后的模板
        """
        rating = feedback.get("rating")
        comments = feedback.get("comments")
        sections_used = feedback.get("sections_used", [])
        industry = feedback.get("industry")
        
        if rating is not None:
            self.preference_service.learn_preference(user_id, "template_rating", {
                "template_key": template_key,
                "rating": rating,
                "industry": industry,
                "sections_used": sections_used,
            })
        
        if sections_used:
            for section_key in sections_used:
                self.preference_service.learn_preference(user_id, "add_section", {
                    "section_key": section_key,
                })
        
        if comments:
            logger.info(f"Template feedback: user={user_id}, template={template_key}, comments={comments}")
        
        return self.preference_service.get_personalized_template(user_id, industry)
    
    def get_template_with_examples(self, user_id: str, industry: str, 
                                   input_text: str) -> Dict[str, Any]:
        """
        获取带示例的个性化模板
        
        Args:
            user_id: 用户ID
            industry: 行业类型
            input_text: 用户输入文本
            
        Returns:
            带示例的模板
        """
        template = self.generate_custom_template(user_id, industry, input_text)
        
        template_with_examples = {**template}
        
        for section in template_with_examples.get("sections", []):
            if "example" not in section or not section["example"]:
                section["example"] = self._generate_section_example(
                    section["key"], 
                    section["name"], 
                    industry,
                    input_text
                )
        
        return template_with_examples
    
    def _generate_section_example(self, section_key: str, section_name: str, 
                                  industry: str, input_text: str) -> str:
        """
        生成章节示例
        
        Args:
            section_key: 章节Key
            section_name: 章节名称
            industry: 行业类型
            input_text: 用户输入
            
        Returns:
            示例文本
        """
        example_map = {
            "business_objectives": f"- 提升{industry}业务效率\n- 优化用户体验\n- 降低运营成本",
            "core_features": "- 核心功能模块1\n- 核心功能模块2\n- 核心功能模块3",
            "user_roles": "- 管理员：系统管理\n- 普通用户：日常操作\n- 运营人员：业务运营",
            "business_process": "描述核心业务流程...",
            "performance_requirements": "- 响应时间：< 2秒\n- QPS：> 1000\n- 可用性：99.9%",
            "non_functional_requirements": "- 安全合规要求\n- 数据加密\n- 系统扩展性",
            "risk_assessment": "- 技术风险：应对措施\n- 业务风险：应对措施\n- 市场风险：应对措施",
            "data_model": "描述核心数据实体和关系...",
            "api_design": "描述对外接口设计...",
            "release_plan": "- 第一阶段：基础功能\n- 第二阶段：高级功能\n- 第三阶段：优化迭代",
        }
        
        return example_map.get(section_key, "请根据实际情况填写。")


__all__ = ["TemplateCustomizer"]
