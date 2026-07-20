"""
Async BSC Pipeline - 异步流程编排器

使用asyncio.gather()实现阶段级并行执行，提升编译性能。

并行策略：
1. Business Understanding → 串行（必须先执行）
2. SOP + Risk + Strategy + Optimization → 并行（无依赖）
3. Business Composer → 串行（依赖所有分析结果）

性能预期：
- 串行模式：T = T_bu + T_sop + T_risk + T_strategy + T_optimization + T_composer
- 并行模式：T = T_bu + max(T_sop, T_risk, T_strategy, T_optimization) + T_composer
- 提升：约50%+（取决于各阶段耗时分布）

缓存策略：
- 基于PRD内容哈希的缓存键
- Pipeline级缓存（TTL 7200秒）
- 阶段级缓存（TTL 3600秒）
"""
from __future__ import annotations
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional

from app.utils.common import flatten_risks, build_cache_key
from app.enums import PipelineStage

logger = logging.getLogger(__name__)

_CACHE_ENABLED = False


class AsyncBSCPipeline:
    """
    异步BSC流程编排器
    
    使用异步LLM服务和asyncio.gather()实现并行执行。
    """

    AGENT_INFO_MAP = {
        PipelineStage.SOP: ("SOP Agent", "流程设计"),
        PipelineStage.RISK: ("Risk Agent", "风险分析"),
        PipelineStage.STRATEGY: ("Strategy Agent", "战略分析"),
        PipelineStage.OPTIMIZATION: ("Optimization Agent", "优化建议"),
        PipelineStage.ROOT_CAUSE: ("Root Cause Agent", "根因分析"),
    }

    def __init__(self, llm_service=None, stream_id: str = None):
        """
        初始化异步Pipeline
        
        Args:
            llm_service: LLM服务实例（可选，用于依赖注入）
            stream_id: SSE流ID（可选，用于实时进度推送）
        """
        from app.core.planner import Planner
        
        self._llm_service = llm_service
        self._async_llm_service = None
        self._planner = Planner()
        self._stream_id = stream_id
        self._current_stage = 0
        self._total_stages = 6
    
    def _set_stream_id(self, stream_id: str):
        """设置流ID"""
        self._stream_id = stream_id
    
    async def _emit_stage_start(self, stage: str, display: str):
        """发布阶段开始事件"""
        if self._stream_id:
            try:
                from app.engines.stream_emitter import get_stream_emitter
                emitter = get_stream_emitter()
                await emitter.stage_start(self._stream_id, stage, display, self._total_stages)
            except Exception as e:
                logger.debug(f"Failed to emit stage_start: {e}")
    
    async def _emit_stage_progress(self, stage: str, display: str, progress: int, message: str = ""):
        """发布阶段进度事件"""
        if self._stream_id:
            try:
                from app.engines.stream_emitter import get_stream_emitter
                emitter = get_stream_emitter()
                await emitter.stage_progress(self._stream_id, stage, display, progress, message)
            except Exception as e:
                logger.debug(f"Failed to emit stage_progress: {e}")
    
    async def _emit_stage_complete(self, stage: str, display: str, duration_ms: int, success: bool = True, error: str = ""):
        """发布阶段完成事件"""
        if self._stream_id:
            try:
                from app.engines.stream_emitter import get_stream_emitter
                emitter = get_stream_emitter()
                await emitter.stage_complete(self._stream_id, stage, display, duration_ms, success, error)
            except Exception as e:
                logger.debug(f"Failed to emit stage_complete: {e}")
    
    async def _emit_agent_status(self, agent_name: str, status: str, message: str = "", elapsed_ms: int = 0):
        """发布Agent状态事件"""
        if self._stream_id:
            try:
                from app.engines.stream_emitter import get_stream_emitter
                emitter = get_stream_emitter()
                await emitter.agent_status(self._stream_id, agent_name, status, message, elapsed_ms)
            except Exception as e:
                logger.debug(f"Failed to emit agent_status: {e}")

    @property
    def async_llm_service(self):
        """获取异步LLM服务"""
        if self._async_llm_service is None:
            from app.services.async_llm_service import get_async_llm_service
            
            if self._llm_service:
                from app.services.async_llm_service import AsyncLLMService
                self._async_llm_service = AsyncLLMService()
                self._async_llm_service._sync_service = self._llm_service
            else:
                self._async_llm_service = get_async_llm_service()
        
        return self._async_llm_service

    async def execute(self, prd_content: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        异步执行完整BSC流程
        
        Args:
            prd_content: PRD文本内容
            context: 初始上下文
        
        Returns:
            dict: 包含所有Agent结果和执行状态的完整输出
        """
        t0 = time.perf_counter()
        flow_context = context or {}
        
        if "stream_id" in flow_context:
            self._set_stream_id(flow_context["stream_id"])
        
        chunks = [{"chunk_id": "001", "content": prd_content}]

        cache = self._get_cache()
        full_cache_key = build_cache_key("pipeline", prd_content, namespace="bsc:async")
        
        if _CACHE_ENABLED and cache and cache.exists(full_cache_key):
            cached_result = cache.get(full_cache_key)
            logger.info(f"✓ Async Pipeline result from cache")
            if self._stream_id:
                await self._emit_stage_progress("pipeline", "管道执行", 100, "从缓存加载结果")
                await self._emit_stage_complete("pipeline", "管道执行", 0, success=True)
            return cached_result

        results = self._create_initial_results(prd_content)
        
        self._current_stage = 1
        await self._emit_stage_start("business_understanding", "业务理解")
        
        bu_cache_key = build_cache_key("stage", prd_content, "business_understanding", namespace="bsc:async")
        if _CACHE_ENABLED and cache and cache.exists(bu_cache_key):
            bu_result = cache.get(bu_cache_key)
            logger.info(f"✓ Business Understanding from cache")
            await self._emit_stage_progress("business_understanding", "业务理解", 100, "从缓存加载")
        else:
            await self._emit_stage_progress("business_understanding", "业务理解", 20, "正在分析PRD文档...")
            bu_result = await self._execute_business_understanding(chunks, flow_context)
            if _CACHE_ENABLED and cache:
                cache.set(bu_cache_key, bu_result, ttl=3600)
        
        await self._emit_stage_complete(
            "business_understanding", "业务理解", 
            bu_result["stage"]["duration_ms"],
            bu_result["stage"]["status"] == "success",
            bu_result["stage"].get("error", "")
        )
        
        results = self._collect_stage_result(results, bu_result, "business_understanding")
        flow_context["business_understanding"] = bu_result["result"]

        if bu_result["stage"]["status"] == "failed":
            return self._prepare_failed_result(results, t0, "业务理解阶段出错")

        self._current_stage = 2
        await self._emit_stage_start("analysis", "并行分析")
        
        analysis_results = await self._execute_parallel_analysis(chunks, flow_context, cache=cache)
        
        for agent_key, result in analysis_results.items():
            display_name = self.AGENT_INFO_MAP.get(agent_key, ('', ''))[1]
            await self._emit_stage_complete(
                agent_key, display_name,
                result["stage"]["duration_ms"],
                result["stage"]["status"] == "success",
                result["stage"].get("error", "")
            )
        
        results = self._collect_parallel_results(results, analysis_results, flow_context)

        self._current_stage = 5
        await self._emit_stage_start("composer", "结果组装")
        
        composer_result = await self._execute_composer(results, flow_context)
        
        await self._emit_stage_complete(
            "composer", "结果组装",
            composer_result["stage"]["duration_ms"],
            composer_result["stage"]["status"] == "success",
            composer_result["stage"].get("error", "")
        )
        
        results = self._collect_stage_result(results, composer_result, "composed")
        flow_context["composed"] = composer_result["result"]

        results = self._prepare_workspace_result(results, composer_result)

        total_ms = int((time.perf_counter() - t0) * 1000)
        results["total_ms"] = total_ms
        results["parallel"] = True
        logger.info(f"Async BSC Pipeline completed in {total_ms}ms")

        if _CACHE_ENABLED and cache:
            cache.set(full_cache_key, results, ttl=7200)

        return results

    def _get_cache(self):
        """获取缓存服务实例"""
        try:
            from app.services.cache_service import get_cache_service
            return get_cache_service()
        except Exception:
            return None

    def _create_initial_results(self, prd_content: str) -> Dict[str, Any]:
        """创建初始结果字典"""
        return {
            "prd_content": prd_content,
            "stages": [],
            "total_ms": 0,
            "summary": "",
            "parallel": False,
        }

    async def _execute_business_understanding(self, chunks: List[Dict[str, str]], 
                                              context: Dict[str, Any]) -> Dict[str, Any]:
        """异步执行业务理解阶段"""
        logger.info("→ Business Understanding（业务理解）")
        return await self._execute_stage_async("business_understanding", "业务理解", chunks, context)

    async def _execute_parallel_analysis(self, chunks: List[Dict[str, str]], 
                                          context: Dict[str, Any], 
                                          cache=None) -> Dict[str, Dict[str, Any]]:
        """异步并行执行分析Agent（基于Planner动态规划）"""
        logger.info("→ Agent Orchestrator（按Planner规划并行执行）")
        
        plan = self._planner.plan(chunks)
        logger.info(f"→ Planner规划: 需要执行 {len(plan['agents'])} 个Agent")
        
        prd_content = chunks[0]["content"] if chunks else ""
        execution_order = plan.get("execution_order", [])
        
        independent_agents = []
        dependent_agents = []
        
        for agent_key in execution_order:
            deps = self._planner.DEPENDENCIES.get(agent_key, [])
            if not deps or all(d in context for d in deps):
                independent_agents.append(agent_key)
            else:
                dependent_agents.append(agent_key)
        
        results = {}
        available_context = context.copy()
        
        if independent_agents:
            tasks = []
            for key in independent_agents:
                agent_info = self.AGENT_INFO_MAP.get(key)
                if agent_info:
                    agent_name, display_name = agent_info
                    stage_cache_key = build_cache_key("stage", prd_content, key, namespace="bsc:async") if cache else None
                    coroutine = self._execute_stage_async(key, display_name, chunks, available_context, stage_cache_key, cache)
                    task = asyncio.create_task(coroutine)
                    tasks.append((key, task))

            done, _ = await asyncio.wait([t[1] for t in tasks])
            
            for key, task in tasks:
                try:
                    stage_result = task.result()
                    results[key] = stage_result
                    available_context[key] = stage_result["result"]
                except Exception as e:
                    logger.error(f"  ✗ {self.AGENT_INFO_MAP.get(key, ('', ''))[1]} failed: {e}")
                    results[key] = {
                        "result": {},
                        "stage": {
                            "agent": key,
                            "display": self.AGENT_INFO_MAP.get(key, ('', ''))[1],
                            "status": "failed",
                            "duration_ms": 0,
                            "error": str(e),
                        },
                    }
        
        for agent_key in dependent_agents:
            agent_info = self.AGENT_INFO_MAP.get(agent_key)
            if agent_info:
                agent_name, display_name = agent_info
                stage_cache_key = build_cache_key("stage", prd_content, agent_key, namespace="bsc:async") if cache else None
                stage_result = await self._execute_stage_async(agent_key, display_name, chunks, available_context, stage_cache_key, cache)
                results[agent_key] = stage_result
                available_context[agent_key] = stage_result["result"]

        return results

    async def _execute_stage_async(self, agent_key: str, display_name: str, 
                                    chunks: List[Dict[str, str]], context: Dict[str, Any],
                                    cache_key: str = None, cache=None) -> Dict[str, Any]:
        """异步执行单个Agent"""
        if _CACHE_ENABLED and cache and cache_key and cache.exists(cache_key):
            cached_result = cache.get(cache_key)
            logger.info(f"  ✓ {display_name} from cache")
            return cached_result

        t0 = time.perf_counter()
        try:
            from app.agents.unified_agent import AgentContext
            from app.agents.unified_agent import AgentExecutionContext
            
            exec_context = AgentExecutionContext(llm_service=self._llm_service)
            
            agent_ctx = AgentContext(
                chunks=chunks,
                business_system=context.get("business_understanding", {}),
                previous_output=context,
            )
            
            result = exec_context.run_agent(agent_key, agent_ctx)
            
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"  ✓ {display_name} completed in {duration_ms}ms")
            
            stage_result = {
                "result": result.data,
                "stage": {
                    "agent": result.agent_name or agent_key,
                    "key": agent_key,
                    "display": display_name,
                    "status": "success" if result.status == "completed" else "failed",
                    "duration_ms": result.elapsed_ms,
                    "error": result.error,
                },
            }
            
            if _CACHE_ENABLED and cache and cache_key:
                cache.set(cache_key, stage_result, ttl=3600)
            
            return stage_result
        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"  ✗ {display_name} failed: {e}")
            return {
                "result": {},
                "stage": {
                    "agent": agent_key,
                    "display": display_name,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
            }

    async def _execute_composer(self, agent_results: Dict[str, Any], 
                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """异步执行Business Composer组装结果"""
        t0 = time.perf_counter()
        try:
            from app.agents.unified_agent import AgentExecutionContext
            
            exec_context = AgentExecutionContext(llm_service=self._llm_service)
            composer = exec_context.agents["composer"]
            
            if hasattr(composer, '_agent') and hasattr(composer._agent, 'compose'):
                composed = composer._agent.compose(agent_results)
            elif hasattr(composer, 'compose'):
                composed = composer.compose(agent_results)
            else:
                from app.agents.unified_agent import AgentContext
                agent_ctx = AgentContext(business_system=agent_results)
                result = composer.run(agent_ctx)
                composed = result.data

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"  ✓ Business Composer completed in {duration_ms}ms")

            return {
                "result": composed,
                "stage": {
                    "agent": "Business Composer",
                    "key": "composer",
                    "display": "结果组装",
                    "status": "success",
                    "duration_ms": duration_ms,
                },
            }
        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"  ✗ Business Composer failed: {e}")
            return {
                "result": {},
                "stage": {
                    "agent": "Business Composer",
                    "key": "composer",
                    "display": "结果组装",
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
            }

    def _collect_stage_result(self, results: Dict[str, Any], stage_result: Dict[str, Any],
                              key: str) -> Dict[str, Any]:
        """收集单个阶段的执行结果"""
        results[key] = stage_result["result"]
        results["stages"].append(stage_result["stage"])
        return results

    def _collect_parallel_results(self, results: Dict[str, Any], 
                                   parallel_results: Dict[str, Dict[str, Any]],
                                   flow_context: Dict[str, Any]) -> Dict[str, Any]:
        """收集并行执行的结果"""
        for agent_key, result in parallel_results.items():
            results[agent_key] = result["result"]
            results["stages"].append(result["stage"])
            flow_context[agent_key] = result["result"]
        return results

    def _prepare_failed_result(self, results: Dict[str, Any], start_time: float,
                               error_msg: str) -> Dict[str, Any]:
        """准备失败结果"""
        results["total_ms"] = int((time.perf_counter() - start_time) * 1000)
        results["summary"] = f"流程执行失败：{error_msg}"
        logger.warning(f"Pipeline failed: {error_msg}")
        return results

    def _prepare_workspace_result(self, results: Dict[str, Any], 
                                   composer_result: Dict[str, Any]) -> Dict[str, Any]:
        """准备Workspace结果"""
        results["workspace"] = self._prepare_workspace(results)
        results["summary"] = composer_result["result"].get("report", {}).get("executive_summary", "流程执行完成")
        return results

    def _prepare_workspace(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """准备Workspace数据"""
        composed = results.get("composed", {})
        bs = results.get("business_understanding", {})
        sop = results.get("sop", {})
        risk = results.get("risk", {})
        strategy = results.get("strategy", {})
        optimization = results.get("optimization", {})

        all_risks = flatten_risks(risk)

        return {
            "dashboard": {
                "business_domain": bs.get("business_domain", ""),
                "objectives_count": len(bs.get("core_objectives", [])),
                "workflow_steps": len(sop.get("workflow", [])),
                "risk_count": len(all_risks),
                "strategy_count": len(strategy.get("growth_opportunities", [])),
                "recommendation_count": len(optimization.get("recommendations", [])),
            },
            "report": {
                "title": composed.get("report", {}).get("title", "业务分析报告"),
                "summary": composed.get("summary", ""),
                "sections": composed.get("report", {}).get("sections", []),
            },
            "ppt_blueprint": {
                "slide_count": self._calculate_slide_count(results),
                "slides": self._generate_ppt_slides(results),
            },
        }

    def _calculate_slide_count(self, results: Dict[str, Any]) -> int:
        """计算PPT页数"""
        count = 3
        count += len(results.get("business_understanding", {}).get("core_objectives", []))
        count += len(results.get("sop", {}).get("workflow", [])) // 2
        count += len(results.get("risk", {}).get("process_risks", [])) // 3 + 1
        count += len(results.get("strategy", {}).get("growth_opportunities", []))
        count += len(results.get("optimization", {}).get("recommendations", []))
        return count

    def _generate_ppt_slides(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成PPT幻灯片结构"""
        slides = []
        bs = results.get("business_understanding", {})

        slides.append({"type": "cover", "title": bs.get("business_domain", "") + "业务分析报告"})
        slides.append({"type": "table_of_contents", "items": ["业务目标", "流程设计", "风险分析", "战略机会", "优化建议"]})

        for obj in bs.get("core_objectives", []):
            slides.append({"type": "objective", "title": obj.get("objective", ""), "content": obj.get("target", "")})

        for step in results.get("sop", {}).get("workflow", []):
            slides.append({"type": "workflow", "step": step.get("step", 0), "title": step.get("name", ""), "action": step.get("action", "")})

        slides.append({"type": "summary", "title": "总结", "content": results.get("summary", "")})

        return slides


async def run_async_bsc_pipeline(prd_content: str, context: Dict[str, Any] = None, 
                                   llm_service=None) -> Dict[str, Any]:
    """
    便捷函数：异步执行完整BSC流程
    
    Args:
        prd_content: PRD文本内容
        context: 初始上下文
        llm_service: LLM服务实例（可选，用于依赖注入）
    
    Returns:
        dict: 执行结果
    """
    pipeline = AsyncBSCPipeline(llm_service=llm_service)
    return await pipeline.execute(prd_content, context)


async def compile_to_business_system_async(prd_content: str, llm_service=None,
                                            template_id: Optional[str] = None,
                                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    异步编译PRD到Business System Schema
    
    Args:
        prd_content: PRD文本内容
        llm_service: LLM服务实例（可选，用于依赖注入）
        template_id: 模板ID（可选，用于应用行业模板配置）
    
    Returns:
        dict: 包含business_system和pipeline信息
    """
    template_info = None
    if template_id:
        try:
            from app.templates.template_manager import get_template_manager
            tm = get_template_manager()
            template_info = tm.get_template(template_id)
        except Exception as e:
            logger.warning(f"Failed to load template {template_id}: {e}")

    result = await run_async_bsc_pipeline(
        prd_content,
        context=context,
        llm_service=llm_service,
    )

    bs = result.get("business_understanding", {})
    sop = result.get("sop", {})
    risk = result.get("risk", {})
    strategy = result.get("strategy", {})
    optimization = result.get("optimization", {})
    composed = result.get("composed", {})

    all_risks = flatten_risks(risk)

    business_system = {
        "business_domain": bs.get("business_domain", ""),
        "objectives": bs.get("core_objectives", []),
        "roles": sop.get("roles", []),
        "workflow": sop.get("workflow", []),
        "responsibilities": sop.get("responsibilities", []),
        "sla": sop.get("sla", []),
        "metrics": sop.get("kpi", []),
        "kpi": sop.get("kpi", []),
        "risks": all_risks,
        "risk": {"process_risks": risk.get("process_risks", []), 
                 "organization_risks": risk.get("organization_risks", []),
                 "system_risks": risk.get("system_risks", []),
                 "compliance_risks": risk.get("compliance_risks", [])},
        "strategy": strategy,
        "optimization": optimization,
        "composed": composed,
        "report": composed.get("report", {}),
    }

    if template_info:
        business_system["template"] = {
            "id": template_info.get("id"),
            "name": template_info.get("name"),
            "industry": template_info.get("industry"),
            "config": template_info.get("config", {}),
        }

    # Pydantic 校验（降级不阻塞）
    from app.schemas.production_schema import validate_business_system
    _, validation_warnings = validate_business_system(business_system)

    return {
        "business_system": business_system,
        "pipeline": {
            "stages": result.get("stages", []),
            "total_ms": result.get("total_ms", 0),
            "parallel": result.get("parallel", False),
        },
        "summary": result.get("summary", ""),
        "workspace": result.get("workspace", {}),
        "template": template_info,
    }
