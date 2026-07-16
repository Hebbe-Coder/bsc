# app/orchestrator/agents/reviewer.py
from __future__ import annotations
import json
from app.agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Reviewer Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Reviewer Agent。职责：审查业务模型与 SOP，执行两项核心检查：\n"
            "A. 约束覆盖率检查：逐条核对 requirements 中的每个约束，判断是否被 SOP 或 business_model 覆盖。\n"
            "   - 覆盖判定标准：SOP 中存在对应的流程步骤/闭环管控/复盘机制，或 business_model 中存在对应规则。\n"
            "   - 对于每个未覆盖的约束，生成一条 high 级 gap，type 为 'constraint_uncovered'，target 为 'sop'。\n"
            "B. 通用漏洞检查：找漏洞（尤其缺复审/升级机制/SLA）。\n"
            "\n必须输出 JSON：\n"
            '{"review":{"approved":bool,'
            ' "constraint_coverage": {"total":int,"covered":int,"uncovered_ids":[str],"coverage_pct":int},'
            ' "gaps":[{"id":str,"severity":"high|medium|low","type":str,"desc":str,'
            '          "suggested_fix":str,"target":"ba|sop","constraint_id":str}],'
            ' "loopback_target":"ba|sop|null",'
            ' "loopback_fixes":[str],'
            ' "summary":str}}'
            "\n约束：\n"
            "1. 若存在 high 级漏洞，loopback_target 必须等于某个 high 级 gap 的 target；"
            "若存在多个 high gap 指向不同段，取影响最大者，且 gaps 中须至少有一条 high gap 的 target 与之相同。\n"
            "2. approved 为 true 当且仅当无 high 级漏洞（此时 loopback_target 必为 null）；否则 approved 为 false。\n"
            "3. loopback_fixes 是要传递给回环目标的具体修复指令列表（基于 high 级 gap 的 suggested_fix）。\n"
            "4. constraint_coverage 必须准确反映 requirements 的覆盖情况。"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["review"]}

    def run(self, project: dict, business_model: dict, sop: dict,
            requirements: list = None, risk: dict = None, context: dict = None) -> dict:
        req_str = json.dumps(requirements or [], ensure_ascii=False)
        user_prompt = (
            f"项目：{json.dumps(project, ensure_ascii=False)}\n"
            f"需求/约束列表：{req_str}\n"
            f"业务模型：{json.dumps(business_model, ensure_ascii=False)}\n"
            f"SOP：{json.dumps(sop, ensure_ascii=False)}\n"
            f"风险/约束系统：{json.dumps(risk or {}, ensure_ascii=False)}\n"
            f"请逐条核对约束覆盖情况，并审查通用漏洞，产出 review。"
        )
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
