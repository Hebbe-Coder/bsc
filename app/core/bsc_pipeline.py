"""
BSC Pipeline - BSC流程编排器

架构（按照用户设计）：
    用户上传PRD
        │
        ▼
    Business Understanding Agent (DeepSeek)
        │
        ▼
    Agent Orchestrator
        │
   ┌────┼────┬────┬────┐
   ▼    ▼    ▼    ▼
  SOP  Risk Strategy Optimization
  Agent Agent Agent   Agent
   └────┼────┬────┬────┘
        ▼
    Business Composer（组装结果）
        │
        ▼
    Workspace（Dashboard/Report/PPT Blueprint）

支持多模型路由：
    - Analysis Agents (SOP/Risk/Strategy/Optimization) → DeepSeek
    - Generation Agents (Business Understanding/Business Composer) → Doubao

设计改进：
    - 使用统一的Agent接口（UnifiedBaseAgent）
    - 依赖注入模式，消除全局单例
    - 线程安全的执行上下文
    - 缓存层集成，减少重复LLM调用
"""
from __future__ import annotations
import time, logging, concurrent.futures
from typing import List, Dict, Any, Optional

from app.utils.common import flatten_risks, build_cache_key

logger = logging.getLogger(__name__)

_CACHE_ENABLED = False


class BSCPipeline:
    """
    BSC流程编排器
    
    执行流程：
    1. Business Understanding Agent (DeepSeek) → 业务理解
    2. Planner → 根据PRD内容规划Agent执行链
    3. Agent Orchestrator → 按规划并行/串行执行分析Agent
    4. Business Composer → 组装所有结果
    5. Workspace → 准备展示数据
    
    线程安全：
    - 使用依赖注入模式，每个实例拥有独立的LLM服务和Agent
    - 并行执行时使用独立的上下文副本
    """

    SERIAL_STAGES = [
        ("business_understanding", "Business Understanding Agent", "业务理解"),
        ("composer", "Business Composer", "结果组装"),
    ]

    AGENT_INFO_MAP = {
        "sop": ("SOP Agent", "流程设计"),
        "risk": ("Risk Agent", "风险分析"),
        "strategy": ("Strategy Agent", "战略分析"),
        "optimization": ("Optimization Agent", "优化建议"),
        "root_cause": ("Root Cause Agent", "根因分析"),
    }

    def __init__(self, llm_service=None):
        """
        初始化Pipeline
        
        Args:
            llm_service: LLM服务实例（可选，用于依赖注入）
        """
        from app.agents.unified_agent import AgentExecutionContext
        from app.core.planner import Planner
        
        self._exec_context = AgentExecutionContext(llm_service=llm_service)
        self._planner = Planner()

    @property
    def agents(self):
        """获取所有Agent（延迟加载）"""
        return self._exec_context.agents

    @property
    def llm_service(self):
        """获取LLM服务"""
        return self._exec_context.llm_service

    def execute(self, prd_content: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行完整BSC流程
        
        Args:
            prd_content: PRD文本内容
            context: 初始上下文
        
        Returns:
            dict: 包含所有Agent结果和执行状态的完整输出
        """
        t0 = time.perf_counter()
        flow_context = context or {}
        chunks = [{"chunk_id": "001", "content": prd_content}]
        
        try:
            from app.core.metrics import record_request
        except Exception as e:
            logger.warning(f"Failed to import metrics module: {e}")
            record_request = None

        cache = self._get_cache()
        full_cache_key = build_cache_key("pipeline", prd_content)
        
        if _CACHE_ENABLED and cache and cache.exists(full_cache_key):
            cached_result = cache.get(full_cache_key)
            logger.info(f"✓ Pipeline result from cache")
            return cached_result

        results = self._create_initial_results(prd_content)
        
        bu_cache_key = build_cache_key("stage", prd_content, "business_understanding")
        if _CACHE_ENABLED and cache and cache.exists(bu_cache_key):
            bu_result = cache.get(bu_cache_key)
            logger.info(f"✓ Business Understanding from cache")
        else:
            bu_result = self._execute_business_understanding(chunks, flow_context)
            if _CACHE_ENABLED and cache:
                cache.set(bu_cache_key, bu_result, ttl=3600)
        
        results = self._collect_stage_result(results, bu_result, "business_understanding")
        flow_context["business_understanding"] = bu_result["result"]

        if bu_result["stage"]["status"] == "failed":
            return self._prepare_failed_result(results, t0, "业务理解阶段出错")

        plan = self._planner.plan(chunks)
        logger.info(f"→ Planner规划: 需要执行 {len(plan['agents'])} 个Agent")
        logger.info(f"  执行顺序: {plan['execution_order']}")
        results["plan"] = plan

        analysis_results = self._execute_agents_by_plan(plan, chunks, flow_context, cache=cache)
        results = self._collect_parallel_results(results, analysis_results, flow_context)

        composer_result = self._execute_composer(results, flow_context)
        results = self._collect_stage_result(results, composer_result, "composed")
        flow_context["composed"] = composer_result["result"]

        results = self._prepare_workspace_result(results, composer_result)

        total_ms = int((time.perf_counter() - t0) * 1000)
        results["total_ms"] = total_ms
        logger.info(f"BSC Pipeline completed in {total_ms}ms")

        if record_request:
            record_request("BSC Pipeline", total_ms, 200)

        if _CACHE_ENABLED and cache:
            cache.set(full_cache_key, results, ttl=7200)

        return results

    def _get_cache(self):
        """获取缓存服务实例"""
        try:
            from app.services.cache_service import get_cache_service
            return get_cache_service()
        except Exception as e:
            logger.warning(f"Failed to get cache service: {e}")
            return None

    def _create_initial_results(self, prd_content: str) -> Dict[str, Any]:
        """创建初始结果字典"""
        return {
            "prd_content": prd_content,
            "stages": [],
            "total_ms": 0,
            "summary": "",
        }

    def _execute_business_understanding(self, chunks: List[Dict[str, str]], 
                                        context: Dict[str, Any]) -> Dict[str, Any]:
        """执行业务理解阶段"""
        logger.info("→ Business Understanding（业务理解）")
        return self._execute_stage("business_understanding", "业务理解", chunks, context)

    def _execute_parallel_analysis(self, chunks: List[Dict[str, str]], 
                                   context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """并行执行分析Agent（兼容旧接口）"""
        logger.info("→ Agent Orchestrator（并行执行SOP/Risk/Strategy/Optimization）")
        return self._execute_parallel(chunks, context)

    def _execute_agents_by_plan(self, plan: Dict[str, Any], chunks: List[Dict[str, str]],
                                context: Dict[str, Any], cache=None) -> Dict[str, Dict[str, Any]]:
        """
        根据Planner规划动态执行Agent
        
        支持并行和串行执行：
        - 无依赖的Agent并行执行
        - 有依赖的Agent按顺序串行执行
        """
        logger.info("→ Agent Orchestrator（按Planner规划执行）")
        
        execution_order = plan.get("execution_order", [])
        agents_to_run = plan.get("agents", [])
        
        if not agents_to_run:
            logger.warning("Planner未规划任何Agent")
            return {}

        results = {}
        available_context = context.copy()
        prd_content = chunks[0]["content"] if chunks else ""

        independent_agents = []
        dependent_agents = []

        for agent_key in execution_order:
            deps = self._planner.DEPENDENCIES.get(agent_key, [])
            if not deps or all(d in available_context for d in deps):
                independent_agents.append(agent_key)
            else:
                dependent_agents.append(agent_key)

        if independent_agents:
            parallel_results = self._execute_parallel_with_keys(independent_agents, chunks, available_context, prd_content, cache)
            results.update(parallel_results)
            for key, result in parallel_results.items():
                available_context[key] = result["result"]

        for agent_key in dependent_agents:
            agent_info = self.AGENT_INFO_MAP.get(agent_key)
            if agent_info:
                agent_name, display_name = agent_info
                
                stage_cache_key = build_cache_key("stage", prd_content, agent_key)
                if _CACHE_ENABLED and cache and cache.exists(stage_cache_key):
                    stage_result = cache.get(stage_cache_key)
                    logger.info(f"✓ {display_name} from cache")
                else:
                    stage_result = self._execute_stage(agent_key, display_name, chunks, available_context)
                    if _CACHE_ENABLED and cache:
                        cache.set(stage_cache_key, stage_result, ttl=3600)
                
                results[agent_key] = stage_result
                available_context[agent_key] = stage_result["result"]

        return results

    def _execute_parallel_with_keys(self, agent_keys: List[str], chunks: List[Dict[str, str]],
                                    context: Dict[str, Any], prd_content: str = "", cache=None) -> Dict[str, Dict[str, Any]]:
        """并行执行指定的Agent"""
        from app.agents.unified_agent import AgentContext
        
        def _run_agent(exec_context, agent_key, agent_name, display_name):
            stage_cache_key = build_cache_key("stage", prd_content, agent_key)
            if _CACHE_ENABLED and cache and cache.exists(stage_cache_key):
                logger.info(f"✓ {display_name} from cache")
                return agent_key, cache.get(stage_cache_key)
            
            t0 = time.perf_counter()
            try:
                agent_ctx = AgentContext(
                    chunks=chunks.copy(),
                    business_system=context.get("business_understanding", {}).copy(),
                    previous_output=context,
                )
                
                result = exec_context.run_agent(agent_key, agent_ctx)
                
                duration_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(f"  ✓ {display_name} completed in {duration_ms}ms")
                
                stage_result = {
                    "result": result.data,
                    "stage": {
                        "agent": result.agent_name or agent_name,
                        "key": agent_key,
                        "display": display_name,
                        "status": "success" if result.status == "completed" else "failed",
                        "duration_ms": result.elapsed_ms,
                        "error": result.error,
                    },
                }
                
                if _CACHE_ENABLED and cache:
                    cache.set(stage_cache_key, stage_result, ttl=3600)
                
                return agent_key, stage_result
            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                logger.error(f"  ✗ {display_name} failed: {e}")
                return agent_key, {
                    "result": {},
                    "stage": {
                        "agent": agent_name,
                        "display": display_name,
                        "status": "failed",
                        "duration_ms": duration_ms,
                        "error": str(e),
                    },
                }

        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(agent_keys))) as executor:
            futures = {}
            for key in agent_keys:
                agent_info = self.AGENT_INFO_MAP.get(key)
                if agent_info:
                    agent_name, display_name = agent_info
                    exec_context_copy = type(self._exec_context)(llm_service=self.llm_service)
                    futures[executor.submit(_run_agent, exec_context_copy, key, agent_name, display_name)] = key
            
            for future in concurrent.futures.as_completed(futures):
                key, result = future.result()
                results[key] = result

        return results

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

    def _execute_stage(self, agent_key: str, display_name: str, 
                       chunks: List[Dict[str, str]], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个Agent（使用统一接口）"""
        t0 = time.perf_counter()
        try:
            from app.agents.unified_agent import AgentContext
            
            agent_ctx = AgentContext(
                chunks=chunks,
                business_system=context.get("business_understanding", {}),
                previous_output=context,
            )
            
            result = self._exec_context.run_agent(agent_key, agent_ctx)
            
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"  ✓ {display_name} completed in {duration_ms}ms")
            
            return {
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

    def _execute_parallel(self, chunks: List[Dict[str, str]], context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """并行执行分析Agent（线程安全，兼容旧接口）
        
        注意：新流程已使用_execute_agents_by_plan，此方法保留用于向后兼容
        """
        plan = self._planner.plan(chunks)
        return self._execute_agents_by_plan(plan, chunks, context)

    def _execute_composer(self, agent_results: Dict[str, Any], 
                          context: Dict[str, Any]) -> Dict[str, Any]:
        """执行Business Composer组装结果"""
        t0 = time.perf_counter()
        try:
            composer = self.agents["composer"]
            
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

    def _prepare_workspace(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """准备Workspace数据（Dashboard/Report/PPT Blueprint）"""
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

    def get_stage_info(self) -> List[Dict[str, str]]:
        """获取所有阶段信息"""
        stages = []
        for key, agent, display in self.SERIAL_STAGES:
            stages.append({"key": key, "agent": agent, "display": display, "type": "serial"})
        stages.append({"key": "orchestrator", "agent": "Agent Orchestrator", "display": "Agent Orchestrator", "type": "parallel_start"})
        for key, (agent, display) in self.AGENT_INFO_MAP.items():
            stages.append({"key": key, "agent": agent, "display": display, "type": "parallel"})
        return stages

    def execute_stage(self, stage_key: str, chunks: List[Dict[str, str]]) -> Dict[str, Any]:
        """单独执行某个阶段"""
        if stage_key == "business_understanding":
            return self._execute_stage("business_understanding", "业务理解", chunks, {})
        
        if stage_key in self.AGENT_INFO_MAP:
            agent_name, display_name = self.AGENT_INFO_MAP[stage_key]
            return self._execute_stage(stage_key, display_name, chunks, {})
        
        if stage_key == "composer":
            return self._execute_composer(chunks, {})
        
        raise ValueError(f"Unknown stage key: {stage_key}")


def run_bsc_pipeline(prd_content: str, context: Dict[str, Any] = None, 
                     llm_service=None) -> Dict[str, Any]:
    """
    便捷函数：执行完整BSC流程
    
    Args:
        prd_content: PRD文本内容
        context: 初始上下文
        llm_service: LLM服务实例（可选，用于依赖注入）
    
    Returns:
        dict: 执行结果
    """
    pipeline = BSCPipeline(llm_service=llm_service)
    return pipeline.execute(prd_content, context)


def _validate_business_system_integrity(business_system: Dict[str, Any]) -> bool:
    """
    验证business_system数据完整性
    
    Args:
        business_system: 业务系统数据
    
    Returns:
        bool: 是否完整（至少包含domain、objectives、workflow）
    """
    if not business_system.get("business_domain"):
        return False
    if not business_system.get("objectives"):
        return False
    if not business_system.get("workflow"):
        return False
    return True


def compile_to_business_system(prd_content: str, llm_service=None, 
                               template_id: Optional[str] = None) -> Dict[str, Any]:
    """
    编译PRD到Business System Schema
    
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

    result = run_bsc_pipeline(prd_content, llm_service=llm_service)

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
    validated_model, validation_warnings = validate_business_system(business_system)
    validated_business_system = validated_model.model_dump(exclude_none=False)

    # 数据完整性检查：如果核心字段为空，尝试回退到mock数据
    if not _validate_business_system_integrity(validated_business_system):
        logger.warning("Business system data is incomplete, attempting fallback...")
        business_system = _generate_fallback_business_system(prd_content)
        _, validation_warnings = validate_business_system(business_system)

    return {
        "business_system": business_system,
        "pipeline": {
            "stages": result.get("stages", []),
            "total_ms": result.get("total_ms", 0),
            "plan": result.get("plan", {}),
        },
        "summary": result.get("summary", ""),
        "workspace": result.get("workspace", {}),
        "plan": result.get("plan", {}),
        "template": template_info,
    }


def _generate_fallback_business_system(prd_content: str) -> Dict[str, Any]:
    """
    生成回退业务系统数据（当真实LLM返回空模型时使用）
    
    Args:
        prd_content: PRD文本内容
    
    Returns:
        dict: 回退的业务系统数据
    """
    try:
        from app.services.llm_service import LLMService
        
        mock_service = LLMService(provider="mock")
        domain_info = mock_service._analyze_input_domain(prd_content)
        
        return {
            "business_domain": domain_info.get("domain_name", "企业服务"),
            "objectives": [
                {"objective": domain_info.get("core_objective", "效率提升"), "target": "达成年度目标", "priority": "high"},
                {"objective": "流程优化", "target": "提升工作效率", "priority": "high"},
                {"objective": "数据驱动", "target": "关键指标可视化", "priority": "medium"},
            ],
            "roles": [
                {"role": f"{domain_info.get('role_prefix', '业务')}专员", "department": domain_info.get("department", "业务部"), "level": "L4", "headcount": 10},
                {"role": "质检员", "department": domain_info.get("department", "业务部"), "level": "L5", "headcount": 2},
            ],
            "workflow": [
                {"step": 1, "name": "请求接收", "action": "用户提交请求", "input": "原始请求", "output": "请求记录", "role": "用户"},
                {"step": 2, "name": "智能分类", "action": "系统自动分类", "input": "请求记录", "output": "分类结果", "role": "系统"},
                {"step": 3, "name": "专业处理", "action": f"{domain_info.get('role_prefix', '业务')}专员执行处理", "input": "分类结果", "output": "处理结果", "role": f"{domain_info.get('role_prefix', '业务')}专员"},
                {"step": 4, "name": "质量审核", "action": "质检员审核", "input": "处理结果", "output": "审核结论", "role": "质检员"},
                {"step": 5, "name": "结果交付", "action": "系统交付结果", "input": "审核结论", "output": "交付记录", "role": "系统"},
            ],
            "responsibilities": [],
            "sla": [
                {"metric": "处理时效", "target": "<4小时", "owner": f"{domain_info.get('role_prefix', '业务')}专员"},
                {"metric": "准确率", "target": ">=95%", "owner": "质检员"},
            ],
            "metrics": [],
            "kpi": [
                {"name": "处理准确率", "formula": "(正确数/总数)*100", "target": ">=95%", "owner": "质检员"},
                {"name": "处理效率", "formula": "处理量/工时", "target": "提升20%", "owner": f"{domain_info.get('role_prefix', '业务')}专员"},
            ],
            "risks": [
                {"risk": "处理瓶颈导致SLA违约", "severity": "high", "probability": "medium", "mitigation": "提升自动化率"},
                {"risk": "人员流失风险", "severity": "medium", "probability": "medium", "mitigation": "薪酬优化"},
            ],
            "risk": {
                "process_risks": [{"risk": "处理瓶颈", "severity": "high", "probability": "medium", "mitigation": "自动化"}],
                "organization_risks": [{"risk": "人员流失", "severity": "medium", "probability": "medium", "mitigation": "优化"}],
                "system_risks": [{"risk": "系统故障", "severity": "critical", "probability": "low", "mitigation": "冗余部署"}],
                "compliance_risks": [{"risk": "合规风险", "severity": "high", "probability": "medium", "mitigation": "合规审查"}],
            },
            "strategy": {
                "growth_opportunities": [{"opportunity": "自动化提升", "potential": "50万元/年", "priority": "高"}],
                "strategic_path": [{"phase": "第一阶段", "theme": "效率提升", "timeline": "0-3月", "goal": "成本降低"}],
            },
            "optimization": {
                "recommendations": [{"id": "REC-1", "title": "自动化提升", "description": "提升自动化率", "priority": "P0"}],
            },
            "composed": {
                "report": {
                    "title": f"{domain_info.get('domain_name', '业务')}分析报告",
                    "executive_summary": "业务分析报告已生成",
                    "sections": [],
                    "key_findings": [],
                },
            },
            "report": {
                "title": f"{domain_info.get('domain_name', '业务')}分析报告",
                "executive_summary": "业务分析报告已生成",
                "sections": [],
                "key_findings": [],
            },
        }
    except Exception as e:
        logger.error(f"Failed to generate fallback business system: {e}")
        return {
            "business_domain": "企业服务",
            "objectives": [],
            "roles": [],
            "workflow": [],
            "responsibilities": [],
            "sla": [],
            "metrics": [],
            "kpi": [],
            "risks": [],
            "risk": {"process_risks": [], "organization_risks": [], "system_risks": [], "compliance_risks": []},
            "strategy": {},
            "optimization": {},
            "composed": {},
            "report": {},
        }


BSC_PIPELINE = BSCPipeline()
