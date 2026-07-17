from __future__ import annotations
import json
from app.agents.base_agent import BaseAgent
from app.constraint.engine import evaluate as evaluate_constraints


SYSTEM_PROMPT = (
    "你是 Risk Architect Agent（约束系统）。职责：基于业务模型与可选 SOP，评估业务风险并生成风险清单。\n"
    "输入：business_model（flows/roles/rules），可选 sop、kpi。\n"
    "请产出 JSON：\n"
    '{"risk":{"overall_score":"low|medium|high",'
    '"risks":[{"id":str,"category":str,"description":str,"likelihood":"low|medium|high",'
    '"impact":"low|medium|high","mitigation":str,"owner_role":str}]}}'
)


class RiskArchitectAgent(BaseAgent):
    def __init__(self, llm_service=None):
        super().__init__(llm_service=llm_service)

    @property
    def name(self) -> str:
        return "Risk Architect Agent"

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def output_schema(self) -> dict:
        return {"required": ["risk"]}

    def run(self, business_model: dict, sop: dict = None, kpi: dict = None,
            requirements: list = None, context: dict = None) -> dict:
        user_prompt = (
            f"业务模型：{json.dumps(business_model, ensure_ascii=False)}\n"
            f"SOP：{json.dumps(sop or {}, ensure_ascii=False)}\n"
            f"KPI：{json.dumps(kpi or {}, ensure_ascii=False)}\n"
            f"请评估风险并产出 risk。"
        )
        risk_payload = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        if not isinstance(risk_payload, dict):
            risk_payload = {}
        risk_payload = risk_payload.get("risk", {})
        result = evaluate_constraints(
            business_model=business_model, sop=sop,
            requirements=requirements or [],
            risk_payload=risk_payload,
        )
        return {"risk": result.model_dump()}
