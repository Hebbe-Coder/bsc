"""Business Knowledge Center Schema - formal Pydantic models for the knowledge graph."""
from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import time

# ── Enums ──

class KnowledgeCategory(str, Enum):
    BUSINESS_OBJECTIVE = "business_objective"
    BUSINESS_PROCESS = "business_process"
    KPI_METRIC = "kpi_metric"
    ROLE_RESPONSIBILITY = "role_responsibility"
    RISK_SYSTEM = "risk_system"
    RULE_POLICY = "rule_policy"
    ORGANIZATION = "organization"
    SLA_MODEL = "sla_model"

class EntityStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

# ── Core Entities ──

class KnowledgeTag(BaseModel):
    name: str
    color: str = "#6366f1"

class KnowledgeReference(BaseModel):
    """Cross-entity citation link."""
    ref_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    source_entity_id: str
    target_entity_id: str
    relation: str  # "depends_on", "triggers", "measured_by", "owns", "mitigates"
    weight: float = 1.0
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class KnowledgeVersion(BaseModel):
    """Versioned snapshot of a knowledge entity."""
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    entity_id: str
    version_number: int = 1
    data: dict = Field(default_factory=dict)
    change_summary: str = ""
    author: str = "system"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class BusinessObjectiveEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.BUSINESS_OBJECTIVE
    title: str
    description: str
    kpis: list[str] = Field(default_factory=list)  # linked KPI IDs
    owner: str = ""
    priority: str = "medium"  # low | medium | high | critical
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class ProcessEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.BUSINESS_PROCESS
    title: str
    description: str
    steps: list[dict] = Field(default_factory=list)  # [{"step":1,"node":"submit","actor":"user","next":"review"}]
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    roles_involved: list[str] = Field(default_factory=list)  # linked Role IDs
    sla_target: str = ""
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class MetricEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.KPI_METRIC
    title: str
    description: str = ""
    formula: str = ""
    unit: str = ""
    target_value: str = ""
    threshold_warn: str = ""
    threshold_critical: str = ""
    direction: str = "higher_is_better"  # higher_is_better | lower_is_better | target_range
    branch: str = "Efficiency"  # Efficiency | Quality | Capacity | Cost | Risk
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class RoleEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.ROLE_RESPONSIBILITY
    title: str
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    reports_to: str = ""
    process_ids: list[str] = Field(default_factory=list)  # linked Process IDs
    kpi_ids: list[str] = Field(default_factory=list)  # linked KPI IDs
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class RiskEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.RISK_SYSTEM
    title: str
    description: str = ""
    probability: str = "medium"  # low | medium | high
    impact: str = "medium"
    severity_score: int = 1  # 1-9
    affected_processes: list[str] = Field(default_factory=list)
    affected_kpis: list[str] = Field(default_factory=list)
    mitigation_actions: list[dict] = Field(default_factory=list)  # [{"action":"...","owner":"...","status":"planned"}]
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class RuleEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.RULE_POLICY
    title: str
    description: str = ""
    condition: str = ""
    action: str = ""
    priority: int = 0
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class OrganizationEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.ORGANIZATION
    title: str
    description: str = ""
    roles: list[str] = Field(default_factory=list)
    reporting_chain: list[dict] = Field(default_factory=list)  # [{"from":"role_a","to":"role_b"}]
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class SLAEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    category: KnowledgeCategory = KnowledgeCategory.SLA_MODEL
    title: str
    description: str = ""
    normal_sla: str = ""
    warning_sla: str = ""
    escalation_sla: str = ""
    applies_to_processes: list[str] = Field(default_factory=list)
    status: EntityStatus = EntityStatus.ACTIVE
    tags: list[KnowledgeTag] = Field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

# ── Unified Knowledge Graph ──

class KnowledgeGraphSnapshot(BaseModel):
    """Complete snapshot of all knowledge entities + references."""
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    project_id: str = ""
    domain: str = "general"
    version: str = "1.0.0"
    objectives: list[BusinessObjectiveEntity] = Field(default_factory=list)
    processes: list[ProcessEntity] = Field(default_factory=list)
    metrics: list[MetricEntity] = Field(default_factory=list)
    roles: list[RoleEntity] = Field(default_factory=list)
    risks: list[RiskEntity] = Field(default_factory=list)
    rules: list[RuleEntity] = Field(default_factory=list)
    organizations: list[OrganizationEntity] = Field(default_factory=list)
    slas: list[SLAEntity] = Field(default_factory=list)
    references: list[KnowledgeReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

# ── Search / Query Models ──

class KnowledgeSearchRequest(BaseModel):
    query: str
    categories: list[KnowledgeCategory] = Field(default_factory=list)
    domain: str = ""
    project_id: str = ""
    status: EntityStatus | str = "active"
    top_k: int = 20
    min_score: float = 0.0

class KnowledgeSearchResult(BaseModel):
    entity_id: str
    category: KnowledgeCategory
    title: str
    description: str
    score: float
    highlights: list[str] = Field(default_factory=list)
    entity: dict = Field(default_factory=dict)

class KnowledgeSearchResponse(BaseModel):
    success: bool = True
    query: str
    total_hits: int
    elapsed_ms: float
    results: list[KnowledgeSearchResult]
