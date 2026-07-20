"""Studio Orchestrator v4 — 统一使用主链路 LLM Agent。

v3: Star-topology with 正则 BU + protocol Agent（本地启发式）
v4: 统一到主链路 BSCPipeline（LLM），通过适配层对接 BusinessComposer

同一份 PRD 不再产出两种不同结果。
"""
from dataclasses import dataclass, field
import time, uuid, logging

logger = logging.getLogger("bsc.studio.orchestrator")

@dataclass
class StudioResult:
    run_id: str = ""
    domain: str = ""
    workspace: dict = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)
    total_ms: float = 0.0
    summary: str = ""

    def to_dict(self):
        return {
            "run_id": self.run_id, "domain": self.domain,
            "workspace": self.workspace, "stages": self.stages,
            "total_ms": self.total_ms, "summary": self.summary,
        }

class StudioOrchestrator:
    """统一架构：调用主链路 BSCPipeline (LLM) + 适配层 + BusinessComposer + AssetAgent。"""

    def execute(self, question: str, input_text: str = "", project_name: str = "Quick",
                output_types: list[str] = None, domain: str = "") -> StudioResult:
        if output_types is None:
            output_types = ["ppt", "html"]
        t0 = time.perf_counter()
        run_id = str(uuid.uuid4())[:8]
        stages = []

        # ------ Stage 1: 调用主链路 BSC Pipeline (LLM) ------
        t1 = time.perf_counter()
        bs = {}
        adapted_bm = {}
        try:
            from app.capabilities.runner import run_legacy_bsc_runtime_sync
            pipeline_result = run_legacy_bsc_runtime_sync(
                input_text=input_text or question,
                async_mode=False,
            )
            bs = pipeline_result.get("business_system", {})
            detected_domain = bs.get("business_domain", "general")
            if not domain:
                domain = detected_domain

            # 从 pipeline stages 提取各 agent 状态
            for stage in pipeline_result.get("pipeline", {}).get("stages", []):
                stages.append({
                    "agent": stage.get("key", stage.get("agent", "")),
                    "display": stage.get("display", ""),
                    "status": "done" if stage.get("status") == "success" else stage.get("status", "error"),
                    "duration_ms": stage.get("duration_ms", 0),
                })

            if not stages:
                stages.append({"agent": PipelineStage.BUSINESS_UNDERSTANDING, "display": "Business Understanding",
                               "status": "done", "duration_ms": round((time.perf_counter()-t1)*1000, 1)})

            logger.info(f"✓ BSC Pipeline (LLM) completed: domain={domain}")
        except Exception as e:
            logger.exception("BSC Pipeline failed")
            stages.append({"agent": "pipeline", "display": "BSC Pipeline (LLM)",
                           "status": "error", "error": str(e)[:100], "duration_ms": 0})

        # 适配 LLM Agent 输出到 BusinessComposer 期望的格式
        adapted_bm = self._adapt_business_model(bs)
        adapted_sop = self._adapt_sop(bs)
        adapted_risk = self._adapt_risk(bs)
        adapted_strategy = self._adapt_strategy(bs)
        adapted_opt = self._adapt_optimization(bs)

        # ------ Stage 2: Business Composer ------
        t2 = time.perf_counter()
        summary = "Business analysis complete"
        try:
            from app.agents.business_composer import BusinessComposer
            composer = BusinessComposer()
            workspace = composer.compose(adapted_bm, adapted_sop, adapted_risk,
                                         adapted_strategy, adapted_opt, domain)
            ws = workspace.to_dict()
            summary = workspace.summary
            stages.append({"agent": PipelineStage.COMPOSER, "display": "Business Composer",
                           "status": "done", "duration_ms": round((time.perf_counter()-t2)*1000, 1)})
        except Exception as e:
            logger.exception("Composer failed")
            ws = {"business_model": adapted_bm, "sop": adapted_sop, "risks": adapted_risk,
                  "strategy": adapted_strategy, "optimization": adapted_opt,
                  "dashboard": {}, "summary": "Composition failed"}
            stages.append({"agent": PipelineStage.COMPOSER, "display": "Business Composer",
                           "status": "error", "error": str(e)[:100], "duration_ms": 0})

        # ------ Stage 3: Asset Generation (PPT/HTML) ------
        if output_types:
            t3 = time.perf_counter()
            try:
                from app.agents.asset_agent import AssetAgent, AgentContext
                ctx = AgentContext(project_name=project_name, domain=domain, business_system=adapted_bm)
                agent = AssetAgent()
                agent.on_generate(ctx, output_types=output_types)
                ws["assets"] = ctx.assets.get("assets", []) if hasattr(ctx, "assets") else []
                stages.append({"agent": "asset", "display": "Asset Generator",
                               "status": "done", "duration_ms": round((time.perf_counter()-t3)*1000, 1)})
            except Exception as e:
                logger.exception("Asset generation failed")
                ws["assets"] = []
                stages.append({"agent": "asset", "display": "Asset Generator",
                               "status": "error", "error": str(e)[:100], "duration_ms": 0})

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        return StudioResult(run_id=run_id, domain=domain, workspace=ws, stages=stages,
                            total_ms=total_ms, summary=summary)

    # ============================================================
    # 适配层：LLM Agent 输出 → BusinessComposer 期望格式
    # ============================================================

    @staticmethod
    def _adapt_business_model(bs: dict) -> dict:
        """LLM BU 输出 → BusinessComposer 期望的 business_model 格式"""
        objectives = bs.get("objectives", [])
        workflow = bs.get("workflow", [])
        metrics = bs.get("metrics") or bs.get("kpi", [])
        risks = bs.get("risks", [])
        return {
            "objectives": objectives,
            "processes": [{"name": w.get("name", ""), "step": w.get("step", "")} for w in workflow],
            "metrics": metrics,
            "risks": risks,
            "constraints": [],
            "domain": bs.get("business_domain", "general"),
            "complexity": "medium",
        }

    @staticmethod
    def _adapt_sop(bs: dict) -> dict:
        """LLM SOP 输出 → BusinessComposer 期望的 sop 格式"""
        workflow = bs.get("workflow", [])
        return {
            "sop": [{"step": w.get("step", ""), "name": w.get("name", ""),
                      "action": w.get("action", "")} for w in workflow],
            "total_steps": len(workflow),
            "roles": bs.get("roles", []),
        }

    @staticmethod
    def _adapt_risk(bs: dict) -> dict:
        """LLM Risk 输出 → BusinessComposer 期望的 risk 格式"""
        risks = bs.get("risks", [])
        high_count = sum(1 for r in risks
                         if str(r.get("severity", "")).lower() in ("high", "critical", "严重", "高"))
        return {
            "risks": [{"name": r.get("risk", ""),
                        "severity": r.get("severity", "medium"),
                        "category": r.get("category", "operational")} for r in risks],
            "summary": {"total": len(risks), "high": high_count},
        }

    @staticmethod
    def _adapt_strategy(bs: dict) -> dict:
        """LLM Strategy 输出 → BusinessComposer 期望的 strategy 格式"""
        strategy = bs.get("strategy", {})
        growth = strategy.get("growth_opportunities", [])
        return {
            "recommendations": [{"name": g.get("opportunity", ""),
                                   "potential": g.get("potential", "")} for g in growth],
        }

    @staticmethod
    def _adapt_optimization(bs: dict) -> dict:
        """LLM Optimization 输出 → BusinessComposer 期望的 optimization 格式"""
        opt = bs.get("optimization", {})
        recs = opt.get("recommendations", [])
        return {
            "bottlenecks": [{"step": r.get("id", ""), "name": r.get("title", ""),
                              "suggestion": r.get("description", "")} for r in recs],
            "automation_potential": {"automation_rate": 0},
        }


_studio_orch: StudioOrchestrator = None

def get_studio_orchestrator() -> StudioOrchestrator:
    global _studio_orch
    if _studio_orch is None:
        _studio_orch = StudioOrchestrator()
    return _studio_orch
