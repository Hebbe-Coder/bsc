"""Phase 1-4 + P1 — Complete Business Agent OS capability layer.

ADR-010 frozen architecture:
  Nanobot (Agent Kernel) → Business Agent Framework
    ├── CapabilityExecutor   (Nanobot/Local dual backend)
    ├── BusinessRuntime      (3-loop engine)
    ├── CapabilitySystem     (registry + 12 capabilities)
    ├── MissionPlanner       (LLM → MissionGraph)
    └── ReflectionPipeline   (LLM + rule-based, 3-stage)
"""

from .registry import Capability, CapabilityRegistry, build_default_registry
from .planner import (
    MissionGraph, MissionGoal, MissionStep,
    MissionPlanner, build_planner,
)
from .runtime import (
    BusinessRuntime, RuntimeResult, RuntimeState, RuntimePhase,
)
from .reflection import (
    ReflectionEngine, GapAnalyzer, GapResolver,
    ReflectionPipeline, LLMReflectionEngine, LLMReflectionPipeline,
)
from .memory import CapabilityMemory, IndustryMemory, RunMemory, BusinessMemory
from .board import MultiAgentBoard, BoardDecision, BoardRole, RoleOpinion, BOARD_ROLES
from .executor import (
    CapabilityExecutor, ExecutionResult,
    NanobotAgentBackend, LocalAgentBackend,
)

__all__ = [
    # Registry
    "Capability", "CapabilityRegistry", "build_default_registry",
    # Planner
    "MissionGraph", "MissionGoal", "MissionStep",
    "MissionPlanner", "build_planner",
    # Runtime
    "BusinessRuntime", "RuntimeResult", "RuntimeState", "RuntimePhase",
    # Reflection
    "ReflectionEngine", "GapAnalyzer", "GapResolver",
    "ReflectionPipeline", "LLMReflectionEngine", "LLMReflectionPipeline",
    # Executor
    "CapabilityExecutor", "ExecutionResult",
    "NanobotAgentBackend", "LocalAgentBackend",
    "CapabilityMemory", "IndustryMemory", "RunMemory", "BusinessMemory",
    "MultiAgentBoard", "BoardDecision", "BoardRole", "RoleOpinion", "BOARD_ROLES",
]
