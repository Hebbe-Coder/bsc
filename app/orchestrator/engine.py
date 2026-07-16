# app/orchestrator/engine.py
from __future__ import annotations
import asyncio
from typing import Optional
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.orchestrator.sse import SessionEventBus


class OrchestratorEngine:
    STAGES = ["planner", "architect", "sop", "reviewer", "presenter"]
    MAX_LOOP = 3  # 最多回环次数

    def __init__(self, agents: dict, repo: Optional[ProjectDraftRepository] = None,
                 bus: Optional[SessionEventBus] = None):
        self.agents = agents
        self.repo = repo or ProjectDraftRepository()
        self.bus = bus or SessionEventBus()

    async def _emit(self, sid, stage, status, msg=""):
        await self.bus.publish(sid, {"stage": stage, "status": status, "msg": msg})

    async def run_pipeline(self, session_id: str, idea: str) -> dict:
        draft = self.repo.get(session_id) or ProjectDraft(session_id=session_id, idea=idea)
        state = draft.to_dict()
        await self._emit(session_id, "planner", "running", "正在识别行业与边界")
        out = await self._call("planner", idea=idea)
        state["project"] = out.get("project", {})
        state["requirements"] = out.get("requirements", [])
        self._save(session_id, state)
        await self._emit(session_id, "planner", "done", "项目与目标已明确")

        await self._emit(session_id, "architect", "running", "正在构建流程")
        out = await self._call("architect", idea=idea,
                               project=state["project"], requirements=state["requirements"])
        state["business_model"] = out.get("business_model", {})
        self._save(session_id, state)
        await self._emit(session_id, "architect", "done", "业务架构已生成")

        # FORK: sop || risk（二者仅依赖 business_model，真并行）
        await self._emit(session_id, "sop", "running", "正在生成 SOP")
        await self._emit(session_id, "risk", "running", "正在评估约束与风险（并行）")
        sop_fut = asyncio.to_thread(self._call_sync, "sop", business_model=state["business_model"])
        risk_fut = asyncio.to_thread(self._call_sync, "risk",
                                     business_model=state["business_model"],
                                     requirements=state.get("requirements", []))
        sop_out, risk_out = await asyncio.gather(sop_fut, risk_fut)
        state["sop"] = sop_out.get("sop", {})
        state["risk"] = risk_out.get("risk", {})
        self._save(session_id, state)
        await self._emit(session_id, "sop", "done", "SOP 已生成")
        await self._emit(session_id, "risk", "done", "约束与风险评估完成")

        # Reviewer + 受控回环
        loop_count = 0
        while True:
            await self._emit(session_id, "reviewer", "running", "正在审查约束覆盖率与漏洞")
            out = await self._call("reviewer",
                                   project=state["project"], business_model=state["business_model"],
                                   sop=state["sop"], risk=state["risk"],
                                   requirements=state.get("requirements", []))
            review = out.get("review", {})
            state["review"] = review
            self._save(session_id, state)

            coverage = review.get("constraint_coverage", {})
            coverage_pct = coverage.get("coverage_pct", 100)
            gaps = review.get("gaps", [])
            high_gaps = [g for g in gaps if g.get("severity") == "high"]

            if review.get("approved") or loop_count >= self.MAX_LOOP:
                msg = review.get("summary", "审查完成")
                if coverage_pct < 100:
                    msg += f" | 约束覆盖率 {coverage_pct}%"
                if high_gaps and loop_count >= self.MAX_LOOP:
                    msg += f" | 已达最大回环次数({self.MAX_LOOP})，仍有 {len(high_gaps)} 项高危缺口未覆盖"
                await self._emit(session_id, "reviewer", "done", msg)
                break

            target = review.get("loopback_target")
            fixes = review.get("loopback_fixes", [])
            # 兜底：若无 loopback_fixes，从 gaps 提取 suggested_fix
            if not fixes:
                fixes = [g.get("suggested_fix", "") for g in high_gaps if g.get("suggested_fix")]

            if target == "sop":
                await self._emit(session_id, "sop", "loopback",
                                 f"↺ 打回 SOP 重做（第{loop_count+1}次回环），需补齐 {len(high_gaps)} 项缺口")
                out = await self._call("sop", business_model=state["business_model"],
                                       fix_instructions=fixes)
                state["sop"] = out.get("sop", {})
            elif target == "architect":
                await self._emit(session_id, "architect", "loopback",
                                 f"↺ 打回 Architect 重做（第{loop_count+1}次回环），需补齐 {len(high_gaps)} 项缺口")
                out = await self._call("architect", idea=idea,
                                       project=state["project"], requirements=state["requirements"],
                                       fix_instructions=fixes)
                state["business_model"] = out.get("business_model", {})
            else:
                await self._emit(session_id, "reviewer", "done", "无回环目标，审查完成")
                break

            self._save(session_id, state)
            loop_count += 1
            await self._emit(session_id, "reviewer", "running", f"第{loop_count+1}轮审查中…")

        await self._emit(session_id, "presenter", "running", "正在生成汇报材料")
        out = await self._call("presenter", session_id=session_id, state=state)
        state["presentation"] = out.get("presentation", {})
        self._save(session_id, state)
        await self._emit(session_id, "presenter", "done", "汇报材料已生成")
        return state

    async def rerun_node(self, session_id: str, node: str) -> dict:
        """定点重跑单节点（仅允许 architect/sop/reviewer/presenter）。"""
        if node not in ("architect", "sop", "reviewer", "presenter"):
            raise ValueError(f"不允许重跑 {node}")
        draft = self.repo.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        state = draft.to_dict()
        await self._emit(session_id, node, "running", f"定点重跑 {node}")
        kwargs = self._upstream_for(node, state)
        out = await self._call(node, **kwargs)
        seg = {"architect": "business_model", "sop": "sop",
               "reviewer": "review", "presenter": "presentation"}[node]
        state[seg] = out.get(seg, out)
        self._save(session_id, state)
        await self._emit(session_id, node, "done", f"{node} 已重跑")
        return state

    def _call_sync(self, name, **kwargs):
        agent = self.agents[name]
        return agent.run(**kwargs)

    async def _call(self, name, **kwargs):
        agent = self.agents[name]
        if asyncio.iscoroutinefunction(agent.run):
            return await agent.run(**kwargs)
        return agent.run(**kwargs)

    def _upstream_for(self, node, state):
        if node == "architect":
            return {"idea": state["idea"], "project": state["project"], "requirements": state["requirements"]}
        if node == "sop":
            return {"business_model": state["business_model"]}
        if node == "reviewer":
            return {"project": state["project"], "business_model": state["business_model"],
                    "sop": state["sop"], "requirements": state.get("requirements", [])}
        if node == "presenter":
            return {"session_id": state["session_id"], "state": state}
        return {}

    def _save(self, session_id, state):
        draft = ProjectDraft(
            session_id=session_id, idea=state.get("idea", ""),
            project=state.get("project", {}), requirements=state.get("requirements", []),
            business_model=state.get("business_model", {}), sop=state.get("sop", {}),
            risk=state.get("risk", {}), review=state.get("review", {}),
            presentation=state.get("presentation", {}),
            status="running", messages=state.get("messages", []),
        )
        self.repo.save(draft)
