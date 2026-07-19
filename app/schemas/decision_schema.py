"""Decision Center Schema — Unified dashboard data model for executive decision-making.

The Decision Center aggregates:
  - Real-time KPIs from KPI Computation Engine
  - Risk alerts from Risk Visualization Engine
  - Bottleneck analysis from Business Graph Engine
  - Strategy simulation params from Sandbox Engine
  - Knowledge insights from Knowledge Center
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum
import uuid
import time

# ── KPI Components ──

class KpiStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

class KpiCard(BaseModel):
    """A single KPI card for the dashboard."""
    card_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    formula: str = ""
    branch: str = "Efficiency"  # Efficiency | Quality | Capacity | Cost | Risk
    current_value: float = 0.0
    target_value: float = 0.0
    previous_value: float = 0.0
    unit: str = ""
    status: KpiStatus = KpiStatus.PASS
    trend: Literal["up", "down", "flat"] = "flat"
    trend_pct: float = 0.0
    direction: Literal["higher_better", "lower_better"] = "higher_better"
    linked_nodes: list[str] = Field(default_factory=list)
    alert_threshold: float = 0.0

class HealthScore(BaseModel):
    """Aggregated business health score (0-100)."""
    overall: float = 75.0
    efficiency: float = 70.0
    quality: float = 80.0
    capacity: float = 65.0
    cost: float = 70.0
    risk: float = 60.0
    trend: Literal["improving", "stable", "declining"] = "stable"

# ── Risk Components ──

class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class RiskAlert(BaseModel):
    """A single risk alert card."""
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    level: RiskLevel = RiskLevel.MEDIUM
    color: str = "#EAB308"
    impact_score: float = 0.0
    probability: str = "medium"
    affected_nodes: list[str] = Field(default_factory=list)
    affected_kpis: list[str] = Field(default_factory=list)
    mitigation: str = ""
    triggered: bool = False
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class RiskHeatmap(BaseModel):
    """Heatmap data for the risk matrix."""
    cells: list[dict] = Field(default_factory=list)  # [{x, y, count, color}]
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

# ── Bottleneck Components ──

class BottleneckItem(BaseModel):
    """A detected bottleneck in the workflow."""
    node_id: str
    label: str
    node_type: str = "process"
    in_degree: int = 0
    out_degree: int = 0
    congestion_score: float = 0.0
    affected_paths: int = 0
    recommendation: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM

# ── Simulation Components ──

class SimulationParam(BaseModel):
    """A single adjustable simulation parameter."""
    param_id: str
    name: str
    description: str = ""
    current_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 100.0
    step: float = 1.0
    unit: str = ""
    category: str = "staffing"  # staffing | automation | review | sla | threshold

class SimulationResult(BaseModel):
    """Result of a what-if simulation."""
    param_id: str
    param_name: str
    original_value: float
    new_value: float
    impacts: dict = Field(default_factory=dict)  # {"cost_change_pct": 15, "efficiency_change_pct": -5, ...}
    kpi_impacts: list[dict] = Field(default_factory=list)  # [{kpi_name, before, after, change_pct}]
    risk_impacts: list[dict] = Field(default_factory=list)  # [{risk_name, before_level, after_level}]
    recommendation: str = ""

class SimulationPreset(BaseModel):
    """A saved simulation scenario."""
    preset_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    params: dict = Field(default_factory=dict)  # {param_id: value}

# ── Layout Components ──

class DashboardZone(str, Enum):
    TOP = "top"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    BOTTOM = "bottom"

class DashboardPanel(BaseModel):
    """A single dashboard panel specification."""
    panel_id: str
    zone: DashboardZone
    title: str
    component: str  # kpi_cards | risk_matrix | workflow_graph | bottleneck_list | sim_controls | health_score
    width_ratio: float = 1.0
    min_width: str = "280px"
    data_bindings: list[str] = Field(default_factory=list)
    visible: bool = True

class DashboardLayout(BaseModel):
    """Complete dashboard layout specification."""
    layout_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Decision Center"
    panels: list[DashboardPanel] = Field(default_factory=list)
    theme: dict = Field(default_factory=dict)
    responsive: dict = Field(default_factory=dict)

# ── Unified Decision Dashboard ──

class DecisionDashboard(BaseModel):
    """The complete Decision Center dashboard data model."""
    dashboard_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    project_name: str = ""
    domain: str = "general"
    generated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    # Health
    health_score: HealthScore = Field(default_factory=HealthScore)

    # KPIs
    kpi_cards: list[KpiCard] = Field(default_factory=list)

    # Risks
    risk_alerts: list[RiskAlert] = Field(default_factory=list)
    risk_heatmap: RiskHeatmap = Field(default_factory=RiskHeatmap)

    # Bottlenecks
    bottlenecks: list[BottleneckItem] = Field(default_factory=list)

    # Simulation
    sim_params: list[SimulationParam] = Field(default_factory=list)
    sim_presets: list[SimulationPreset] = Field(default_factory=list)
    sim_results: list[SimulationResult] = Field(default_factory=list)

    # Graph data (for workflow visualization)
    workflow_graph: dict = Field(default_factory=dict)  # Cytoscape-compatible
    centrality_top: list[dict] = Field(default_factory=list)

    # Layout
    layout: DashboardLayout = Field(default_factory=DashboardLayout)

    # Summary
    executive_summary: str = ""
    top_recommendations: list[str] = Field(default_factory=list)

    def health_status(self) -> str:
        s = self.health_score.overall
        if s >= 80: return "healthy"
        if s >= 60: return "warning"
        return "critical"
