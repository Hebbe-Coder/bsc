"""
PRD Analyzer - PRD智能解析器

为产品经理设计的PRD输入优化工具：
1. PRD结构解析 - 提取业务目标、核心功能、性能要求等关键信息
2. 模板匹配 - 根据PRD内容推荐最合适的行业模板
3. 缺失项检测 - 检测PRD中缺失的关键信息
4. 智能补全建议 - 提供缺失信息的补全建议

设计原则：
- 零LLM依赖的快速解析模式（基于规则）
- 可选的LLM增强模式（更准确的语义理解）
"""
from __future__ import annotations
import re
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class PRDSection:
    """PRD章节定义"""
    
    def __init__(self, name: str, key: str, required: bool = False, 
                 patterns: List[str] = None, description: str = ""):
        self.name = name
        self.key = key
        self.required = required
        self.patterns = patterns or []
        self.description = description
        self.content = ""
        self.found = False
    
    def match(self, text: str) -> bool:
        """检查文本是否匹配章节模式"""
        for pattern in self.patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


class PRDAnalyzer:
    """PRD智能解析器"""
    
    SECTIONS = [
        PRDSection(
            name="业务目标",
            key="business_objectives",
            required=True,
            patterns=[
                r"业务目标", r"产品目标", r"目标", r"Objective", r"Goal",
                r"1\.\s*目标", r"1\.\s*业务", r"一、目标", r"第一章.*目标"
            ],
            description="产品要达成的核心业务目标和指标"
        ),
        PRDSection(
            name="核心功能",
            key="core_features",
            required=True,
            patterns=[
                r"核心功能", r"功能需求", r"功能列表", r"Features", r"功能模块",
                r"2\.\s*功能", r"二、功能", r"第二章.*功能"
            ],
            description="产品的主要功能模块和特性"
        ),
        PRDSection(
            name="用户角色",
            key="user_roles",
            required=False,
            patterns=[
                r"用户角色", r"角色", r"用户画像", r"Persona", r"User Role",
                r"角色定义", r"干系人"
            ],
            description="系统涉及的用户角色和权限"
        ),
        PRDSection(
            name="性能要求",
            key="performance_requirements",
            required=False,
            patterns=[
                r"性能要求", r"性能指标", r"响应时间", r"Performance", r"QPS",
                r"SLA", r"可用性", r"吞吐量"
            ],
            description="系统的性能指标和可用性要求"
        ),
        PRDSection(
            name="非功能需求",
            key="non_functional_requirements",
            required=False,
            patterns=[
                r"非功能需求", r"NFR", r"安全", r"合规", r"扩展性",
                r"可维护性", r"兼容性", r"数据安全"
            ],
            description="安全、合规、扩展性等非功能需求"
        ),
        PRDSection(
            name="业务流程",
            key="business_process",
            required=False,
            patterns=[
                r"业务流程", r"流程图", r"Process", r"Workflow", r"流程说明",
                r"操作流程", r"处理流程"
            ],
            description="核心业务流程的描述"
        ),
        PRDSection(
            name="数据模型",
            key="data_model",
            required=False,
            patterns=[
                r"数据模型", r"数据库", r"Data Model", r"实体", r"数据表",
                r"数据结构", r"数据字典"
            ],
            description="核心数据实体和关系"
        ),
        PRDSection(
            name="接口设计",
            key="api_design",
            required=False,
            patterns=[
                r"接口设计", r"API", r"API设计", r"接口列表", r"接口规范",
                r"RESTful", r"接口说明"
            ],
            description="对外接口设计规范"
        ),
        PRDSection(
            name="上线计划",
            key="release_plan",
            required=False,
            patterns=[
                r"上线计划", r"时间计划", r"Release", r"里程碑", r"迭代计划",
                r"开发计划", r"项目计划"
            ],
            description="项目时间计划和里程碑"
        ),
        PRDSection(
            name="风险评估",
            key="risk_assessment",
            required=False,
            patterns=[
                r"风险", r"风险评估", r"Risk", r"风险分析", r"潜在风险"
            ],
            description="项目风险和应对措施"
        ),
    ]
    
    INDUSTRY_KEYWORDS = {
        "金融": ["银行", "支付", "保险", "理财", "证券", "基金", "贷款", 
                "投资", "股票", "债券", "风控", "征信", "结算"],
        "医疗": ["医院", "医生", "病人", "药品", "诊断", "挂号", "诊疗",
                "病历", "医保", "体检", "健康", "医疗"],
        "零售": ["电商", "购物", "商品", "订单", "物流", "库存", "购物车",
                "优惠券", "促销", "会员", "店铺", "供应链"],
        "制造": ["生产", "工厂", "供应链", "质检", "仓库", "工艺", "设备",
                "产能", "工单", "装配", "零部件"],
        "教育": ["学校", "课程", "学生", "老师", "学习", "考试", "作业",
                "在线教育", "MOOC", "题库", "培训"],
        "内容": ["视频", "图片", "文本", "审核", "安全", "媒体", "直播",
                "短视频", "社区", "论坛", "UGC"],
        "物流": ["快递", "配送", "运输", "仓储", "货运", "报关", "分拣",
                "冷链", "干线", "末端"],
        "人力": ["招聘", "员工", "绩效", "薪酬", "考勤", "HR", "入职",
                "离职", "培训", "福利", "人才"],
        "企业": ["OA", "ERP", "CRM", "SaaS", "协作", "办公", "管理",
                "数字化", "信息化", "业务系统"],
        "营销": ["广告", "推广", "品牌", "渠道", "获客", "投放", "转化",
                "KOL", "裂变", "私域"],
    }
    
    def __init__(self):
        self._sections = {s.key: s for s in self.SECTIONS}
    
    def analyze(self, prd_text: str, use_llm: bool = False) -> Dict[str, Any]:
        """
        解析PRD文档
        
        Args:
            prd_text: PRD文本内容
            use_llm: 是否使用LLM增强解析（更准确但耗时更长）
        
        Returns:
            dict: 解析结果，包含sections、missing、industry、recommendations
        """
        sections = self._parse_sections(prd_text)
        industry = self._detect_industry(prd_text)
        missing = self._find_missing_sections(sections)
        recommendations = self._generate_recommendations(sections, missing, industry)
        
        result = {
            "sections": {k: {"name": v.name, "found": v.found, "content": v.content[:500]} 
                         for k, v in sections.items()},
            "industry": industry,
            "missing_sections": missing,
            "recommendations": recommendations,
            "prd_quality": self._calculate_quality(sections),
            "estimated_length": len(prd_text),
        }
        
        if use_llm:
            llm_enhanced = self._llm_enhance(prd_text, result)
            result.update(llm_enhanced)
        
        return result
    
    def _parse_sections(self, prd_text: str) -> Dict[str, PRDSection]:
        """解析PRD章节"""
        lines = prd_text.split('\n')
        sections = {s.key: s.__class__(s.name, s.key, s.required, s.patterns, s.description) 
                    for s in self._sections.values()}
        
        current_section = None
        current_content = []
        
        for line in lines:
            matched = False
            for section in sections.values():
                if section.match(line):
                    if current_section:
                        sections[current_section].content = '\n'.join(current_content).strip()
                        sections[current_section].found = True
                    
                    current_section = section.key
                    current_content = [line]
                    matched = True
                    break
            
            if not matched and current_section:
                current_content.append(line)
        
        if current_section:
            sections[current_section].content = '\n'.join(current_content).strip()
            sections[current_section].found = True
        
        return sections
    
    def _detect_industry(self, prd_text: str) -> str:
        """检测行业类型"""
        prd_lower = prd_text.lower()
        
        for industry, keywords in self.INDUSTRY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in prd_lower:
                    return industry
        
        return "通用"
    
    def _find_missing_sections(self, sections: Dict[str, PRDSection]) -> List[str]:
        """查找缺失的必要章节"""
        missing = []
        for key, section in sections.items():
            if section.required and not section.found:
                missing.append(key)
        return missing
    
    def _generate_recommendations(self, sections: Dict[str, PRDSection], 
                                  missing: List[str], industry: str) -> List[Dict[str, str]]:
        """生成补全建议"""
        recommendations = []
        
        recommendation_map = {
            "business_objectives": {
                "title": "补充业务目标",
                "suggestion": "建议明确产品的核心业务目标，例如：提升用户转化率、降低运营成本、提高系统稳定性等，并设定可量化的指标。",
            },
            "core_features": {
                "title": "补充核心功能",
                "suggestion": "建议列出产品的主要功能模块，每个功能模块说明核心价值和使用场景。",
            },
            "user_roles": {
                "title": "补充用户角色",
                "suggestion": "建议定义系统涉及的用户角色，包括管理员、普通用户、运营人员等，并说明各角色的权限范围。",
            },
            "performance_requirements": {
                "title": "补充性能要求",
                "suggestion": "建议明确系统的性能指标，例如：响应时间<2秒、QPS>1000、可用性99.9%等。",
            },
            "business_process": {
                "title": "补充业务流程",
                "suggestion": "建议描述核心业务流程，包括用户操作路径、系统处理逻辑和异常处理流程。",
            },
        }
        
        for key in missing:
            if key in recommendation_map:
                recommendations.append(recommendation_map[key])
        
        if industry != "通用":
            recommendations.append({
                "title": f"参考{industry}行业最佳实践",
                "suggestion": f"建议参考{industry}行业的标准PRD结构和关键要素，确保文档的专业性和完整性。",
            })
        
        return recommendations
    
    def _calculate_quality(self, sections: Dict[str, PRDSection]) -> float:
        """计算PRD质量分数"""
        total = len(self.SECTIONS)
        found = sum(1 for s in sections.values() if s.found)
        return round((found / total) * 100, 1)
    
    def _llm_enhance(self, prd_text: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM增强解析结果"""
        try:
            from app.services.llm_service import LLMService
            
            llm_service = LLMService()
            system_prompt = """你是一个专业的PRD分析助手。请分析以下PRD文档，提取关键信息并给出专业建议。
            
输出格式要求：
{
  "key_objectives": ["目标1", "目标2"],
  "key_features": ["功能1", "功能2"],
  "key_roles": ["角色1", "角色2"],
  "potential_risks": ["风险1", "风险2"],
  "improvement_suggestions": ["建议1", "建议2"]
}
"""
            
            response = llm_service.chat(system_prompt, prd_text[:3000])
            
            if isinstance(response, dict):
                return {
                    "llm_enhanced": True,
                    "key_objectives": response.get("key_objectives", []),
                    "key_features": response.get("key_features", []),
                    "key_roles": response.get("key_roles", []),
                    "potential_risks": response.get("potential_risks", []),
                    "improvement_suggestions": response.get("improvement_suggestions", []),
                }
        except Exception as e:
            logger.debug(f"LLM enhance failed: {e}")
        
        return {"llm_enhanced": False}


class PRDTemplateManager:
    """PRD模板管理器"""
    
    TEMPLATES = {
        "general": {
            "name": "通用PRD模板",
            "industry": "通用",
            "description": "适用于各类产品的标准PRD模板",
            "sections": [
                {"key": "business_objectives", "name": "业务目标", "required": True},
                {"key": "core_features", "name": "核心功能", "required": True},
                {"key": "user_roles", "name": "用户角色", "required": False},
                {"key": "business_process", "name": "业务流程", "required": False},
                {"key": "performance_requirements", "name": "性能要求", "required": False},
                {"key": "non_functional_requirements", "name": "非功能需求", "required": False},
            ],
            "example": """# 产品名称PRD

## 一、业务目标
- 目标1：描述要达成的业务指标
- 目标2：描述要达成的业务指标

## 二、核心功能
### 功能模块1
- 功能点1：详细描述
- 功能点2：详细描述

### 功能模块2
- 功能点1：详细描述

## 三、用户角色
- 角色1：职责描述
- 角色2：职责描述

## 四、业务流程
描述核心业务流程...

## 五、性能要求
- 响应时间：< 2秒
- QPS：> 1000
- 可用性：99.9%
""",
        },
        "finance": {
            "name": "金融行业PRD模板",
            "industry": "金融",
            "description": "适用于银行、支付、保险等金融产品",
            "sections": [
                {"key": "business_objectives", "name": "业务目标", "required": True},
                {"key": "core_features", "name": "核心功能", "required": True},
                {"key": "risk_assessment", "name": "风险评估", "required": True},
                {"key": "user_roles", "name": "用户角色", "required": False},
                {"key": "business_process", "name": "业务流程", "required": False},
                {"key": "non_functional_requirements", "name": "合规要求", "required": True},
                {"key": "data_model", "name": "数据模型", "required": False},
            ],
            "example": """# 金融产品PRD

## 一、业务目标
- 提升交易成功率至99.9%
- 降低欺诈风险损失率至0.01%

## 二、核心功能
### 交易处理
- 支付接口：支持多种支付渠道
- 清算结算：自动清算和结算流程

### 风控模块
- 实时风控：毫秒级风险识别
- 反欺诈：多维度欺诈检测

## 三、风险评估
- 信用风险：评估方法和阈值
- 操作风险：应急预案

## 四、合规要求
- 监管合规：符合行业监管要求
- 数据安全：加密存储和传输

## 五、性能要求
- 交易响应：< 500ms
- 系统可用性：99.99%
""",
        },
        "retail": {
            "name": "零售电商PRD模板",
            "industry": "零售",
            "description": "适用于电商平台、零售系统",
            "sections": [
                {"key": "business_objectives", "name": "业务目标", "required": True},
                {"key": "core_features", "name": "核心功能", "required": True},
                {"key": "user_roles", "name": "用户角色", "required": False},
                {"key": "business_process", "name": "业务流程", "required": False},
                {"key": "performance_requirements", "name": "性能要求", "required": False},
                {"key": "api_design", "name": "接口设计", "required": False},
            ],
            "example": """# 电商平台PRD

## 一、业务目标
- 提升用户转化率至5%
- 优化订单履约效率

## 二、核心功能
### 商品管理
- 商品发布：支持多规格商品
- 库存管理：实时库存同步

### 订单系统
- 订单创建：支持多种支付方式
- 订单履约：自动化配送流程

### 用户中心
- 会员体系：积分和等级制度
- 优惠券：营销活动支持

## 三、业务流程
用户浏览 → 加入购物车 → 下单支付 → 商家发货 → 用户收货

## 四、性能要求
- 页面响应：< 1秒
- 峰值QPS：> 10000
""",
        },
        "healthcare": {
            "name": "医疗健康PRD模板",
            "industry": "医疗",
            "description": "适用于医疗健康产品",
            "sections": [
                {"key": "business_objectives", "name": "业务目标", "required": True},
                {"key": "core_features", "name": "核心功能", "required": True},
                {"key": "user_roles", "name": "用户角色", "required": True},
                {"key": "non_functional_requirements", "name": "合规要求", "required": True},
                {"key": "data_model", "name": "数据模型", "required": False},
            ],
            "example": """# 医疗健康产品PRD

## 一、业务目标
- 提升患者就医体验
- 优化医疗资源配置

## 二、核心功能
### 在线挂号
- 科室选择：支持多科室挂号
- 医生预约：选择医生和时间

### 电子病历
- 病历管理：电子病历的创建和查看
- 数据共享：跨机构数据共享

### 在线问诊
- 图文问诊：文字和图片咨询
- 视频问诊：实时视频咨询

## 三、用户角色
- 患者：使用服务的用户
- 医生：提供医疗服务
- 管理员：系统管理

## 四、合规要求
- 医疗数据安全：符合医疗数据规范
- 隐私保护：患者隐私保护措施
""",
        },
        "enterprise": {
            "name": "企业管理PRD模板",
            "industry": "企业",
            "description": "适用于企业级SaaS产品",
            "sections": [
                {"key": "business_objectives", "name": "业务目标", "required": True},
                {"key": "core_features", "name": "核心功能", "required": True},
                {"key": "user_roles", "name": "用户角色", "required": True},
                {"key": "business_process", "name": "业务流程", "required": False},
                {"key": "api_design", "name": "接口设计", "required": False},
                {"key": "release_plan", "name": "上线计划", "required": False},
            ],
            "example": """# 企业管理系统PRD

## 一、业务目标
- 提升企业办公效率30%
- 实现数字化转型

## 二、核心功能
### 协同办公
- 任务管理：任务分配和追踪
- 文档协作：多人实时协作

### 审批流程
- 流程设计：自定义审批流程
- 移动端审批：随时随地审批

### 数据分析
- 数据报表：多维度数据分析
- 可视化：图表展示

## 三、用户角色
- 员工：日常办公
- 部门经理：团队管理
- 管理员：系统配置

## 四、性能要求
- 并发用户：> 1000人
- 响应时间：< 1.5秒
""",
        },
    }
    
    @classmethod
    def get_template(cls, template_key: str) -> Optional[Dict[str, Any]]:
        """获取模板"""
        return cls.TEMPLATES.get(template_key)
    
    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        """获取所有模板列表"""
        return [
            {
                "key": key,
                "name": template["name"],
                "industry": template["industry"],
                "description": template["description"],
                "section_count": len(template["sections"]),
            }
            for key, template in cls.TEMPLATES.items()
        ]
    
    @classmethod
    def recommend_template(cls, prd_text: str) -> str:
        """根据PRD内容推荐模板"""
        analyzer = PRDAnalyzer()
        industry = analyzer._detect_industry(prd_text)
        
        for key, template in cls.TEMPLATES.items():
            if template["industry"] == industry:
                return key
        
        return "general"
    
    @classmethod
    def generate_prd_guide(cls, template_key: str) -> Dict[str, Any]:
        """生成PRD填写指南"""
        template = cls.get_template(template_key)
        if not template:
            return {}
        
        guide = {
            "template_key": template_key,
            "template_name": template["name"],
            "industry": template["industry"],
            "sections": [],
            "example": template["example"],
        }
        
        for section in template["sections"]:
            analyzer = PRDAnalyzer()
            section_def = analyzer._sections.get(section["key"])
            
            guide["sections"].append({
                "key": section["key"],
                "name": section["name"],
                "required": section["required"],
                "description": section_def.description if section_def else "",
                "tips": cls._get_section_tips(section["key"]),
            })
        
        return guide
    
    @staticmethod
    def _get_section_tips(section_key: str) -> str:
        """获取章节填写提示"""
        tips_map = {
            "business_objectives": "请明确产品要达成的核心业务目标，建议使用SMART原则（具体、可衡量、可实现、相关、有时限）。",
            "core_features": "请列出产品的主要功能模块，每个功能模块说明核心价值和使用场景。",
            "user_roles": "请定义系统涉及的用户角色，包括管理员、普通用户、运营人员等，并说明各角色的权限范围。",
            "business_process": "请描述核心业务流程，包括用户操作路径、系统处理逻辑和异常处理流程。",
            "performance_requirements": "请明确系统的性能指标，例如：响应时间、QPS、可用性等。",
            "non_functional_requirements": "请描述安全、合规、扩展性等非功能需求，特别是行业合规要求。",
            "risk_assessment": "请识别项目潜在风险，并给出应对措施和应急预案。",
            "data_model": "请描述核心数据实体和关系，建议使用ER图辅助说明。",
            "api_design": "请描述对外接口设计规范，包括接口地址、请求参数、返回格式等。",
            "release_plan": "请制定项目时间计划和里程碑，包括各阶段的交付物和验收标准。",
        }
        return tips_map.get(section_key, "请根据实际情况填写。")


__all__ = ["PRDAnalyzer", "PRDTemplateManager"]
