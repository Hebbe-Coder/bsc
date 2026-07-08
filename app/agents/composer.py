"""
Business Composer - 统一组装所有Agent结果

职责：
    1. 合并所有并行Agent的结果（SOP/Risk/Strategy/Optimization）
    2. 整合业务理解结果
    3. 生成综合业务报告
    4. 构建统计摘要

输入：各Agent的结构化JSON
输出：统一最终结果（包含报告）

使用豆包模型（生成类Agent），适合创意写作和报告生成。
"""
from __future__ import annotations
import json, time


class Composer:
    """Business Composer - 结果组装器"""

    def compose(self, results: dict) -> dict:
        """
        统一合并所有Agent结果
        
        Args:
            results: {"business_understanding": {...}, "sop": {...}, "risk": {...}, "strategy": {...}, "optimization": {...}}
        
        Returns:
            统一最终结果（包含报告）
        """
        composed = {
            "composed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agents_executed": list(results.keys()),
        }

        # Business Understanding
        if "business_understanding" in results:
            bu = results["business_understanding"]
            composed["business_understanding"] = {
                "business_domain": bu.get("business_domain", ""),
                "core_objectives": bu.get("core_objectives", []),
                "key_entities": bu.get("key_entities", []),
                "process_flow": bu.get("process_flow", []),
                "success_metrics": bu.get("success_metrics", []),
                "constraints": bu.get("constraints", []),
                "industry_context": bu.get("industry_context", ""),
            }

        # SOP
        if "sop" in results:
            sop = results["sop"]
            composed["sop"] = {
                "workflow": sop.get("workflow", []),
                "roles": sop.get("roles", []),
                "responsibilities": sop.get("responsibilities", []),
                "sla": sop.get("sla", []),
                "kpi": sop.get("kpi", []),
            }

        # Risk
        if "risk" in results:
            risk = results["risk"]
            composed["risk"] = {
                "process_risks": risk.get("process_risks", []),
                "organization_risks": risk.get("organization_risks", []),
                "system_risks": risk.get("system_risks", []),
                "compliance_risks": risk.get("compliance_risks", []),
            }

        # Strategy
        if "strategy" in results:
            strategy = results["strategy"]
            composed["strategy"] = {
                "growth_opportunities": strategy.get("growth_opportunities", []),
                "efficiency_opportunities": strategy.get("efficiency_opportunities", []),
                "automation_opportunities": strategy.get("automation_opportunities", []),
                "strategic_path": strategy.get("strategic_path", []),
            }

        # Optimization
        if "optimization" in results:
            opt = results["optimization"]
            composed["optimization"] = {
                "recommendations": opt.get("recommendations", []),
                "roi_estimation": opt.get("roi_estimation", []),
            }

        # 生成综合业务报告
        composed["report"] = self._generate_report(composed)

        # 统计摘要
        composed["summary"] = self._build_summary(composed)

        return composed

    def _generate_report(self, composed: dict) -> dict:
        """生成综合业务报告"""
        bu = composed.get("business_understanding", {})
        sop = composed.get("sop", {})
        risk = composed.get("risk", {})
        strategy = composed.get("strategy", {})
        optimization = composed.get("optimization", {})

        domain = bu.get("business_domain", "业务")
        objectives = [o.get("objective", "") for o in bu.get("core_objectives", [])]
        workflow_steps = len(sop.get("workflow", []))
        total_risks = sum(len(risk.get(k, [])) for k in ["process_risks", "organization_risks", "system_risks", "compliance_risks"])
        growth_opportunities = len(strategy.get("growth_opportunities", []))
        recommendations = len(optimization.get("recommendations", []))

        return {
            "title": f"{domain}业务分析报告",
            "executive_summary": f"本报告基于PRD分析，针对{domain}领域提出完整的业务系统方案。"
                               f"共识别{len(objectives)}个核心目标，设计{workflow_steps}步流程，"
                               f"识别{total_risks}项风险，发现{growth_opportunities}个增长机会，"
                               f"提出{recommendations}项优化建议。",
            "sections": [
                {
                    "section": "1. 业务目标",
                    "content": f"核心目标：{', '.join(objectives) if objectives else '暂无'}。"
                              f"行业背景：{bu.get('industry_context', '')}。"
                              f"约束条件：{', '.join(bu.get('constraints', []))}。"
                },
                {
                    "section": "2. 流程设计",
                    "content": f"共{workflow_steps}个步骤，涉及{len(sop.get('roles', []))}个角色。"
                              f"SLA指标：{len(sop.get('sla', []))}项，KPI指标：{len(sop.get('kpi', []))}项。"
                },
                {
                    "section": "3. 风险分析",
                    "content": f"共识别{total_risks}项风险，涵盖流程、组织、系统、合规四大维度。"
                              f"其中流程风险{len(risk.get('process_risks', []))}项，组织风险{len(risk.get('organization_risks', []))}项，"
                              f"系统风险{len(risk.get('system_risks', []))}项，合规风险{len(risk.get('compliance_risks', []))}项。"
                },
                {
                    "section": "4. 战略机会",
                    "content": f"发现{growth_opportunities}个增长机会，"
                              f"{len(strategy.get('efficiency_opportunities', []))}个效率机会，"
                              f"{len(strategy.get('automation_opportunities', []))}个自动化机会。"
                },
                {
                    "section": "5. 优化建议",
                    "content": f"提出{recommendations}项优化建议，均附带ROI估算。"
                },
            ],
            "key_findings": [
                {"finding": f"{domain}领域共识别{total_risks}项风险，需优先关注", "impact": "高", "category": "风险"},
                {"finding": f"流程设计包含{workflow_steps}个步骤，涉及{len(sop.get('roles', []))}个角色", "impact": "中", "category": "流程"},
                {"finding": f"发现{growth_opportunities}个增长机会，具有较高商业价值", "impact": "高", "category": "战略"},
                {"finding": f"{recommendations}项优化建议可带来显著ROI提升", "impact": "高", "category": "优化"},
            ],
        }

    def _build_summary(self, composed: dict) -> dict:
        """构建统计摘要"""
        summary = {}

        if "business_understanding" in composed:
            bu = composed["business_understanding"]
            summary["business_domain"] = bu.get("business_domain", "")
            summary["objectives_count"] = len(bu.get("core_objectives", []))

        if "sop" in composed:
            summary["workflow_steps"] = len(composed["sop"].get("workflow", []))
            summary["roles"] = len(composed["sop"].get("roles", []))
            summary["sla"] = len(composed["sop"].get("sla", []))
            summary["kpi"] = len(composed["sop"].get("kpi", []))

        if "risk" in composed:
            summary["total_risks"] = sum(
                len(composed["risk"].get(k, []))
                for k in ["process_risks", "organization_risks", "system_risks", "compliance_risks"]
            )

        if "strategy" in composed:
            summary["growth_opportunities"] = len(composed["strategy"].get("growth_opportunities", []))
            summary["efficiency_opportunities"] = len(composed["strategy"].get("efficiency_opportunities", []))
            summary["automation_opportunities"] = len(composed["strategy"].get("automation_opportunities", []))

        if "optimization" in composed:
            summary["recommendations"] = len(composed["optimization"].get("recommendations", []))

        return summary


COMPOSER = Composer()
