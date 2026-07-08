"""
BSC Repair Engine v2 — 适配生产模型 ProductionBusinessSystem。

v1: 基于 BusinessSystemSchema（图结构 workflow、KPI树、Mitigation模型）
v2: 基于 ProductionBusinessSystem（线性 workflow、扁平 risks、LLM产出结构）

Phases:
  1. Parse & Unwrap       - 解包 business_system
  2. Fill Top-level        - 填充缺失的顶层字段
  3. Fix Objectives        - 修复目标项（objective/target/priority）
  4. Fix Workflow          - 修复线性流程步骤（step/name/action）
  5. Fix Metrics & KPI     - 修复指标（name/formula/target）
  6. Fix Risks             - 修复扁平风险 + 同步分类风险
  7. Fix Strategy & Opt    - 修复战略和优化建议
  8. Re-validate           - 用 ProductionBusinessSystem 校验
"""

from __future__ import annotations
import json as _json, copy as _copy, uuid as _uuid, re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepairAction:
    phase: str; action: str; path: str; before: str; after: str; auto: bool = True


@dataclass
class RepairReport:
    report_id: str; is_valid: bool
    actions: list = field(default_factory=list)
    repaired_json: dict = field(default_factory=dict)
    errors_remaining: list = field(default_factory=list)

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "is_valid": self.is_valid,
            "actions_applied": len(self.actions),
            "actions": [
                {"phase": a.phase, "action": a.action, "path": a.path,
                 "before": a.before, "after": a.after, "auto": a.auto}
                for a in self.actions
            ],
            "errors_remaining": self.errors_remaining,
            "repaired_json": self.repaired_json,
        }


# ============================================================
# 默认值 — 匹配生产模型字段结构
# ============================================================

DEFAULT_OBJECTIVES = [
    {"objective": "提升业务效率", "target": "效率提升20%", "priority": "high"},
    {"objective": "降低运营风险", "target": "风险事件减少50%", "priority": "high"},
    {"objective": "保障服务质量", "target": "SLA达标率>99%", "priority": "medium"},
]

DEFAULT_WORKFLOW = [
    {"step": 1, "name": "需求接收", "action": "接收并登记业务请求", "owner": "前端", "sla": "1h"},
    {"step": 2, "name": "验证处理", "action": "验证数据完整性和合规性", "owner": "系统", "sla": "2h"},
    {"step": 3, "name": "业务处理", "action": "执行核心业务逻辑", "owner": "后端", "sla": "4h"},
    {"step": 4, "name": "质量审核", "action": "审核处理结果，决定是否通过", "owner": "QA", "sla": "2h"},
    {"step": 5, "name": "完成交付", "action": "输出结果并归档", "owner": "系统", "sla": "1h"},
]

DEFAULT_KPI = [
    {"name": "处理吞吐量", "formula": "处理总数 / 时间", "target": "> 100/小时", "owner": "运营"},
    {"name": "错误率", "formula": "错误数 / 总数 * 100", "target": "< 1%", "owner": "QA"},
    {"name": "平均处理时长", "formula": "sum(处理时间) / count", "target": "< 120分钟", "owner": "运营"},
    {"name": "SLA达标率", "formula": "按时完成数 / 总数 * 100", "target": "> 99%", "owner": "运营"},
]

DEFAULT_RISKS = [
    {"risk": "数据验证缺失", "severity": "high", "mitigation": "增加多级验证规则", "category": "process"},
    {"risk": "处理瓶颈", "severity": "high", "mitigation": "弹性扩容处理资源", "category": "process"},
    {"risk": "审核积压", "severity": "medium", "mitigation": "增加审核人员和自动优先级排序", "category": "organization"},
]

RISK_CATEGORIES = ["process", "organization", "system", "compliance"]
SEVERITY_LEVELS = ["low", "medium", "high", "critical"]


# ============================================================
# REPAIR ENGINE
# ============================================================

class RepairEngine:

    def __init__(self):
        self.actions: list[RepairAction] = []

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def repair(self, data: dict) -> RepairReport:
        self.actions.clear()
        report_id = str(_uuid.uuid4())[:12]
        repaired = _copy.deepcopy(data) if isinstance(data, dict) else {}

        repaired = self._unwrap(repaired)
        repaired = self._fill_top(repaired)
        repaired = self._fix_objectives(repaired)
        repaired = self._fix_workflow(repaired)
        repaired = self._fix_metrics(repaired)
        repaired = self._fix_risks(repaired)
        repaired = self._fix_strategy_optimization(repaired)
        errors = self._validate(repaired)

        return RepairReport(
            report_id=report_id, is_valid=len(errors) == 0,
            actions=list(self.actions), repaired_json=repaired,
            errors_remaining=errors,
        )

    def repair_string(self, json_str: str) -> RepairReport:
        try:
            data = _json.loads(json_str)
        except _json.JSONDecodeError:
            cleaned = self._extract_json(json_str)
            try:
                data = _json.loads(cleaned)
            except _json.JSONDecodeError:
                data = {}
        return self.repair(data)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> str:
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        start = text.find("{")
        if start == -1:
            return "{}"
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return "{}"

    def _act(self, phase: str, action: str, path: str, before: str, after: str):
        self.actions.append(RepairAction(phase=phase, action=action, path=path, before=before, after=after))

    # ------------------------------------------------------------------
    # PHASE 1: Unwrap
    # ------------------------------------------------------------------

    def _unwrap(self, data: dict) -> dict:
        if "business_system" in data and isinstance(data["business_system"], dict):
            self._act("parse", "unwrapped", "root", "wrapped in business_system", "extracted")
            return data["business_system"]
        return data

    # ------------------------------------------------------------------
    # PHASE 2: Top-level fields
    # ------------------------------------------------------------------

    def _fill_top(self, data: dict) -> dict:
        defaults = {
            "business_domain": "未命名业务系统",
            "objectives": [],
            "roles": [],
            "workflow": [],
            "responsibilities": [],
            "sla": [],
            "metrics": [],
            "kpi": [],
            "risks": [],
            "risk": {},
            "strategy": {},
            "optimization": {},
            "composed": {},
            "report": {},
        }
        for key, default in defaults.items():
            if key not in data or data[key] is None:
                data[key] = _copy.deepcopy(default)
                self._act("schema", "filled", key, "MISSING", f"default {type(default).__name__}")
        return data

    # ------------------------------------------------------------------
    # PHASE 3: Objectives
    # ------------------------------------------------------------------

    def _fix_objectives(self, data: dict) -> dict:
        objectives = data.get("objectives", [])
        if not objectives:
            data["objectives"] = _copy.deepcopy(DEFAULT_OBJECTIVES)
            self._act("objectives", "filled", "objectives", "empty", f"{len(DEFAULT_OBJECTIVES)} default objectives")
            return data

        for i, obj in enumerate(objectives):
            if not isinstance(obj, dict):
                objectives[i] = {"objective": f"目标{i+1}", "target": "待定义", "priority": "medium"}
                self._act("objectives", "filled", f"objectives[{i}]", "non-dict", "default objective")
                obj = objectives[i]
            if not obj.get("objective"):
                obj["objective"] = f"目标{i+1}"
                self._act("objectives", "filled", f"objectives[{i}].objective", "MISSING", obj["objective"])
            if not obj.get("target"):
                obj["target"] = "待定义"
                self._act("objectives", "filled", f"objectives[{i}].target", "MISSING", obj["target"])
            obj.setdefault("priority", "medium")
        return data

    # ------------------------------------------------------------------
    # PHASE 4: Workflow（线性步骤）
    # ------------------------------------------------------------------

    def _fix_workflow(self, data: dict) -> dict:
        workflow = data.get("workflow", [])
        if not workflow:
            data["workflow"] = _copy.deepcopy(DEFAULT_WORKFLOW)
            self._act("workflow", "filled", "workflow", "empty", f"{len(DEFAULT_WORKFLOW)} default steps")
            return data

        for i, step in enumerate(workflow):
            if not isinstance(step, dict):
                workflow[i] = {"step": i + 1, "name": f"步骤{i+1}", "action": "待定义"}
                self._act("workflow", "filled", f"workflow[{i}]", "non-dict", "default step")
                step = workflow[i]
            # step 序号
            if not step.get("step") or not isinstance(step.get("step"), (int, float)):
                step["step"] = i + 1
                self._act("workflow", "filled", f"workflow[{i}].step", "MISSING", str(step["step"]))
            # name
            if not step.get("name"):
                step["name"] = f"步骤{i+1}"
                self._act("workflow", "filled", f"workflow[{i}].name", "MISSING", step["name"])
            # action
            if not step.get("action"):
                step["action"] = f"执行{step['name']}"
                self._act("workflow", "filled", f"workflow[{i}].action", "MISSING", step["action"])
            step.setdefault("owner", "unassigned")
        return data

    # ------------------------------------------------------------------
    # PHASE 5: Metrics & KPI
    # ------------------------------------------------------------------

    def _fix_metrics(self, data: dict) -> dict:
        # 确保 metrics 和 kpi 同步
        metrics = data.get("metrics", [])
        kpi = data.get("kpi", [])

        # 如果 metrics 为空但 kpi 有值，从 kpi 复制
        if not metrics and kpi:
            data["metrics"] = _copy.deepcopy(kpi)
            metrics = data["metrics"]
            self._act("metrics", "copied", "kpi->metrics", f"{len(kpi)} items", "copied to metrics")
        # 如果 kpi 为空但 metrics 有值，从 metrics 复制
        elif not kpi and metrics:
            data["kpi"] = _copy.deepcopy(metrics)
            self._act("metrics", "copied", "metrics->kpi", f"{len(metrics)} items", "copied to kpi")

        if not metrics:
            data["metrics"] = _copy.deepcopy(DEFAULT_KPI)
            data["kpi"] = _copy.deepcopy(DEFAULT_KPI)
            self._act("metrics", "filled", "metrics", "empty", f"{len(DEFAULT_KPI)} default metrics")
            return data

        for i, metric in enumerate(metrics):
            if not isinstance(metric, dict):
                metrics[i] = {"name": f"指标{i+1}", "formula": "TBD", "target": "TBD"}
                self._act("metrics", "filled", f"metrics[{i}]", "non-dict", "default metric")
                metric = metrics[i]
            if not metric.get("name"):
                metric["name"] = f"指标{i+1}"
                self._act("metrics", "filled", f"metrics[{i}].name", "MISSING", metric["name"])
            if not metric.get("formula") or metric["formula"] in ("", "TBD", None):
                metric["formula"] = self._gen_formula(metric.get("name", ""))
                self._act("metrics", "generated", f"metrics[{i}].formula", "MISSING", metric["formula"])
            if not metric.get("target") or metric["target"] in ("", "TBD", None):
                metric["target"] = "> 90%" if "率" in metric.get("name", "") else "TBD"
                self._act("metrics", "generated", f"metrics[{i}].target", "MISSING", metric["target"])
            metric.setdefault("owner", "unassigned")

        # 同步 kpi
        data["kpi"] = _copy.deepcopy(metrics)
        return data

    @staticmethod
    def _gen_formula(name: str) -> str:
        nl = name.lower()
        if "吞吐" in name or "throughput" in nl: return "处理总数 / 时间"
        if "错误" in name or "error" in nl: return "错误数 / 总数 * 100"
        if "时长" in name or "时间" in name or "time" in nl: return "sum(处理时间) / count"
        if "成本" in name or "cost" in nl: return "总成本 / 单位数"
        if "队列" in name or "积压" in name: return "count(待处理)"
        if "率" in name or "rate" in nl: return "(达标数 / 总数) * 100"
        if "sla" in nl or "达标" in name: return "(按时完成数 / 总数) * 100"
        return "metric_value_measured"

    # ------------------------------------------------------------------
    # PHASE 6: Risks（扁平风险 + 分类风险）
    # ------------------------------------------------------------------

    def _fix_risks(self, data: dict) -> dict:
        risks = data.get("risks", [])

        # 如果 risks 为空但 risk（分类）有值，从分类风险提取
        if not risks and data.get("risk"):
            risks = self._flatten_risk_categories(data.get("risk", {}))
            if risks:
                data["risks"] = risks
                self._act("risk", "flattened", "risk->risks", "categorized", f"{len(risks)} flattened risks")

        if not risks:
            data["risks"] = _copy.deepcopy(DEFAULT_RISKS)
            self._act("risk", "filled", "risks", "empty", f"{len(DEFAULT_RISKS)} default risks")
            risks = data["risks"]

        for i, risk in enumerate(risks):
            if not isinstance(risk, dict):
                risks[i] = {"risk": f"风险{i+1}", "severity": "medium", "mitigation": "待定义"}
                self._act("risk", "filled", f"risks[{i}]", "non-dict", "default risk")
                risk = risks[i]
            # risk 描述
            if not risk.get("risk"):
                risk["risk"] = f"风险{i+1}"
                self._act("risk", "filled", f"risks[{i}].risk", "MISSING", risk["risk"])
            # severity 规范化
            sev = str(risk.get("severity", "")).lower()
            if sev not in SEVERITY_LEVELS:
                risk["severity"] = "medium"
                self._act("risk", "normalized", f"risks[{i}].severity", sev or "MISSING", "medium")
            # mitigation
            if not risk.get("mitigation"):
                risk["mitigation"] = "监控并制定缓解措施"
                self._act("risk", "filled", f"risks[{i}].mitigation", "MISSING", risk["mitigation"])
            # category 规范化
            cat = str(risk.get("category", "")).lower()
            if cat not in RISK_CATEGORIES:
                risk["category"] = "process"
                self._act("risk", "normalized", f"risks[{i}].category", cat or "MISSING", "process")
            risk.setdefault("probability", "medium")

        # 同步分类风险结构
        data["risk"] = self._categorize_risks(risks)
        return data

    @staticmethod
    def _flatten_risk_categories(risk_data: dict) -> list[dict]:
        """将分类风险 {process_risks[], ...} 扁平化为列表"""
        all_risks = []
        for cat in RISK_CATEGORIES:
            key = f"{cat}_risks"
            for r in risk_data.get(key, []):
                if isinstance(r, dict):
                    r.setdefault("category", cat)
                    all_risks.append(r)
        return all_risks

    @staticmethod
    def _categorize_risks(risks: list[dict]) -> dict:
        """将扁平风险列表分类到 {process_risks[], organization_risks[], ...}"""
        result = {f"{cat}_risks": [] for cat in RISK_CATEGORIES}
        for r in risks:
            cat = str(r.get("category", "process")).lower()
            if cat not in RISK_CATEGORIES:
                cat = "process"
            result[f"{cat}_risks"].append(r)
        return result

    # ------------------------------------------------------------------
    # PHASE 7: Strategy & Optimization
    # ------------------------------------------------------------------

    def _fix_strategy_optimization(self, data: dict) -> dict:
        # Strategy
        strategy = data.get("strategy", {})
        if not isinstance(strategy, dict):
            strategy = {}
            data["strategy"] = strategy
            self._act("strategy", "filled", "strategy", "non-dict", "empty dict")
        strategy.setdefault("growth_opportunities", [])
        strategy.setdefault("efficiency_opportunities", [])
        strategy.setdefault("automation_opportunities", [])
        strategy.setdefault("strategic_path", [])

        # Optimization
        opt = data.get("optimization", {})
        if not isinstance(opt, dict):
            opt = {}
            data["optimization"] = opt
            self._act("optimization", "filled", "optimization", "non-dict", "empty dict")
        opt.setdefault("recommendations", [])
        opt.setdefault("roi_estimation", [])

        # Composed & Report
        composed = data.get("composed", {})
        if not isinstance(composed, dict):
            composed = {}
            data["composed"] = composed
        composed.setdefault("report", {})

        report = data.get("report", {})
        if not isinstance(report, dict):
            report = {}
            data["report"] = report
        report.setdefault("title", f"{data.get('business_domain', '业务')}分析报告")
        report.setdefault("executive_summary", "")
        report.setdefault("sections", [])

        return data

    # ------------------------------------------------------------------
    # PHASE 8: Validate
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(data: dict) -> list[str]:
        errors = []
        try:
            from app.schemas.production_schema import validate_business_system
            _, warnings = validate_business_system(data)
            errors.extend(warnings)
        except Exception as e:
            errors.append(f"校验异常: {str(e)[:200]}")
        return errors


# ============================================================
# CONVENIENCE
# ============================================================

def repair_json(data: dict) -> RepairReport:
    return RepairEngine().repair(data)

def repair_string(json_str: str) -> RepairReport:
    return RepairEngine().repair_string(json_str)


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":
    broken = {
        "business_system": {
            "business_domain": "内容审核",
            "objectives": [{"target": "99%"}],  # 缺少 objective
            "workflow": [{"name": "提交", "action": "接收"}],  # 缺少 step
            "kpi": [{"name": "审核率"}],  # 缺少 formula
            "risks": [{"risk": "误判", "severity": "非常高"}],  # severity 不规范
        }
    }
    engine = RepairEngine()
    report = engine.repair(broken)
    print(f"Report: {report.report_id}  Valid: {report.is_valid}")
    print(f"Actions: {len(report.actions)}")
    for a in report.actions:
        print(f"  [{a.phase}] {a.action}: {a.path}  ({a.before} -> {a.after})")
    if report.errors_remaining:
        print(f"Warnings: {report.errors_remaining}")
    rj = report.repaired_json
    print(f"\nDomain: {rj.get('business_domain')}")
    print(f"Objectives: {len(rj.get('objectives', []))}")
    print(f"Workflow: {len(rj.get('workflow', []))}")
    print(f"Metrics: {len(rj.get('metrics', []))}")
    print(f"Risks: {len(rj.get('risks', []))}")
    print(f"Risk categories: {sum(len(v) for v in rj.get('risk', {}).values())}")
