"""
PM Report Engine - 产品经理专业报告引擎

为产品经理设计的专业报告输出工具：
1. 需求追踪矩阵 (RTM) - 需求与功能的映射关系
2. 功能优先级矩阵 - 基于价值和复杂度的优先级排序
3. 干系人地图 - 识别关键干系人和影响力
4. 项目时间线 - 里程碑和交付计划
5. 风险登记册 - 风险识别和应对措施

输出格式：
- Word文档（专业排版）
- PDF文档（可打印）
- Markdown（版本控制友好）
"""
from __future__ import annotations
import logging
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PMReportEngine:
    """产品经理专业报告引擎"""
    
    def __init__(self):
        pass
    
    def generate_requirement_traceability_matrix(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成需求追踪矩阵 (RTM)
        
        RTM结构：
        - 需求ID、需求描述、功能模块、关联SOP步骤、状态、优先级、验收标准
        """
        objectives = business_system.get("business_understanding", {}).get("core_objectives", [])
        workflow = business_system.get("sop", {}).get("workflow", [])
        features = self._extract_features(business_system)
        
        rows = []
        row_id = 1
        
        for obj in objectives:
            obj_name = obj.get("objective", "")
            obj_target = obj.get("target", "")
            obj_priority = obj.get("priority", "medium")
            
            rows.append({
                "id": f"REQ-{row_id:03d}",
                "requirement": obj_name,
                "description": obj_target,
                "feature_module": "业务目标",
                "sop_step": "",
                "status": "pending",
                "priority": obj_priority,
                "acceptance_criteria": f"达成目标: {obj_target}",
            })
            row_id += 1
        
        for step in workflow:
            step_name = step.get("name", "")
            step_action = step.get("action", "")
            step_role = step.get("role", "")
            
            rows.append({
                "id": f"REQ-{row_id:03d}",
                "requirement": step_name,
                "description": step_action,
                "feature_module": "流程步骤",
                "sop_step": step.get("step", ""),
                "status": "pending",
                "priority": "high",
                "acceptance_criteria": f"{step_role}完成{step_name}",
            })
            row_id += 1
        
        for feature in features:
            rows.append({
                "id": f"REQ-{row_id:03d}",
                "requirement": feature.get("name", ""),
                "description": feature.get("description", ""),
                "feature_module": feature.get("module", ""),
                "sop_step": "",
                "status": "pending",
                "priority": feature.get("priority", "medium"),
                "acceptance_criteria": feature.get("acceptance", ""),
            })
            row_id += 1
        
        return {
            "title": "需求追踪矩阵 (RTM)",
            "description": "需求与功能、流程的映射关系表",
            "columns": ["ID", "需求描述", "详细说明", "功能模块", "关联SOP", "状态", "优先级", "验收标准"],
            "data": rows,
            "total_requirements": len(rows),
        }
    
    def generate_feature_priority_matrix(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成功能优先级矩阵
        
        基于RICE模型或价值/复杂度矩阵进行优先级排序：
        - 影响范围 (Reach)
        - 影响力 (Impact)
        - 信心指数 (Confidence)
        - 投入成本 (Effort)
        """
        features = self._extract_features(business_system)
        objectives = business_system.get("business_understanding", {}).get("core_objectives", [])
        
        priority_rows = []
        
        for feature in features:
            value = feature.get("value", 5)
            complexity = feature.get("complexity", 5)
            
            priority_score = (value * 2) - complexity
            
            if priority_score >= 8:
                priority = "P0 - 紧急"
                quadrant = "高价值/低复杂度"
            elif priority_score >= 5:
                priority = "P1 - 重要"
                quadrant = "高价值/中复杂度"
            elif priority_score >= 3:
                priority = "P2 - 一般"
                quadrant = "中价值/中复杂度"
            else:
                priority = "P3 - 低优先级"
                quadrant = "低价值/高复杂度"
            
            priority_rows.append({
                "feature": feature.get("name", ""),
                "module": feature.get("module", ""),
                "value": value,
                "complexity": complexity,
                "priority_score": priority_score,
                "priority": priority,
                "quadrant": quadrant,
                "description": feature.get("description", ""),
                "estimated_effort": feature.get("effort", "TBD"),
            })
        
        priority_rows.sort(key=lambda x: x["priority_score"], reverse=True)
        
        return {
            "title": "功能优先级矩阵",
            "description": "基于价值/复杂度的功能优先级排序",
            "methodology": "价值/复杂度矩阵",
            "data": priority_rows,
            "priority_distribution": {
                "P0": len([r for r in priority_rows if r["priority"].startswith("P0")]),
                "P1": len([r for r in priority_rows if r["priority"].startswith("P1")]),
                "P2": len([r for r in priority_rows if r["priority"].startswith("P2")]),
                "P3": len([r for r in priority_rows if r["priority"].startswith("P3")]),
            },
        }
    
    def generate_stakeholder_map(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成干系人地图
        
        基于权力/利益矩阵识别关键干系人：
        - 高权力/高利益：重点管理
        - 高权力/低利益：保持满意
        - 低权力/高利益：保持告知
        - 低权力/低利益：最小关注
        """
        roles = business_system.get("sop", {}).get("roles", [])
        responsibilities = business_system.get("sop", {}).get("responsibilities", [])
        
        stakeholders = []
        
        for role in roles:
            role_name = role.get("role", "")
            department = role.get("department", "")
            level = role.get("level", "L3")
            headcount = role.get("headcount", 1)
            
            level_power_map = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5, "L6": 6}
            power = level_power_map.get(level, 3)
            interest = 4 if "经理" in role_name or "总监" in role_name else 3
            
            if power >= 5 and interest >= 4:
                strategy = "重点管理"
                quadrant = "高权力/高利益"
            elif power >= 5 and interest < 4:
                strategy = "保持满意"
                quadrant = "高权力/低利益"
            elif power < 5 and interest >= 4:
                strategy = "保持告知"
                quadrant = "低权力/高利益"
            else:
                strategy = "最小关注"
                quadrant = "低权力/低利益"
            
            stakeholders.append({
                "name": role_name,
                "department": department,
                "level": level,
                "headcount": headcount,
                "power": power,
                "interest": interest,
                "strategy": strategy,
                "quadrant": quadrant,
                "responsibilities": [],
            })
        
        for resp in responsibilities:
            role_name = resp.get("role", "")
            duties = resp.get("duties", [])
            
            for s in stakeholders:
                if s["name"] == role_name:
                    s["responsibilities"] = duties
                    break
        
        return {
            "title": "干系人地图",
            "description": "基于权力/利益矩阵的干系人分析",
            "methodology": "权力/利益矩阵",
            "data": stakeholders,
            "strategy_distribution": {
                "重点管理": len([s for s in stakeholders if s["strategy"] == "重点管理"]),
                "保持满意": len([s for s in stakeholders if s["strategy"] == "保持满意"]),
                "保持告知": len([s for s in stakeholders if s["strategy"] == "保持告知"]),
                "最小关注": len([s for s in stakeholders if s["strategy"] == "最小关注"]),
            },
        }
    
    def generate_project_timeline(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成项目时间线
        
        基于战略分析中的阶段规划生成时间线：
        - 里程碑
        - 交付物
        - 时间节点
        """
        strategic_path = business_system.get("strategy", {}).get("strategic_path", [])
        recommendations = business_system.get("optimization", {}).get("recommendations", [])
        
        phases = []
        
        for i, phase in enumerate(strategic_path):
            phases.append({
                "phase": phase.get("phase", f"第{i+1}阶段"),
                "theme": phase.get("theme", ""),
                "timeline": phase.get("timeline", ""),
                "goal": phase.get("goal", ""),
                "deliverables": [],
                "status": "pending",
            })
        
        for rec in recommendations:
            timeline = rec.get("timeline", "TBD")
            for phase in phases:
                if timeline in phase["timeline"] or "周" in timeline:
                    phase["deliverables"].append(rec.get("title", ""))
                    break
        
        return {
            "title": "项目时间线",
            "description": "项目阶段规划和里程碑",
            "phases": phases,
            "total_phases": len(phases),
        }
    
    def generate_risk_register(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成风险登记册
        
        整合所有风险分析结果：
        - 风险描述
        - 严重程度
        - 概率
        - 影响
        - 应对措施
        """
        risks = []
        
        process_risks = business_system.get("risk", {}).get("process_risks", [])
        org_risks = business_system.get("risk", {}).get("organization_risks", [])
        system_risks = business_system.get("risk", {}).get("system_risks", [])
        compliance_risks = business_system.get("risk", {}).get("compliance_risks", [])
        
        risk_types = {
            "流程风险": process_risks,
            "组织风险": org_risks,
            "系统风险": system_risks,
            "合规风险": compliance_risks,
        }
        
        for risk_type, items in risk_types.items():
            for risk in items:
                severity_map = {
                    "critical": {"score": 5, "label": "严重"},
                    "high": {"score": 4, "label": "高"},
                    "medium": {"score": 3, "label": "中"},
                    "low": {"score": 2, "label": "低"},
                }
                
                severity = severity_map.get(risk.get("severity", "medium"), severity_map["medium"])
                probability = risk.get("probability", "medium")
                
                if probability == "high":
                    prob_score = 4
                elif probability == "medium":
                    prob_score = 3
                else:
                    prob_score = 2
                
                risk_score = severity["score"] * prob_score
                
                if risk_score >= 16:
                    priority = "P0 - 紧急"
                elif risk_score >= 10:
                    priority = "P1 - 高"
                elif risk_score >= 6:
                    priority = "P2 - 中"
                else:
                    priority = "P3 - 低"
                
                risks.append({
                    "risk_id": f"RISK-{len(risks)+1:03d}",
                    "category": risk_type,
                    "description": risk.get("risk", ""),
                    "severity": severity["label"],
                    "severity_score": severity["score"],
                    "probability": probability,
                    "probability_score": prob_score,
                    "risk_score": risk_score,
                    "priority": priority,
                    "mitigation": risk.get("mitigation", ""),
                    "status": "open",
                })
        
        risks.sort(key=lambda x: x["risk_score"], reverse=True)
        
        return {
            "title": "风险登记册",
            "description": "项目风险识别和应对措施",
            "data": risks,
            "total_risks": len(risks),
            "critical_count": len([r for r in risks if r["priority"] == "P0 - 紧急"]),
            "high_count": len([r for r in risks if r["priority"] == "P1 - 高"]),
        }
    
    def generate_kpi_dashboard(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成KPI仪表盘数据
        
        整合所有关键指标：
        - SLA指标
        - KPI指标
        - 自动化指标
        """
        sla = business_system.get("sop", {}).get("sla", [])
        kpi = business_system.get("sop", {}).get("kpi", [])
        automation = business_system.get("strategy", {}).get("automation_opportunities", [])
        
        kpi_items = []
        
        for item in sla:
            kpi_items.append({
                "name": item.get("metric", ""),
                "type": "SLA",
                "target": item.get("target", ""),
                "owner": item.get("owner", ""),
                "current": "TBD",
                "status": "pending",
            })
        
        for item in kpi:
            kpi_items.append({
                "name": item.get("name", ""),
                "type": "KPI",
                "target": item.get("target", ""),
                "owner": item.get("owner", ""),
                "formula": item.get("formula", ""),
                "current": "TBD",
                "status": "pending",
            })
        
        for item in automation:
            kpi_items.append({
                "name": f"{item.get('process', '')}自动化率",
                "type": "自动化",
                "target": item.get("target", ""),
                "current": item.get("current", ""),
                "impact": item.get("impact", ""),
                "status": "pending",
            })
        
        return {
            "title": "KPI仪表盘",
            "description": "关键业务指标和目标",
            "data": kpi_items,
            "total_kpis": len(kpi_items),
        }
    
    def generate_full_pm_report(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成完整的产品经理专业报告
        
        包含：
        1. 需求追踪矩阵
        2. 功能优先级矩阵
        3. 干系人地图
        4. 项目时间线
        5. 风险登记册
        6. KPI仪表盘
        """
        report = {
            "title": f"{business_system.get('business_understanding', {}).get('business_domain', '业务系统')}产品分析报告",
            "generated_at": datetime.now().isoformat(),
            "sections": [
                self.generate_requirement_traceability_matrix(business_system),
                self.generate_feature_priority_matrix(business_system),
                self.generate_stakeholder_map(business_system),
                self.generate_project_timeline(business_system),
                self.generate_risk_register(business_system),
                self.generate_kpi_dashboard(business_system),
            ],
        }
        
        return report
    
    def export_to_markdown(self, report: Dict[str, Any]) -> str:
        """将报告导出为Markdown格式"""
        md_lines = []
        md_lines.append(f"# {report['title']}")
        md_lines.append(f"生成时间: {report['generated_at']}")
        md_lines.append("")
        
        for section in report["sections"]:
            md_lines.append(f"## {section['title']}")
            md_lines.append(section.get("description", ""))
            md_lines.append("")
            
            if "columns" in section and "data" in section:
                md_lines.append("| " + " | ".join(section["columns"]) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(section["columns"])) + " |")
                
                for row in section["data"]:
                    if "id" in row:
                        md_lines.append(f"| {row['id']} | {row.get('requirement', '')} | {row.get('description', '')} | {row.get('feature_module', '')} | {row.get('sop_step', '')} | {row.get('status', '')} | {row.get('priority', '')} | {row.get('acceptance_criteria', '')} |")
                    elif "feature" in row:
                        md_lines.append(f"| {row['feature']} | {row.get('module', '')} | {row.get('value', '')} | {row.get('complexity', '')} | {row.get('priority_score', '')} | {row.get('priority', '')} | {row.get('quadrant', '')} |")
                    elif "risk_id" in row:
                        md_lines.append(f"| {row['risk_id']} | {row.get('category', '')} | {row.get('description', '')} | {row.get('severity', '')} | {row.get('probability', '')} | {row.get('risk_score', '')} | {row.get('priority', '')} | {row.get('mitigation', '')} |")
                    elif "name" in row:
                        md_lines.append(f"| {row['name']} | {row.get('type', '')} | {row.get('target', '')} | {row.get('current', '')} | {row.get('owner', '')} | {row.get('status', '')} |")
            
            elif "phases" in section:
                for phase in section["phases"]:
                    md_lines.append(f"### {phase['phase']}: {phase['theme']}")
                    md_lines.append(f"- 时间线: {phase['timeline']}")
                    md_lines.append(f"- 目标: {phase['goal']}")
                    if phase["deliverables"]:
                        md_lines.append("- 交付物:")
                        for deliverable in phase["deliverables"]:
                            md_lines.append(f"  - {deliverable}")
                    md_lines.append("")
            
            elif "data" in section and "quadrant" in section.get("data", {}):
                for stakeholder in section["data"]:
                    md_lines.append(f"### {stakeholder['name']}")
                    md_lines.append(f"- 部门: {stakeholder['department']}")
                    md_lines.append(f"- 级别: {stakeholder['level']}")
                    md_lines.append(f"- 权力: {stakeholder['power']} | 利益: {stakeholder['interest']}")
                    md_lines.append(f"- 策略: {stakeholder['strategy']}")
                    if stakeholder["responsibilities"]:
                        md_lines.append("- 职责:")
                        for duty in stakeholder["responsibilities"]:
                            md_lines.append(f"  - {duty}")
                    md_lines.append("")
            
            md_lines.append("")
        
        return "\n".join(md_lines)
    
    def export_to_html(self, report: Dict[str, Any]) -> str:
        """将报告导出为HTML格式"""
        html_lines = []
        html_lines.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        h3 {{ color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #3498db; color: white; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .priority-P0 {{ background: #e74c3c; color: white; padding: 2px 8px; border-radius: 4px; }}
        .priority-P1 {{ background: #e67e22; color: white; padding: 2px 8px; border-radius: 4px; }}
        .priority-P2 {{ background: #f39c12; color: white; padding: 2px 8px; border-radius: 4px; }}
        .priority-P3 {{ background: #95a5a6; color: white; padding: 2px 8px; border-radius: 4px; }}
        .severity-critical {{ color: #e74c3c; font-weight: bold; }}
        .severity-high {{ color: #e67e22; font-weight: bold; }}
        .severity-medium {{ color: #f39c12; }}
        .severity-low {{ color: #95a5a6; }}
        .phase-box {{ background: #ecf0f1; padding: 20px; border-radius: 8px; margin: 10px 0; }}
        .stakeholder-box {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #ffc107; }}
        .kpi-card {{ display: inline-block; width: 280px; background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 10px; text-align: center; }}
        .kpi-value {{ font-size: 24px; font-weight: bold; color: #3498db; }}
        .kpi-label {{ color: #7f8c8d; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">""".format(title=report["title"]))
        
        html_lines.append(f"<h1>{report['title']}</h1>")
        html_lines.append(f"<p><strong>生成时间:</strong> {report['generated_at']}</p>")
        
        for section in report["sections"]:
            html_lines.append(f"<h2>{section['title']}</h2>")
            html_lines.append(f"<p>{section.get('description', '')}</p>")
            
            if "columns" in section and "data" in section:
                html_lines.append("<table>")
                html_lines.append("<thead><tr>" + "".join(f"<th>{col}</th>" for col in section["columns"]) + "</tr></thead>")
                html_lines.append("<tbody>")
                
                for row in section["data"]:
                    html_lines.append("<tr>")
                    if "id" in row:
                        html_lines.append(f"<td>{row['id']}</td>")
                        html_lines.append(f"<td>{row.get('requirement', '')}</td>")
                        html_lines.append(f"<td>{row.get('description', '')}</td>")
                        html_lines.append(f"<td>{row.get('feature_module', '')}</td>")
                        html_lines.append(f"<td>{row.get('sop_step', '')}</td>")
                        html_lines.append(f"<td>{row.get('status', '')}</td>")
                        priority_class = f"priority-{row.get('priority', '').split()[0]}" if row.get("priority") else ""
                        html_lines.append(f"<td><span class='{priority_class}'>{row.get('priority', '')}</span></td>")
                        html_lines.append(f"<td>{row.get('acceptance_criteria', '')}</td>")
                    elif "feature" in row:
                        html_lines.append(f"<td>{row['feature']}</td>")
                        html_lines.append(f"<td>{row.get('module', '')}</td>")
                        html_lines.append(f"<td>{row.get('value', '')}</td>")
                        html_lines.append(f"<td>{row.get('complexity', '')}</td>")
                        html_lines.append(f"<td>{row.get('priority_score', '')}</td>")
                        priority_class = f"priority-{row.get('priority', '').split()[0]}" if row.get("priority") else ""
                        html_lines.append(f"<td><span class='{priority_class}'>{row.get('priority', '')}</span></td>")
                        html_lines.append(f"<td>{row.get('quadrant', '')}</td>")
                    elif "risk_id" in row:
                        html_lines.append(f"<td>{row['risk_id']}</td>")
                        html_lines.append(f"<td>{row.get('category', '')}</td>")
                        html_lines.append(f"<td>{row.get('description', '')}</td>")
                        severity_class = f"severity-{row.get('severity', '').lower()}"
                        html_lines.append(f"<td><span class='{severity_class}'>{row.get('severity', '')}</span></td>")
                        html_lines.append(f"<td>{row.get('probability', '')}</td>")
                        html_lines.append(f"<td>{row.get('risk_score', '')}</td>")
                        priority_class = f"priority-{row.get('priority', '').split()[0]}" if row.get("priority") else ""
                        html_lines.append(f"<td><span class='{priority_class}'>{row.get('priority', '')}</span></td>")
                        html_lines.append(f"<td>{row.get('mitigation', '')}</td>")
                    elif "name" in row:
                        html_lines.append(f"<td>{row['name']}</td>")
                        html_lines.append(f"<td>{row.get('type', '')}</td>")
                        html_lines.append(f"<td>{row.get('target', '')}</td>")
                        html_lines.append(f"<td>{row.get('current', '')}</td>")
                        html_lines.append(f"<td>{row.get('owner', '')}</td>")
                        html_lines.append(f"<td>{row.get('status', '')}</td>")
                    html_lines.append("</tr>")
                
                html_lines.append("</tbody></table>")
            
            elif "phases" in section:
                for phase in section["phases"]:
                    html_lines.append("<div class='phase-box'>")
                    html_lines.append(f"<h3>{phase['phase']}: {phase['theme']}</h3>")
                    html_lines.append(f"<p><strong>时间线:</strong> {phase['timeline']}</p>")
                    html_lines.append(f"<p><strong>目标:</strong> {phase['goal']}</p>")
                    if phase["deliverables"]:
                        html_lines.append("<p><strong>交付物:</strong></p>")
                        html_lines.append("<ul>" + "".join(f"<li>{d}</li>" for d in phase["deliverables"]) + "</ul>")
                    html_lines.append("</div>")
            
            elif "data" in section and "quadrant" in section.get("data", {}):
                for stakeholder in section["data"]:
                    html_lines.append("<div class='stakeholder-box'>")
                    html_lines.append(f"<h3>{stakeholder['name']}</h3>")
                    html_lines.append(f"<p><strong>部门:</strong> {stakeholder['department']}</p>")
                    html_lines.append(f"<p><strong>级别:</strong> {stakeholder['level']}</p>")
                    html_lines.append(f"<p><strong>权力:</strong> {stakeholder['power']} | <strong>利益:</strong> {stakeholder['interest']}</p>")
                    html_lines.append(f"<p><strong>策略:</strong> {stakeholder['strategy']}</p>")
                    if stakeholder["responsibilities"]:
                        html_lines.append("<p><strong>职责:</strong></p>")
                        html_lines.append("<ul>" + "".join(f"<li>{d}</li>" for d in stakeholder["responsibilities"]) + "</ul>")
                    html_lines.append("</div>")
            
            elif "data" in section and "type" in section.get("data", {}):
                html_lines.append("<div>")
                for kpi in section["data"]:
                    html_lines.append("<div class='kpi-card'>")
                    html_lines.append(f"<div class='kpi-value'>{kpi.get('current', 'TBD')}</div>")
                    html_lines.append(f"<div class='kpi-label'>{kpi.get('name', '')}</div>")
                    html_lines.append(f"<div style='font-size:12px;color:#7f8c8d'>目标: {kpi.get('target', '')}</div>")
                    html_lines.append("</div>")
                html_lines.append("</div>")
        
        html_lines.append("</div></body></html>")
        
        return "\n".join(html_lines)
    
    def _extract_features(self, business_system: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从业务系统中提取功能列表"""
        features = []
        
        objectives = business_system.get("business_understanding", {}).get("core_objectives", [])
        for i, obj in enumerate(objectives):
            features.append({
                "name": obj.get("objective", f"功能{i+1}"),
                "description": obj.get("target", ""),
                "module": "业务目标",
                "priority": obj.get("priority", "medium"),
                "value": 8 if obj.get("priority") == "high" else 5,
                "complexity": 5,
                "effort": "TBD",
                "acceptance": obj.get("target", ""),
            })
        
        workflow = business_system.get("sop", {}).get("workflow", [])
        for i, step in enumerate(workflow):
            features.append({
                "name": step.get("name", f"流程步骤{i+1}"),
                "description": step.get("action", ""),
                "module": "流程功能",
                "priority": "high",
                "value": 7,
                "complexity": 4,
                "effort": "TBD",
                "acceptance": f"{step.get('role', '')}完成{step.get('name', '')}",
            })
        
        return features


__all__ = ["PMReportEngine"]
