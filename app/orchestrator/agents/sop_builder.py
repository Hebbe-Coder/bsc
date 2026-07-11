# app/orchestrator/agents/sop_builder.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class SopBuilderAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "SOP Builder Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 SOP Builder Agent。职责：把 SOP 报告结构化为最终 SOP 集合。\n"
            "输入是 SOPReportEngine 生成的报告（含 workflow/roles/sla）。请产出 JSON：\n"
            '{"sop":{"sops":[{"id":str,"title":str,"owner_role":str,"trigger":str,'
            '"steps":[{"seq":int,"action":str,"sla":str}],"escalation":str,"review_cycle":str}]}}'
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["sop"]}

    def run(self, business_model: dict, _engine=None, context: dict = None) -> dict:
        if _engine is None:
            from app.engines.sop_report_engine import SOPReportEngine
            _engine = SOPReportEngine()
        report = _engine.generate_full_sop_report(business_model, enable_ai_analysis=True)
        user_prompt = f"SOP 报告：{report}\n请结构化为 sop 集合。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
