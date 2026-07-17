# app/orchestrator/agents/business_architect.py
from __future__ import annotations
import json
from typing import Optional
from app.agents.base_agent import BaseAgent
from app.orchestrator.methodology import (
    derive_methodology_query,
    validate_source_refs,
)


class BusinessArchitectAgent(BaseAgent):
    def __init__(self, llm_service=None, bridge=None):
        """构造 Business Architect Agent，可注入 MethodologyBridge 以检索方法论依据。"""
        super().__init__(llm_service)
        self._bridge = bridge

    def _get_bridge(self):
        """惰性获取 MethodologyBridge（未注入时自动构建默认实例）。"""
        if self._bridge is None:
            from app.orchestrator.methodology import MethodologyBridge
            self._bridge = MethodologyBridge()
        return self._bridge

    @property
    def name(self) -> str:
        return "Business Architect Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Business Architect Agent。职责：把已编译的业务系统结构化为业务模型。\n"
            "输入是编译后的 business_system（含流程/角色）。\n"
            "若提供了 fix_instructions（回环修复指令），必须据此补充或修改 business_model，"
            "确保每个未覆盖的约束都有对应的流程或规则。\n"
            "请产出 JSON：\n"
            '{"business_model":{"flows":[{"id":str,"name":str,"description":str,'
            '"steps":[str],"input":str,"output":str,"source_ref":[str]}],'
            ' "roles":[{"id":str,"name":str,"responsibility":str,"belongs_to_flow":str,'
            '"source_ref":[str]}],'
            ' "rules":[{"id":str,"statement":str,"applies_to":str,"covers_constraints":[str],'
            '"source_ref":[str]}]}}\n'
            "溯源约束：flows/roles/rules 中每个元素必须包含 source_ref 字段，"
            "其值只能引用「方法论依据」章节中出现的 chunk_id；"
            "若未检索到方法论依据，则 source_ref 必须为 []。"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["business_model"]}

    async def run(self, idea: str, project: dict, requirements: list,
                  _compile=None, context: dict = None,
                  fix_instructions: list = None,
                  project_id: Optional[str] = None) -> dict:
        if _compile is None:
            from app.core.async_pipeline import compile_to_business_system_async
            _compile = compile_to_business_system_async
        bs = await _compile(idea, llm_service=self.llm_service)
        parts = [
            f"项目：{json.dumps(project, ensure_ascii=False)}",
            f"需求：{json.dumps(requirements, ensure_ascii=False)}",
            f"已编译业务系统：{json.dumps(bs, ensure_ascii=False, default=str)}",
        ]
        if fix_instructions:
            parts.append(f"⚠ 回环修复指令（必须逐条落实）：{json.dumps(fix_instructions, ensure_ascii=False)}")
            parts.append("请在 business_model 中为每个修复指令添加对应的流程或规则，并在 covers_constraints 中标注覆盖的约束 ID。")
        else:
            parts.append("请结构化为 business_model。")

        # 若提供 project_id，则检索方法论依据并前置到 user_prompt
        citations = []
        if project_id:
            out = self._get_bridge().retrieve(
                project_id, derive_methodology_query(project)
            )
            citations = out.get("citations") or []
            if out.get("context_block"):
                parts.insert(
                    0,
                    "\n## 方法论依据（检索自方法论库，生成 business_model 时只能引用下列 chunk_id）\n"
                    + out["context_block"] + "\n",
                )

        user_prompt = "\n".join(parts)
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        # 仅当发生检索时附加溯源覆盖率指标，无 project_id 路径行为保持不变
        if citations:
            bm = result.get("business_model") or {}
            items = (bm.get("flows") or []) + (bm.get("roles") or []) + (bm.get("rules") or [])
            cov = validate_source_refs(items, citations)
            # 内联进 business_model 子段：引擎 state["business_model"] 入库时指标才得以保留
            result.setdefault("business_model", {})["_citation_coverage"] = cov
        return result
