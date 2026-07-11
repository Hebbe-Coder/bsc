# app/orchestrator/engine.py
from __future__ import annotations
import asyncio
from typing import Optional
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.orchestrator.sse import SessionEventBus


class OrchestratorEngine:
    STAGES = ["planner", "architect", "sop", "reviewer", "presenter"]

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

        await self._emit(session_id, "sop", "running", "正在生成 SOP")
        out = await self._call("sop", business_model=state["business_model"])
        state["sop"] = out.get("sop", {})
        self._save(session_id, state)
        await self._emit(session_id, "sop", "done", "SOP 已生成")

        # Reviewer + 受控回环（≤1）
        loop_count = 0
        while True:
            await self._emit(session_id, "reviewer", "running", "正在审查漏洞")
            out = await self._call("reviewer",
                                   project=state["project"], business_model=state["business_model"],
                                   sop=state["sop"])
            review = out.get("review", {})
            state["review"] = review
            self._save(session_id, state)
            if review.get("approved") or loop_count >= 1:
                await self._emit(session_id, "reviewer", "done", review.get("summary", "审查完成"))
                break
            target = review.get("loopback_target")
            await self._emit(session_id, target, "loopback", f"↺ 打回 {target} 重做")
            if target == "sop":
                out = await self._call("sop", business_model=state["business_model"])
                state["sop"] = out.get("sop", {})
            elif target == "architect":
                out = await self._call("architect", idea=idea,
                                       project=state["project"], requirements=state["requirements"])
                state["business_model"] = out.get("business_model", {})
            self._save(session_id, state)
            loop_count += 1
            await self._emit(session_id, "reviewer", "running", "重新审查")

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

    async def _call(self, name, **kwargs):
        # 注意：session_id 仅当 agent 真正需要时才放入 kwargs（如 presenter），
        # 不在本方法签名里保留未使用的 session_id 形参，否则会吞掉 presenter 的 session_id。
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
            return {"project": state["project"], "business_model": state["business_model"], "sop": state["sop"]}
        if node == "presenter":
            return {"session_id": state["session_id"], "state": state}
        return {}

    def _save(self, session_id, state):
        draft = ProjectDraft(
            session_id=session_id, idea=state.get("idea", ""),
            project=state.get("project", {}), requirements=state.get("requirements", []),
            business_model=state.get("business_model", {}), sop=state.get("sop", {}),
            review=state.get("review", {}), presentation=state.get("presentation", {}),
            status="running", messages=state.get("messages", []),
        )
        self.repo.save(draft)
