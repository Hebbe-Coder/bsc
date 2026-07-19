"""Phase 0 - ArtifactGraphStore: Pure file I/O artifact graph storage.

Nanobot-aligned design: no database, just JSON files on disk.
Follows nanobot MemoryStore pattern (simple read/write file operations).
"""

from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path
from collections import defaultdict
from typing import Any, Optional

from .types import (
    ArtifactStatus,
    ArtifactType,
    ARTIFACT_CLASS_MAP,
    AssumptionArtifact,
    BaseArtifact,
    BusinessModelArtifact,
    ConstraintArtifact,
    CoverageArtifact,
    DecisionArtifact,
    EvidenceArtifact,
    GapArtifact,
    GapCategory,
    RiskArtifact,
    RiskDimension,
    Severity,
)

logger = logging.getLogger(__name__)


class ArtifactGraphStore:
    """Pure file I/O store for the Artifact Graph."""

    INDEX_FILE = "_index.json"

    def __init__(self, data_dir: str = "./data/artifacts"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._data_dir / self.INDEX_FILE
        self._index: dict[str, dict[str, Any]] = {}
        self._children_index: dict[str, list[str]] = defaultdict(list)
        self._load_index()

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._index = data.get("artifacts", {})
                self._children_index = defaultdict(list)
                for art_id, meta in self._index.items():
                    for pid in meta.get("parent_ids", []):
                        self._children_index[pid].append(art_id)
                logger.debug("Loaded index: %d artifacts", len(self._index))
            except Exception as exc:
                logger.error("Failed to load index: %s", exc)
                self._index = {}
                self._children_index = defaultdict(list)
        else:
            self._index = {}
            self._children_index = defaultdict(list)

    def _save_index(self) -> None:
        data = {
            "artifacts": self._index,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(self._index),
        }
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _artifact_path(self, artifact_id: str) -> Path:
        return self._data_dir / f"{artifact_id}.json"

    def add(self, artifact: BaseArtifact) -> str:
        artifact.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        path = self._artifact_path(artifact.artifact_id)
        path.write_text(
            artifact.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._index[artifact.artifact_id] = {
            "artifact_type": artifact.artifact_type.value,
            "project_id": artifact.project_id,
            "label": artifact.label,
            "parent_ids": artifact.parent_ids,
            "confidence": artifact.confidence,
            "status": artifact.status.value,
            "tags": artifact.tags,
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        }
        for pid in artifact.parent_ids:
            if artifact.artifact_id not in self._children_index[pid]:
                self._children_index[pid].append(artifact.artifact_id)
        self._save_index()
        logger.info("Artifact added: %s (%s)", artifact.artifact_id, artifact.artifact_type.value)
        return artifact.artifact_id

    def get(self, artifact_id: str) -> Optional[BaseArtifact]:
        path = self._artifact_path(artifact_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize(raw)

    def get_by_type(self, artifact_type: ArtifactType) -> list[BaseArtifact]:
        matching_ids = [
            aid for aid, meta in self._index.items()
            if meta.get("artifact_type") == artifact_type.value
        ]
        results = []
        for aid in matching_ids:
            art = self.get(aid)
            if art is not None:
                results.append(art)
        results.sort(key=lambda a: a.created_at, reverse=True)
        return results

    def get_by_project(self, project_id: str) -> list[BaseArtifact]:
        matching_ids = [
            aid for aid, meta in self._index.items()
            if meta.get("project_id") == project_id
        ]
        results = []
        for aid in matching_ids:
            art = self.get(aid)
            if art is not None:
                results.append(art)
        results.sort(key=lambda a: a.created_at, reverse=True)
        return results

    def update(self, artifact: BaseArtifact) -> None:
        if artifact.artifact_id not in self._index:
            raise KeyError(f"Artifact not found: {artifact.artifact_id}")
        self.add(artifact)

    def delete(self, artifact_id: str) -> bool:
        path = self._artifact_path(artifact_id)
        existed = path.exists()
        if existed:
            path.unlink()
        self._index.pop(artifact_id, None)
        for pid, children in list(self._children_index.items()):
            if artifact_id in children:
                children.remove(artifact_id)
        self._children_index.pop(artifact_id, None)
        self._save_index()
        if existed:
            logger.info("Artifact deleted: %s", artifact_id)
        return existed

    def list_all(self) -> list[str]:
        return sorted(self._index.keys())

    def count(self) -> int:
        return len(self._index)

    def get_parents(self, artifact_id: str) -> list[BaseArtifact]:
        meta = self._index.get(artifact_id)
        if not meta:
            return []
        parents = []
        for pid in meta.get("parent_ids", []):
            art = self.get(pid)
            if art is not None:
                parents.append(art)
        return parents

    def get_children(self, artifact_id: str) -> list[BaseArtifact]:
        child_ids = self._children_index.get(artifact_id, [])
        children = []
        for cid in child_ids:
            art = self.get(cid)
            if art is not None:
                children.append(art)
        return children

    def get_dependencies(self, artifact_id: str) -> list[BaseArtifact]:
        return self.get_parents(artifact_id)

    def get_dependents(self, artifact_id: str) -> list[BaseArtifact]:
        return self.get_children(artifact_id)

    def get_subgraph(self, root_id: str, max_depth: int = 5) -> dict[str, Any]:
        visited: set[str] = set()
        nodes: list[dict] = []
        edges: list[dict] = []
        queue: list[tuple[str, int]] = [(root_id, 0)]
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            art = self.get(current_id)
            if art is None:
                continue
            nodes.append({
                "id": art.artifact_id,
                "type": art.artifact_type.value,
                "label": art.label,
                "confidence": art.confidence,
                "status": art.status.value,
            })
            for pid in art.parent_ids:
                edges.append({"source": pid, "target": art.artifact_id})
            for cid in self._children_index.get(current_id, []):
                if cid not in visited:
                    queue.append((cid, depth + 1))
        return {"nodes": nodes, "edges": edges, "root_id": root_id}

    def export(self, project_id: str | None = None) -> dict[str, Any]:
        artifacts = (
            self.get_by_project(project_id)
            if project_id
            else [self.get(aid) for aid in self.list_all()]
        )
        artifacts = [a for a in artifacts if a is not None]

        biz_models = [a for a in artifacts if a.artifact_type == ArtifactType.BUSINESS_MODEL]
        assumptions = [a for a in artifacts if a.artifact_type == ArtifactType.ASSUMPTION]
        risks = [a for a in artifacts if a.artifact_type == ArtifactType.RISK]
        constraints = [a for a in artifacts if a.artifact_type == ArtifactType.CONSTRAINT]
        evidences = [a for a in artifacts if a.artifact_type == ArtifactType.EVIDENCE]
        coverages = [a for a in artifacts if a.artifact_type == ArtifactType.COVERAGE]
        gaps = [a for a in artifacts if a.artifact_type == ArtifactType.GAP]
        decisions = [a for a in artifacts if a.artifact_type == ArtifactType.DECISION]

        result: dict[str, Any] = {
            "business_domain": biz_models[0].domain if biz_models else "",
            "objectives": biz_models[0].objectives if biz_models else [],
            "roles": [],
            "workflow": [],
            "responsibilities": [],
            "sla": [],
            "metrics": [],
            "kpi": [],
            "risks": [
                {"risk": r.risk_statement, "severity": r.severity.value,
                 "probability": r.probability.value, "mitigation": r.mitigation}
                for r in risks
            ],
            "risk": {
                dim.value: [
                    {"risk": r.risk_statement, "severity": r.severity.value,
                     "probability": r.probability.value, "mitigation": r.mitigation}
                    for r in risks if r.dimension.value == dim.value
                ]
                for dim in list(RiskDimension)
            },
            "strategy": {},
            "optimization": {},
            "composed": {},
            "report": {},
            "status": "legacy_export",
            "_version": 2,
            "_artifact_graph": {
                "total_artifacts": len(artifacts),
                "biz_models": [a.model_dump() for a in biz_models],
                "assumptions": [a.model_dump() for a in assumptions],
                "risks": [a.model_dump() for a in risks],
                "constraints": [a.model_dump() for a in constraints],
                "evidences": [a.model_dump() for a in evidences],
                "coverages": [a.model_dump() for a in coverages],
                "gaps": [a.model_dump() for a in gaps],
                "decisions": [a.model_dump() for a in decisions],
            },
        }
        return result

    def _deserialize(self, raw: dict) -> BaseArtifact:
        atype = ArtifactType(raw.get("artifact_type", "business_model"))
        cls = ARTIFACT_CLASS_MAP.get(atype, BaseArtifact)
        return cls(**raw)

    # -- Factory methods --

    def create_business_model(self, label: str, project_id: str = "",
                              domain: str = "", objectives: list[str] | None = None,
                              **kwargs) -> BusinessModelArtifact:
        art = BusinessModelArtifact(label=label, project_id=project_id,
                                    domain=domain, objectives=objectives or [], **kwargs)
        self.add(art)
        return art

    def create_assumption(self, statement: str, parent_ids: list[str] | None = None,
                          category: str = "", criticality: Severity = Severity.MEDIUM,
                          **kwargs) -> AssumptionArtifact:
        art = AssumptionArtifact(statement=statement, parent_ids=parent_ids or [],
                                 category=category, criticality=criticality, **kwargs)
        self.add(art)
        return art

    def create_risk(self, risk_statement: str, parent_ids: list[str] | None = None,
                    dimension: RiskDimension = RiskDimension.OPERATIONAL,
                    severity: Severity = Severity.MEDIUM, **kwargs) -> RiskArtifact:
        art = RiskArtifact(risk_statement=risk_statement, parent_ids=parent_ids or [],
                           dimension=dimension, severity=severity, **kwargs)
        self.add(art)
        return art

    def create_gap(self, gap_statement: str, parent_ids: list[str] | None = None,
                   category: GapCategory = GapCategory.EVIDENCE_MISSING,
                   **kwargs) -> GapArtifact:
        art = GapArtifact(gap_statement=gap_statement, parent_ids=parent_ids or [],
                          category=category, **kwargs)
        self.add(art)
        return art

    def create_decision(self, decision_statement: str, parent_ids: list[str] | None = None,
                        rationale: str = "", **kwargs) -> DecisionArtifact:
        art = DecisionArtifact(decision_statement=decision_statement,
                               parent_ids=parent_ids or [], rationale=rationale, **kwargs)
        self.add(art)
        return art

    # ------------------------------------------------------------------
    # Snapshot & Versioning (Phase 0.5 - diff/version)
    # ------------------------------------------------------------------

    def snapshot(self, name: str = "", tag: str = "") -> dict[str, Any]:
        """Create a named snapshot of the current Artifact Graph state.

        Args:
            name: Human-readable snapshot label (e.g. "after_risk_analysis").
            tag: Optional tag (e.g. "run_3", "iteration_2").

        Returns:
            Snapshot metadata dict.
        """
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        snapshot_id = f"snap_{name or 'auto'}_{ts.replace(':', '-')}"

        # Collect all artifacts
        all_artifacts = {}
        for aid in self.list_all():
            art = self.get(aid)
            if art is not None:
                all_artifacts[aid] = art.model_dump()

        snapshot_data = {
            "snapshot_id": snapshot_id,
            "name": name or "snapshot",
            "tag": tag,
            "created_at": ts,
            "total_artifacts": len(all_artifacts),
            "artifact_types": {
                at.value: len([a for a in all_artifacts.values()
                               if a.get("artifact_type") == at.value])
                for at in ArtifactType
            },
            "artifacts": all_artifacts,
        }

        snap_path = self._data_dir / f"{snapshot_id}.json"
        snap_path.write_text(
            json.dumps(snapshot_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Snapshot saved: %s (%d artifacts)", snapshot_id, len(all_artifacts))
        return {
            "snapshot_id": snapshot_id,
            "name": name,
            "tag": tag,
            "created_at": ts,
            "total_artifacts": len(all_artifacts),
        }

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available snapshots, newest first."""
        snapshots = []
        for f in sorted(self._data_dir.glob("snap_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                snapshots.append({
                    "snapshot_id": data.get("snapshot_id", f.stem),
                    "name": data.get("name", ""),
                    "tag": data.get("tag", ""),
                    "created_at": data.get("created_at", ""),
                    "total_artifacts": data.get("total_artifacts", 0),
                })
            except Exception:
                continue
        return snapshots

    def load_snapshot(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """Load a snapshot by ID. Returns full snapshot data or None."""
        snap_path = self._data_dir / f"{snapshot_id}.json"
        if not snap_path.exists():
            return None
        return json.loads(snap_path.read_text(encoding="utf-8"))

    def diff(
        self,
        snapshot_a: Optional[str] = None,
        snapshot_b: Optional[str] = None,
    ) -> dict[str, Any]:
        """Diff two snapshots (or snapshot vs current state).

        If snapshot_a is None, compares against current state.
        If both are provided, compares the two snapshots.

        Returns:
            {
                "added": [...], "removed": [...], "modified": [...],
                "summary": "3 added, 1 removed, 2 modified"
            }
        """
        # Load snapshot A (or current state)
        if snapshot_a:
            snap_a_data = self.load_snapshot(snapshot_a)
            if snap_a_data is None:
                raise ValueError(f"Snapshot not found: {snapshot_a}")
            artifacts_a = snap_a_data.get("artifacts", {})
        else:
            artifacts_a = {}
            for aid in self.list_all():
                art = self.get(aid)
                if art is not None:
                    artifacts_a[aid] = art.model_dump()

        # Load snapshot B
        if snapshot_b:
            snap_b_data = self.load_snapshot(snapshot_b)
            if snap_b_data is None:
                raise ValueError(f"Snapshot not found: {snapshot_b}")
            artifacts_b = snap_b_data.get("artifacts", {})
        else:
            raise ValueError("snapshot_b is required for diff; use snapshot_a=None for current state")

        ids_a = set(artifacts_a.keys())
        ids_b = set(artifacts_b.keys())

        added_ids = ids_b - ids_a
        removed_ids = ids_a - ids_b
        common_ids = ids_a & ids_b

        added = [
            {"artifact_id": aid, "type": artifacts_b[aid].get("artifact_type", ""),
             "label": artifacts_b[aid].get("label", "")}
            for aid in added_ids
        ]
        removed = [
            {"artifact_id": aid, "type": artifacts_a[aid].get("artifact_type", ""),
             "label": artifacts_a[aid].get("label", "")}
            for aid in removed_ids
        ]

        modified = []
        for aid in common_ids:
            a_data = artifacts_a[aid]
            b_data = artifacts_b[aid]

            # Compare key fields
            changed_fields = []
            for field in ("label", "description", "confidence", "status",
                          "risk_statement", "mitigation", "validated",
                          "rationale", "resolution", "resolved", "severity"):
                a_val = str(a_data.get(field, ""))
                b_val = str(b_data.get(field, ""))
                if a_val != b_val:
                    changed_fields.append(field)

            if changed_fields:
                modified.append({
                    "artifact_id": aid,
                    "type": a_data.get("artifact_type", ""),
                    "label": a_data.get("label", ""),
                    "changed_fields": changed_fields,
                })

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "summary": f"{len(added)} added, {len(removed)} removed, {len(modified)} modified",
        }

    def restore_snapshot(self, snapshot_id: str) -> int:
        """Restore the store to a previous snapshot state.

        WARNING: This deletes all current artifacts and replaces them
        with the snapshot contents.

        Returns:
            Number of artifacts restored.
        """
        snap_data = self.load_snapshot(snapshot_id)
        if snap_data is None:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # Clear current state
        for aid in list(self.list_all()):
            self.delete(aid)

        # Reload artifacts from snapshot
        artifacts = snap_data.get("artifacts", {})
        for raw in artifacts.values():
            art = self._deserialize(raw)
            # Force-add without re-index (direct file write)
            path = self._artifact_path(art.artifact_id)
            path.write_text(
                art.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._index[art.artifact_id] = {
                "artifact_type": art.artifact_type.value,
                "project_id": art.project_id,
                "label": art.label,
                "parent_ids": art.parent_ids,
                "confidence": art.confidence,
                "status": art.status.value,
                "tags": art.tags,
                "created_at": art.created_at,
                "updated_at": art.updated_at,
            }

        # Rebuild children index
        self._children_index = defaultdict(list)
        for art_id, meta in self._index.items():
            for pid in meta.get("parent_ids", []):
                self._children_index[pid].append(art_id)

        self._save_index()
        logger.info("Restored snapshot %s: %d artifacts", snapshot_id, len(artifacts))
        return len(artifacts)
