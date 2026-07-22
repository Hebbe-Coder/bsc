# app/orchestrator/agents/sop_builder.py
from __future__ import annotations
import json
from typing import Optional
from app.agents.base_agent import BaseAgent
from app.orchestrator.methodology import (
    derive_methodology_query,
    validate_source_refs,
)


class SopBuilderAgent(BaseAgent):
    def __init__(self, llm_service=None, bridge=None):
        """构造 SOP Builder Agent，可注入 MethodologyBridge 以检索方法论依据。"""
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
        return "SOP Builder Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 SOP Builder Agent。职责：把 SOP 报告结构化为最终 SOP 集合。\n"
            "输入是 SOPReportEngine 生成的报告（含 workflow/roles/sla）。\n"
            "若提供了 fix_instructions（回环修复指令），必须据此补充或修改 SOP，"
            "确保每个未覆盖的约束都有对应的 SOP 流程步骤/闭环管控/复盘机制。\n"
            "请产出 JSON：\n"
            '{"sop":{"sops":[{"id":str,"title":str,"owner_role":str,"trigger":str,'
            '"steps":[{"seq":int,"action":str,"sla":str}],'
            '"escalation":str,"review_cycle":str,"covers_constraints":[str],'
            '"source_ref":[str]}]}}\n'
            "溯源约束：每个 sop 项必须包含 source_ref 字段，"
            "其值只能引用「方法论依据」章节中出现的 chunk_id；"
            "若未检索到方法论依据，则 source_ref 必须为 []。"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["sop"]}

    def run(self, business_model: dict, _engine=None, context: dict = None,
            fix_instructions: list = None, project_id: Optional[str] = None) -> dict:
        if _engine is None:
            from app.engines.sop_report_engine import SOPReportEngine
            _engine = SOPReportEngine()
        report = _engine.generate_full_sop_report(business_model, enable_ai_analysis=True)
        parts = [f"SOP 报告：{json.dumps(report, ensure_ascii=False, default=str)}"]
        if fix_instructions:
            parts.append(f"⚠ 回环修复指令（必须逐条落实）：{json.dumps(fix_instructions, ensure_ascii=False)}")
            parts.append("请在生成的 SOP 中为每个修复指令添加对应的流程步骤，并在 covers_constraints 中标注覆盖的约束 ID。")
        else:
            parts.append("请结构化为 sop 集合。")

        # 若提供 project_id，则检索方法论依据并前置到 user_prompt
        citations = []
        wiki_context = {
            "knowledge_context_used": False,
            "context_block": "",
            "context_pack_id": "",
            "page_ids": [],
            "source_ids": [],
            "assumptions": [],
        }
        growth_context = {
            "knowledge_context_used": False,
            "context_type": "growth",
            "availability": "disabled",
            "context_block": "",
        }
        if project_id:
            bridge = self._get_bridge()
            out = bridge.retrieve(
                project_id, derive_methodology_query(business_model)
            )
            citations = out.get("citations") or []
            growth_retriever = getattr(bridge, "retrieve_growth_context", None)
            if growth_retriever is not None:
                growth_context = growth_retriever(
                    project_id, derive_methodology_query(business_model)
                )
            wiki_context = {
                "knowledge_context_used": False,
                "context_type": "wiki",
                "context_block": "",
            }
            if not growth_context.get("context_block"):
                wiki_context = bridge.retrieve_wiki_context(
                    project_id, derive_methodology_query(business_model)
                )
            selected_context = growth_context if growth_context.get("context_block") else wiki_context
            if selected_context.get("context_block"):
                if selected_context.get("context_type") == "growth":
                    context_heading = "Project Growth Context (A/B/C/D evidence, exact revisions, and assumptions)"
                else:
                    context_heading = "Project Wiki Context (project evidence; retain source IDs and assumptions)"
                parts.insert(
                    0,
                    f"\n## {context_heading}\n"
                    + selected_context["context_block"] + "\n",
                )
            if out.get("context_block"):
                parts.insert(
                    0,
                    "\n## 方法论依据（检索自方法论库，生成 SOP 时只能引用下列 chunk_id）\n"
                    + out["context_block"] + "\n",
                )

        user_prompt = "\n".join(parts)
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        # 仅当发生检索时附加溯源覆盖率指标，无 project_id 路径行为保持不变
        if citations:
            items = (result.get("sop") or {}).get("sops") or []
            cov = validate_source_refs(items, citations)
            # 内联进 sop 子段：引擎 state["sop"] = out.get("sop") 入库时指标才得以保留
            result.setdefault("sop", {})["_citation_coverage"] = cov
        if project_id:
            selected_context = growth_context if growth_context.get("knowledge_context_used") else wiki_context
            result.setdefault("sop", {})["_knowledge_context"] = {
                key: value for key, value in selected_context.items() if key != "context_block"
            }
        return result
