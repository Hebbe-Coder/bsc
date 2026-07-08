"""Business Graph Schema - Formal Pydantic models for the enterprise knowledge graph.

Node types (6): process | role | metric | system | strategy | risk
Edge types (4): depends_on | triggers | inputs_to | outputs_to

The Business Graph is the union of:
  - Workflow graph (process nodes + flow edges)
  - Organization graph (role nodes + reporting edges)
  - Metrics graph (metric nodes + measured_by edges)
  - Risk graph (risk nodes + mitigates edges)
  - Strategy graph (strategy nodes + implemented_by edges)
  - System graph (system nodes + integration edges)
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum
import uuid, time

# ── Node Types ──

class GraphNodeType(str, Enum):
    PROCESS = "process"        # workflow step / business process
    ROLE = "role"              # human role / organization unit
    METRIC = "metric"          # KPI / measurement
    SYSTEM = "system"          # software system / tool
    STRATEGY = "strategy"      # business strategy / policy
    RISK = "risk"              # risk item / threat

# ── Edge Types ──

class GraphEdgeType(str, Enum):
    DEPENDS_ON = "depends_on"        # A requires B to function
    TRIGGERS = "triggers"            # A causes B to start
    INPUTS_TO = "inputs_to"          # A feeds data into B
    OUTPUTS_TO = "outputs_to"        # A produces output consumed by B

# ── Core Graph Entities ──

class GraphNode(BaseModel):
    """A single node in the Business Graph."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    node_type: GraphNodeType
    label: str = ""
    description: str = ""
    owner: str = ""              # role or system owner
    domain: str = "general"
    project_id: str = ""
    entity_ref: str = ""         # back-reference to knowledge entity ID
    properties: dict = Field(default_factory=dict)  # arbitrary key-value pairs
    weight: float = 1.0          # node importance (for centrality, ranking)
    status: str = "active"
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

class GraphEdge(BaseModel):
    """A directed edge connecting two nodes."""
    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    source_id: str               # from node_id
    target_id: str               # to node_id
    edge_type: GraphEdgeType
    label: str = ""
    weight: float = 1.0          # edge strength
    bidirectional: bool = False  # if True, traffic flows both ways
    properties: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

# ── Graph Container ──

class BusinessGraph(BaseModel):
    """Complete business knowledge graph."""
    graph_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    description: str = ""
    domain: str = "general"
    project_id: str = ""
    version: str = "1.0.0"
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def adjacency_list(self) -> dict[str, list[str]]:
        """Build adjacency list: node_id -> [neighbor_ids]."""
        adj: dict[str, list[str]] = {}
        for n in self.nodes:
            adj[n.node_id] = []
        for e in self.edges:
            if e.source_id not in adj:
                adj[e.source_id] = []
            adj[e.source_id].append(e.target_id)
            if e.bidirectional:
                if e.target_id not in adj:
                    adj[e.target_id] = []
                adj[e.target_id].append(e.source_id)
        return adj

    def reverse_adjacency(self) -> dict[str, list[str]]:
        """Build reverse adjacency list: node_id -> [incoming_neighbor_ids]."""
        rev: dict[str, list[str]] = {}
        for n in self.nodes:
            rev[n.node_id] = []
        for e in self.edges:
            if e.target_id not in rev:
                rev[e.target_id] = []
            rev[e.target_id].append(e.source_id)
            if e.bidirectional:
                if e.source_id not in rev:
                    rev[e.source_id] = []
                rev[e.source_id].append(e.target_id)
        return rev

    def get_node(self, node_id: str) -> GraphNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def get_edges_by_type(self, edge_type: GraphEdgeType) -> list[GraphEdge]:
        return [e for e in self.edges if e.edge_type == edge_type]

    def get_nodes_by_type(self, node_type: GraphNodeType) -> list[GraphNode]:
        return [n for n in self.nodes if n.node_type == node_type]

    def stats(self) -> dict:
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_by_type": {
                t.value: len(self.get_nodes_by_type(t))
                for t in GraphNodeType
            },
            "edges_by_type": {
                t.value: len(self.get_edges_by_type(t))
                for t in GraphEdgeType
            },
            "density": round(
                len(self.edges) / max(len(self.nodes) * (len(self.nodes) - 1), 1), 4
            ) if len(self.nodes) > 1 else 0,
        }

# ── Graph Query DSL ──

class GraphQuery(BaseModel):
    """Declarative query for the Business Graph."""
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    # Node filters
    node_types: list[GraphNodeType] = Field(default_factory=list)
    node_labels_contain: str = ""           # substring match on label
    # Edge filters
    edge_types: list[GraphEdgeType] = Field(default_factory=list)
    # Traversal
    start_node_id: str = ""                 # BFS/DFS root
    max_depth: int = 3                      # max traversal hops
    direction: Literal["outgoing", "incoming", "both"] = "both"
    # Result
    limit: int = 100

class GraphPath(BaseModel):
    """A path between two nodes."""
    path_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    nodes: list[str] = Field(default_factory=list)   # ordered node_ids
    edges: list[str] = Field(default_factory=list)   # ordered edge_ids
    total_weight: float = 0.0
    depth: int = 0

class CentralityResult(BaseModel):
    """Centrality metrics for a node."""
    node_id: str
    label: str
    node_type: GraphNodeType
    degree: int = 0                    # total connections
    in_degree: int = 0
    out_degree: int = 0
    betweenness: float = 0.0           # normalized [0-1]
    pagerank: float = 0.0              # normalized [0-1]
    eigenvector: float = 0.0           # normalized [0-1]

class BottleneckResult(BaseModel):
    """Detected bottleneck in the graph."""
    node_id: str
    label: str
    node_type: GraphNodeType
    in_degree: int
    out_degree: int
    congestion_score: float            # higher = more bottlenecked
    affected_paths: int
    recommendation: str = ""

class SubgraphResult(BaseModel):
    """Result of a subgraph extraction."""
    subgraph_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    root_node_id: str = ""
    depth: int = 0
    stats: dict = Field(default_factory=dict)

class GraphDiff(BaseModel):
    """Difference between two graph snapshots."""
    added_nodes: list[str] = Field(default_factory=list)
    removed_nodes: list[str] = Field(default_factory=list)
    added_edges: list[str] = Field(default_factory=list)
    removed_edges: list[str] = Field(default_factory=list)
    modified_nodes: list[str] = Field(default_factory=list)
