# app/orchestrator/agents/planner.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class PlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Planner Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Planner Agent。职责：理解用户的业务点子，明确目标、业务边界、组织结构与规模。\n"
            "必须只输出 JSON，格式：\n"
            "{\n"
            '  "project": {"name":str,"goal":str,"industry":str,'
            '   "scope":{"in_scope":[str],"out_scope":[str]},'
            '   "actors":[{"role":str,"description":str}]},\n'
            '  "requirements": [{"id":str,"text":str,"priority":"high|mid|low","source":str}]\n'
            "}"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["project", "requirements"]}

    def run(self, idea: str, context: dict = None) -> dict:
        user_prompt = f"用户的业务点子：{idea}\n请产出 project 与 requirements。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
