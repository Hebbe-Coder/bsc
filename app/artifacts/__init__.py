"""Phase 0 - Artifact Graph v2: Business World Model for the Business Agent OS.

ADR-010 principle #1: Artifact Graph is the sole business state.

Usage:
    from app.artifacts import (
        ArtifactGraphStore,
        BusinessModelArtifact,
        AssumptionArtifact,
        RiskArtifact,
        GapCategory,
        Severity,
    )
"""

from .types import (
    ArtifactType,
    ArtifactStatus,
    ARTIFACT_CLASS_MAP,
    AssumptionArtifact,
    BaseArtifact,
    BusinessModelArtifact,
    ConstraintArtifact,
    CoverageArtifact,
    DecisionArtifact,
    DeliverableArtifact,
    EvidenceArtifact,
    GapArtifact,
    GapCategory,
    RiskArtifact,
    RiskDimension,
    Severity,
)

from .store import ArtifactGraphStore

__all__ = [
    # Store
    "ArtifactGraphStore",
    # Artifact types
    "BaseArtifact",
    "BusinessModelArtifact",
    "AssumptionArtifact",
    "RiskArtifact",
    "ConstraintArtifact",
    "EvidenceArtifact",
    "CoverageArtifact",
    "GapArtifact",
    "DecisionArtifact",
    "DeliverableArtifact",
    # Enums
    "ArtifactType",
    "ArtifactStatus",
    "GapCategory",
    "RiskDimension",
    "Severity",
    # Registry
    "ARTIFACT_CLASS_MAP",
]
