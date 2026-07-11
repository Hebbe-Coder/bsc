# app/orchestrator/agents/business_architect.py
from __future__ import annotations
import asyncio
from app.agents.base_agent import BaseAgent


class BusinessArchitectAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Business Architect Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Business Architect Agent。职责：把已编译的业务系统结构化为业务模型。\n"
            "输入是编译后的 business_system（含流程/角色）。请产出 JSON：\n"
            '{"business_model":{"flows":[{"id":str,"name":str,"description":str,'
            '"steps":[str],"input":str,"output":str}],'
            ' "roles":[{"id":str,"name":str,"responsibility":str,"belongs_to_flow":str}],'
            ' "rules":[{"id":str,"statement":str,"applies_to":str}]}}'
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["business_model"]}

    async def run(self, idea: str, project: dict, requirements: list,
                  _compile=None, context: dict = None) -> dict:
        if _compile is None:
            from app.core.async_pipeline import compile_to_business_system_async
            _compile = compile_to_business_system_async
        bs = await _compile(idea, llm_service=self.llm_service)
        user_prompt = (
            f"项目：{project}\n需求：{requirements}\n"
            f"已编译业务系统：{bs}\n请结构化为 business_model。"
        )
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
