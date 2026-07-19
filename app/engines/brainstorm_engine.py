"""
Brainstorm Engine - 头脑风暴引擎

支持创意生成、思维导图构建和创新方案探索：
1. 创意生成：基于业务领域和问题生成创新想法
2. 链式头脑风暴：多轮迭代，逐步深化想法
3. 思维导图：生成结构化的思维导图数据
4. 创意评价：对生成的创意进行评分和排序
5. 方案综合：将多个创意整合成完整方案

头脑风暴模式：
- divergent: 发散思维模式，生成尽可能多的想法
- convergent: 收敛思维模式，筛选和优化想法
- hybrid: 混合模式，先发散后收敛
"""
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.enums import BrainstormMode

logger = logging.getLogger(__name__)


class BrainstormEngine:
    """头脑风暴引擎"""
    
    BRAINSTORM_PROMPTS = {
        "divergent": {
            "system": """你是一个创意专家，擅长在给定业务领域内激发创新想法。
            请基于用户的问题和背景，生成尽可能多的创意解决方案。
            要求：
            1. 想法要新颖、独特，不拘泥于传统思维
            2. 覆盖不同维度和角度
            3. 每个想法都要有具体的实施方向
            4. 输出格式为JSON数组""",
            "user": """业务领域：{business_domain}
            问题描述：{problem}
            背景信息：{context}
            
            请生成{num_ideas}个创意解决方案，每个方案包含：
            - idea: 创意描述
            - category: 分类（如：技术创新、流程优化、商业模式、用户体验、运营策略）
            - impact: 影响力评估（高/中/低）
            - feasibility: 可行性评估（高/中/低）
            - keywords: 关键词列表
            - description: 详细描述
            - implementation_steps: 实施步骤要点""",
        },
        "convergent": {
            "system": """你是一个战略分析师，擅长评估和优化创意方案。
            请对给定的创意进行深入分析，筛选出最有价值的方案，并提出优化建议。
            要求：
            1. 基于数据和逻辑进行评估
            2. 给出具体的优化方向
            3. 输出格式为JSON数组""",
            "user": """业务领域：{business_domain}
            原始创意列表：{ideas}
            
            请对这些创意进行评估和优化：
            1. 筛选出Top {top_n}个最有价值的创意
            2. 对每个创意进行评分（1-10分）
            3. 提出具体的优化建议
            4. 输出格式为JSON数组""",
        },
        "mindmap": {
            "system": """你是一个思维导图专家，擅长将复杂概念结构化展示。
            请基于用户的主题生成清晰的思维导图结构。
            要求：
            1. 层次分明，逻辑清晰
            2. 覆盖主要分支和子分支
            3. 输出格式为JSON结构""",
            "user": """主题：{topic}
            业务领域：{business_domain}
            
            请生成一个完整的思维导图，包含：
            - 中心主题
            - 主要分支（至少4个）
            - 每个分支下的子节点
            - 关键字和说明
            
            输出格式：
            {{
                "center": "中心主题",
                "branches": [
                    {{
                        "name": "分支名称",
                        "description": "分支描述",
                        "children": [
                            {{"name": "子节点", "keywords": ["关键词1", "关键词2"]}}
                        ]
                    }}
                ]
            }}""",
        },
        "problem_analysis": {
            "system": """你是一个问题分析专家，擅长深入剖析问题本质。
            请使用多种分析方法对问题进行全面分析。
            要求：
            1. 使用结构化分析方法（如5W1H、鱼骨图、SWOT等）
            2. 找出根本原因
            3. 提出针对性的解决方案方向""",
            "user": """问题：{problem}
            业务领域：{business_domain}
            
            请进行全面的问题分析，输出JSON格式：
            {{
                "5w1h": {{
                    "what": "...",
                    "why": "...",
                    "where": "...",
                    "when": "...",
                    "who": "...",
                    "how": "..."
                }},
                "root_causes": ["原因1", "原因2", ...],
                "impact_analysis": [...],
                "solution_directions": [...]
            }}""",
        },
    }

    def __init__(self, llm_service=None):
        self._llm_service = llm_service

    def _get_llm_service(self):
        if self._llm_service is None:
            from app.services.llm_service import get_llm_service
            self._llm_service = get_llm_service()
        return self._llm_service

    def generate_ideas(self, business_domain: str, problem: str, 
                      context: str = "", num_ideas: int = 10, 
                      mode: str = "divergent") -> Dict[str, Any]:
        """
        生成创意想法
        
        Args:
            business_domain: 业务领域
            problem: 问题描述
            context: 背景信息
            num_ideas: 生成数量
            mode: 模式（divergent/convergent）
        
        Returns:
            包含创意列表和元数据的字典
        """
        llm = self._get_llm_service()
        prompt_config = self.BRAINSTORM_PROMPTS.get(mode, self.BRAINSTORM_PROMPTS["divergent"])
        
        user_prompt = prompt_config["user"].format(
            business_domain=business_domain,
            problem=problem,
            context=context,
            num_ideas=num_ideas,
        )
        
        response = llm.chat(
            system_prompt=prompt_config["system"],
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=4000,
        )
        
        ideas = self._parse_response(response)
        
        return {
            "task_id": str(uuid.uuid4()),
            "generated_at": datetime.now().isoformat(),
            "business_domain": business_domain,
            "problem": problem,
            "mode": mode,
            "total_ideas": len(ideas),
            "ideas": ideas,
            "categories": self._extract_categories(ideas),
            "impact_distribution": self._calculate_distribution(ideas, "impact"),
            "feasibility_distribution": self._calculate_distribution(ideas, "feasibility"),
        }

    def chain_brainstorm(self, business_domain: str, problem: str, 
                        context: str = "", rounds: int = 3, 
                        num_ideas_per_round: int = 8) -> Dict[str, Any]:
        """
        链式头脑风暴 - 多轮迭代生成创意
        
        Args:
            business_domain: 业务领域
            problem: 问题描述
            context: 背景信息
            rounds: 迭代轮数
            num_ideas_per_round: 每轮生成数量
        
        Returns:
            包含多轮创意的完整结果
        """
        results = {
            "task_id": str(uuid.uuid4()),
            "generated_at": datetime.now().isoformat(),
            "business_domain": business_domain,
            "problem": problem,
            "rounds": rounds,
            "round_results": [],
            "final_summary": None,
        }
        
        accumulated_ideas = []
        
        for round_num in range(rounds):
            round_context = context
            if accumulated_ideas:
                round_context += f"\n\n已有创意：{json.dumps(accumulated_ideas[:5], ensure_ascii=False)}"
            
            round_result = self.generate_ideas(
                business_domain=business_domain,
                problem=problem,
                context=round_context,
                num_ideas=num_ideas_per_round,
                mode="divergent",
            )
            
            round_result["round"] = round_num + 1
            results["round_results"].append(round_result)
            accumulated_ideas.extend(round_result["ideas"])
        
        results["total_ideas"] = len(accumulated_ideas)
        
        if accumulated_ideas:
            convergence_result = self.converge_ideas(
                business_domain=business_domain,
                ideas=accumulated_ideas,
                top_n=5,
            )
            results["final_summary"] = convergence_result
        
        return results

    def converge_ideas(self, business_domain: str, ideas: List[Dict[str, Any]],
                      top_n: int = 5) -> Dict[str, Any]:
        """
        收敛创意 - 筛选和优化最佳创意
        
        Args:
            business_domain: 业务领域
            ideas: 创意列表
            top_n: 筛选数量
        
        Returns:
            筛选和优化后的结果
        """
        llm = self._get_llm_service()
        prompt_config = self.BRAINSTORM_PROMPTS["convergent"]
        
        ideas_json = json.dumps(ideas, ensure_ascii=False)
        user_prompt = prompt_config["user"].format(
            business_domain=business_domain,
            ideas=ideas_json,
            top_n=top_n,
        )
        
        response = llm.chat(
            system_prompt=prompt_config["system"],
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=3000,
        )
        
        result = self._parse_response(response)
        
        return {
            "top_ideas": result[:top_n] if isinstance(result, list) else result,
            "optimization_suggestions": self._extract_suggestions(result),
        }

    def generate_mindmap(self, topic: str, business_domain: str = "") -> Dict[str, Any]:
        """
        生成思维导图数据
        
        Args:
            topic: 中心主题
            business_domain: 业务领域
        
        Returns:
            思维导图结构数据
        """
        llm = self._get_llm_service()
        prompt_config = self.BRAINSTORM_PROMPTS["mindmap"]
        
        user_prompt = prompt_config["user"].format(
            topic=topic,
            business_domain=business_domain,
        )
        
        response = llm.chat(
            system_prompt=prompt_config["system"],
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=3000,
        )
        
        mindmap = self._parse_response(response)
        
        if isinstance(mindmap, list):
            mindmap = mindmap[0] if mindmap else {}
        
        if not isinstance(mindmap, dict):
            mindmap = {}
        
        return {
            "topic": topic,
            "business_domain": business_domain,
            "generated_at": datetime.now().isoformat(),
            "mindmap": {
                # 空主题时中心节点应为空，不被 LLM 返回的兜底内容覆盖
                "center": mindmap.get("center", topic) if topic and topic.strip() else topic,
                "branches": mindmap.get("branches", []),
                "total_branches": len(mindmap.get("branches", [])),
            },
        }

    def analyze_problem(self, problem: str, business_domain: str = "") -> Dict[str, Any]:
        """
        问题分析 - 使用多种分析方法剖析问题
        
        Args:
            problem: 问题描述
            business_domain: 业务领域
        
        Returns:
            问题分析结果
        """
        llm = self._get_llm_service()
        prompt_config = self.BRAINSTORM_PROMPTS["problem_analysis"]
        
        user_prompt = prompt_config["user"].format(
            problem=problem,
            business_domain=business_domain,
        )
        
        response = llm.chat(
            system_prompt=prompt_config["system"],
            user_prompt=user_prompt,
            temperature=0.5,
            max_tokens=3000,
        )
        
        analysis = self._parse_response(response)
        
        if isinstance(analysis, list):
            analysis = analysis[0] if analysis else {}
        
        if not isinstance(analysis, dict):
            analysis = {}
        
        return {
            "problem": problem,
            "business_domain": business_domain,
            "generated_at": datetime.now().isoformat(),
            "analysis": analysis,
            "root_causes": analysis.get("root_causes", []),
            "solution_directions": analysis.get("solution_directions", []),
        }

    def evaluate_ideas(self, ideas: List[Dict[str, Any]], 
                      criteria: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        评估创意 - 根据指定标准对创意进行评分
        
        Args:
            ideas: 创意列表
            criteria: 评估标准列表
        
        Returns:
            带有评分的创意列表
        """
        if not criteria:
            criteria = ["创新性", "可行性", "影响力", "商业价值", "实施难度"]
        
        for idea in ideas:
            scores = {}
            total_score = 0
            
            for criterion in criteria:
                score = self._calculate_score(idea, criterion)
                scores[criterion] = score
                total_score += score
            
            idea["scores"] = scores
            idea["total_score"] = round(total_score / len(criteria), 2)
            idea["rank"] = 0
        
        sorted_ideas = sorted(ideas, key=lambda x: x.get("total_score", 0), reverse=True)
        
        for i, idea in enumerate(sorted_ideas):
            idea["rank"] = i + 1
        
        return sorted_ideas

    def export_to_markdown(self, brainstorm_result: Dict[str, Any]) -> str:
        """
        将头脑风暴结果导出为Markdown格式
        
        Args:
            brainstorm_result: 头脑风暴结果
        
        Returns:
            Markdown格式内容
        """
        lines = []
        
        if "round_results" in brainstorm_result:
            lines.append(f"# {brainstorm_result.get('problem', '头脑风暴结果')}")
            lines.append(f"\n**业务领域**: {brainstorm_result.get('business_domain', '')}")
            lines.append(f"**生成时间**: {brainstorm_result.get('generated_at', '')}")
            lines.append(f"**迭代轮数**: {brainstorm_result.get('rounds', 0)}")
            lines.append(f"**总创意数**: {brainstorm_result.get('total_ideas', 0)}")
            
            for round_result in brainstorm_result.get("round_results", []):
                round_num = round_result.get("round", 0)
                lines.append(f"\n## 第{round_num}轮创意")
                
                for idea in round_result.get("ideas", []):
                    lines.append(f"\n### {idea.get('idea', '')}")
                    lines.append(f"- **分类**: {idea.get('category', '')}")
                    lines.append(f"- **影响力**: {idea.get('impact', '')}")
                    lines.append(f"- **可行性**: {idea.get('feasibility', '')}")
                    lines.append(f"- **关键词**: {', '.join(idea.get('keywords', []))}")
                    lines.append(f"- **描述**: {idea.get('description', '')}")
            
            if brainstorm_result.get("final_summary"):
                lines.append("\n## 最终筛选结果")
                for idea in brainstorm_result["final_summary"].get("top_ideas", []):
                    lines.append(f"\n### {idea.get('idea', '')}")
                    lines.append(f"- **评分**: {idea.get('total_score', '')}")
        
        else:
            lines.append(f"# {brainstorm_result.get('problem', '头脑风暴结果')}")
            lines.append(f"\n**业务领域**: {brainstorm_result.get('business_domain', '')}")
            lines.append(f"**生成时间**: {brainstorm_result.get('generated_at', '')}")
            lines.append(f"**总创意数**: {brainstorm_result.get('total_ideas', 0)}")
            
            for idea in brainstorm_result.get("ideas", []):
                lines.append(f"\n## {idea.get('idea', '')}")
                lines.append(f"**分类**: {idea.get('category', '')}")
                lines.append(f"**影响力**: {idea.get('impact', '')}")
                lines.append(f"**可行性**: {idea.get('feasibility', '')}")
                lines.append(f"**关键词**: {', '.join(idea.get('keywords', []))}")
                lines.append(f"\n### 详细描述")
                lines.append(idea.get('description', ''))
                if idea.get('implementation_steps'):
                    lines.append("\n### 实施步骤")
                    for i, step in enumerate(idea['implementation_steps'], 1):
                        lines.append(f"{i}. {step}")
        
        return "\n".join(lines)

    def export_to_json(self, brainstorm_result: Dict[str, Any]) -> str:
        """
        将头脑风暴结果导出为JSON格式
        
        Args:
            brainstorm_result: 头脑风暴结果
        
        Returns:
            JSON格式内容
        """
        return json.dumps(brainstorm_result, ensure_ascii=False, indent=2)

    def _parse_response(self, response: Any) -> Any:
        """解析LLM响应"""
        try:
            if isinstance(response, dict):
                response = response.get("content", str(response))
            
            response_str = str(response).strip()
            
            if response_str.startswith("```json"):
                response_str = response_str[7:]
            if response_str.endswith("```"):
                response_str = response_str[:-3]
            
            return json.loads(response_str.strip())
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse JSON response: {str(response)[:200]}")
            return self._fallback_parse(str(response))

    def _fallback_parse(self, response: str) -> List[Dict[str, Any]]:
        """备用解析方法"""
        ideas = []
        lines = response.split("\n")
        current_idea = {}
        
        for line in lines:
            if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.")):
                if current_idea:
                    ideas.append(current_idea)
                current_idea = {"idea": line[3:].strip()}
            elif line.startswith("- "):
                parts = line[2:].split(":")
                if len(parts) >= 2:
                    key = parts[0].strip()
                    value = ":".join(parts[1:]).strip()
                    if key in ["分类", "category"]:
                        current_idea["category"] = value
                    elif key in ["影响力", "impact"]:
                        current_idea["impact"] = value
                    elif key in ["可行性", "feasibility"]:
                        current_idea["feasibility"] = value
                    elif key in ["关键词", "keywords"]:
                        current_idea["keywords"] = value.split("、")
        
        if current_idea:
            ideas.append(current_idea)
        
        return ideas

    def _extract_categories(self, ideas: List[Dict[str, Any]]) -> List[str]:
        """提取所有分类"""
        categories = set()
        for idea in ideas:
            category = idea.get("category", "")
            if category:
                categories.add(category)
        return sorted(list(categories))

    def _calculate_distribution(self, ideas: List[Dict[str, Any]], field: str) -> Dict[str, int]:
        """计算分布统计"""
        distribution = {}
        for idea in ideas:
            value = idea.get(field, "")
            distribution[value] = distribution.get(value, 0) + 1
        return distribution

    def _extract_suggestions(self, result: Any) -> List[str]:
        """提取优化建议"""
        if isinstance(result, list):
            suggestions = []
            for item in result:
                if isinstance(item, dict):
                    suggestion = item.get("suggestion", item.get("optimization", ""))
                    if suggestion:
                        suggestions.append(suggestion)
            return suggestions
        return []

    def _calculate_score(self, idea: Dict[str, Any], criterion: str) -> int:
        """计算创意评分"""
        impact_map = {"高": 10, "中": 7, "低": 4}
        feasibility_map = {"高": 10, "中": 7, "低": 4}
        
        if criterion == "创新性":
            keywords = idea.get("keywords", [])
            return min(10, len(keywords) * 2 + 2)
        elif criterion == "可行性":
            return feasibility_map.get(idea.get("feasibility", "中"), 7)
        elif criterion == "影响力":
            return impact_map.get(idea.get("impact", "中"), 7)
        elif criterion == "商业价值":
            return 8 if idea.get("impact") == "高" else 6
        elif criterion == "实施难度":
            feasibility = idea.get("feasibility", "中")
            return 10 if feasibility == "高" else 6 if feasibility == "中" else 3
        
        return 7