"""Unified Agent Interface for BSC Studio.

This module provides a single unified interface for all agents,
supporting both LLM-based and local analysis modes.

Design goals:
1. Single interface for all agents - no more type inconsistency
2. Support both LLM-based and local analysis agents
3. Dependency injection pattern - no global singletons
4. Thread-safe execution
5. Backward compatibility
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    data: Dict[str, Any] = field(default_factory=dict)
    status: str = "completed"
    error: Optional[str] = None
    agent_name: str = ""
    elapsed_ms: int = 0


@dataclass
class AgentContext:
    project_name: str = ""
    domain: str = "general"
    business_system: Dict[str, Any] = field(default_factory=dict)
    previous_output: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = field(default_factory=dict)
    chunks: List[Dict[str, str]] = field(default_factory=list)


class UnifiedBaseAgent(ABC):
    """Unified base class for all BSC Studio agents.
    
    All agents must implement:
    - name property
    - capabilities property
    - run() method
    
    Optional:
    - description property
    - system_prompt property (for LLM-based agents)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name"""
        pass
    
    @property
    def description(self) -> str:
        """Agent description"""
        return ""
    
    @property
    def capabilities(self) -> List[str]:
        """Agent capabilities (analyze, generate, llm, local)"""
        return ["analyze"]
    
    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentResult:
        """
        Execute the agent with the given context.
        
        Args:
            ctx: AgentContext containing input data and parameters
            
        Returns:
            AgentResult with execution data and status
        """
        pass
    
    def _wrap_result(self, data: Dict[str, Any], status: str = "completed", 
                     error: Optional[str] = None) -> AgentResult:
        """Helper to wrap result in AgentResult"""
        return AgentResult(
            data=data,
            status=status,
            error=error,
            agent_name=self.name,
        )


class LLMAgentAdapter(UnifiedBaseAgent):
    """Adapter for LLM-based agents (base_agent.py style).
    
    Wraps agents that use the old base_agent.BaseAgent interface
    which calls LLM to generate results.
    """
    
    def __init__(self, llm_agent):
        self._agent = llm_agent
        self._llm_service = None
    
    @property
    def name(self) -> str:
        return self._agent.name
    
    @property
    def description(self) -> str:
        return self._agent.system_prompt[:100] if hasattr(self._agent, 'system_prompt') else ""
    
    @property
    def capabilities(self) -> List[str]:
        return ["analyze", "generate", "llm"]
    
    @property
    def system_prompt(self) -> str:
        return self._agent.system_prompt if hasattr(self._agent, 'system_prompt') else ""
    
    def run(self, ctx: AgentContext) -> AgentResult:
        """Run the LLM-based agent"""
        t0 = time.perf_counter()
        
        try:
            if self._llm_service is None:
                from app.services.llm_service import LLMService
                self._llm_service = LLMService()
            if hasattr(self._agent, "set_llm_service"):
                self._agent.set_llm_service(self._llm_service)
            
            chunks = ctx.chunks if ctx.chunks else [{"chunk_id": "001", "content": str(ctx.business_system)}]
            context = ctx.previous_output or {}
            
            result = self._agent.run(chunks, context)
            
            elapsed = int((time.perf_counter() - t0) * 1000)
            return AgentResult(
                data=result,
                status="completed",
                agent_name=self.name,
                elapsed_ms=elapsed,
            )
            
        except Exception as e:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.error(f"[{self.name}] Execution failed: {e}")
            return AgentResult(
                data={},
                status="failed",
                error=str(e),
                agent_name=self.name,
                elapsed_ms=elapsed,
            )


class LocalAgentAdapter(UnifiedBaseAgent):
    """Adapter for local analysis agents (protocol.py style).
    
    Wraps agents that use the protocol.BaseAgent interface
    which performs local analysis without LLM calls.
    """
    
    def __init__(self, local_agent):
        self._agent = local_agent
    
    @property
    def name(self) -> str:
        return self._agent.name
    
    @property
    def description(self) -> str:
        return self._agent.description
    
    @property
    def capabilities(self) -> List[str]:
        return self._agent.capabilities + ["local"]
    
    def run(self, ctx: AgentContext) -> AgentResult:
        """Run the local analysis agent"""
        t0 = time.perf_counter()
        
        try:
            result = self._agent.run(ctx)
            
            elapsed = int((time.perf_counter() - t0) * 1000)
            return AgentResult(
                data=result.data,
                status=result.status,
                error=result.error,
                agent_name=self.name,
                elapsed_ms=elapsed,
            )
            
        except Exception as e:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.error(f"[{self.name}] Execution failed: {e}")
            return AgentResult(
                data={},
                status="failed",
                error=str(e),
                agent_name=self.name,
                elapsed_ms=elapsed,
            )


class AgentFactory:
    """Factory for creating unified agents.
    
    Creates agents based on type and configuration,
    ensuring thread-safe execution by avoiding global state.
    """
    
    AGENT_REGISTRY = {
        "business_understanding": {
            "module": "app.agents.business_understanding_agent",
            "class": "BusinessUnderstandingAgent",
            "type": "llm",
        },
        "sop": {
            "module": "app.agents.base_agent",
            "class": "SOPAgent",
            "type": "llm",
        },
        "risk": {
            "module": "app.agents.base_agent",
            "class": "RiskAgent",
            "type": "llm",
        },
        "strategy": {
            "module": "app.agents.base_agent",
            "class": "StrategyAgent",
            "type": "llm",
        },
        "optimization": {
            "module": "app.agents.base_agent",
            "class": "OptimizationAgent",
            "type": "llm",
        },
        "composer": {
            "module": "app.agents.composer",
            "class": "COMPOSER",
            "type": "local",
        },
    }
    
    @classmethod
    def create_agent(cls, agent_key: str) -> UnifiedBaseAgent:
        """
        Create an agent by key.
        
        Args:
            agent_key: The key of the agent to create
            
        Returns:
            UnifiedBaseAgent instance
            
        Raises:
            ValueError: If agent key is not registered
            ImportError: If agent module cannot be loaded
        """
        config = cls.AGENT_REGISTRY.get(agent_key)
        if not config:
            raise ValueError(f"Unknown agent: {agent_key}")
        
        module = __import__(config["module"], fromlist=[config["class"]])
        agent_class_or_instance = getattr(module, config["class"])
        
        if isinstance(agent_class_or_instance, UnifiedBaseAgent):
            return agent_class_or_instance
        
        if isinstance(agent_class_or_instance, object) and not callable(agent_class_or_instance):
            if config["type"] == "llm":
                return LLMAgentAdapter(agent_class_or_instance)
            else:
                return LocalAgentAdapter(agent_class_or_instance)
        
        if callable(agent_class_or_instance):
            agent_instance = agent_class_or_instance()
        else:
            agent_instance = agent_class_or_instance
        
        if config["type"] == "llm":
            return LLMAgentAdapter(agent_instance)
        else:
            return LocalAgentAdapter(agent_instance)
    
    @classmethod
    def create_all_agents(cls) -> Dict[str, UnifiedBaseAgent]:
        """Create all registered agents."""
        agents = {}
        for key in cls.AGENT_REGISTRY:
            try:
                agents[key] = cls.create_agent(key)
            except Exception as e:
                logger.error(f"Failed to create agent {key}: {e}")
        return agents


class AgentExecutionContext:
    """Thread-safe execution context for agent pipelines.
    
    This class holds the execution state and provides methods
    for running agents in a thread-safe manner.
    """
    
    def __init__(self, llm_service=None):
        self._llm_service = llm_service
        self._agents = None
    
    @property
    def llm_service(self):
        if self._llm_service is None:
            from app.services.llm_service import LLMService
            self._llm_service = LLMService()
        return self._llm_service
    
    @property
    def agents(self):
        if self._agents is None:
            self._agents = AgentFactory.create_all_agents()
        return self._agents
    
    def run_agent(self, agent_key: str, ctx: AgentContext) -> AgentResult:
        """
        Run an agent with the given context.
        
        Args:
            agent_key: The agent to run
            ctx: AgentContext
            
        Returns:
            AgentResult
        """
        agent = self.agents.get(agent_key)
        if not agent:
            return AgentResult(
                data={},
                status="failed",
                error=f"Agent not found: {agent_key}",
                agent_name=agent_key,
            )
        
        if isinstance(agent, LLMAgentAdapter):
            agent._llm_service = self.llm_service
        
        return agent.run(ctx)
    
    def run_parallel(self, agent_keys: List[str], ctx: AgentContext) -> Dict[str, AgentResult]:
        """
        Run multiple agents in parallel.
        
        Args:
            agent_keys: List of agent keys to run
            ctx: AgentContext
            
        Returns:
            Dict mapping agent keys to AgentResult
        """
        import concurrent.futures
        
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(agent_keys))) as executor:
            futures = {}
            for key in agent_keys:
                agent_ctx = AgentContext(
                    project_name=ctx.project_name,
                    domain=ctx.domain,
                    business_system=ctx.business_system.copy(),
                    previous_output=ctx.previous_output,
                    params=ctx.params.copy(),
                    chunks=ctx.chunks.copy(),
                )
                futures[executor.submit(self.run_agent, key, agent_ctx)] = key
            
            for future in concurrent.futures.as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    results[key] = AgentResult(
                        data={},
                        status="failed",
                        error=str(e),
                        agent_name=key,
                    )
        
        return results
