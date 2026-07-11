# app/orchestrator/agents/reviewer.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Reviewer Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Reviewer Agent。职责：审查业务模型与 SOP，找漏洞（尤其缺复审/升级机制/SLA）。\n"
            "必须输出 JSON：\n"
            '{"review":{"approved":bool,'
            ' "gaps":[{"id":str,"severity":"high|medium|low","type":str,"desc":str,'
            '          "suggested_fix":str,"target":"ba|sop"}],'
            ' "loopback_target":"ba|sop|null",'
            ' "summary":str}}'
            "\n若存在 high 级漏洞，loopback_target 指向需重做的段（ba 或 sop），否则 null。"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["review"]}

    def run(self, project: dict, business_model: dict, sop: dict, context: dict = None) -> dict:
        user_prompt = f"项目：{project}\n业务模型：{business_model}\nSOP：{sop}\n请审查并产出 review。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
