"""Typed Skill contracts shared by discovery and the API layer."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field


class SkillField(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
    type: str = Field(default="string", min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    required: bool = True


class SkillManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(default="1.0.0", min_length=1, max_length=40)
    description: str = Field(default="", max_length=1000)
    source: Literal["builtin", "project"] = "project"
    source_path: str = ""
    entrypoint: str = ""
    inputs: list[SkillField] = Field(default_factory=list)
    outputs: list[SkillField] = Field(default_factory=list)
    prompt: str = ""
    hooks: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    enabled: bool = True
    executable: bool = False

    @property
    def chain_id(self) -> str:
        prefix = "chain:"
        return self.entrypoint[len(prefix):] if self.entrypoint.startswith(prefix) else ""

    @property
    def revision(self) -> str:
        body_hash = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:12]
        return f"{self.version}:{body_hash}"

    def public_payload(self) -> dict:
        return self.model_dump(exclude={"prompt"})


def builtin_skill_manifests() -> list[SkillManifest]:
    definitions = [
        ("prd-analysis", "PRD Analysis", "Analyze a product requirements document", "prd_content"),
        ("objective-extraction", "Objective Extraction", "Extract business objectives", "business_content"),
        ("kpi-extraction", "KPI Extraction", "Identify measurable key performance indicators", "business_content"),
        ("chart-generation", "Chart Generation", "Generate an ECharts configuration", "data_description"),
        ("risk-assessment", "Risk Assessment", "Assess business and operational risks", "business_context"),
        ("strategy-analysis", "Strategy Analysis", "Generate SWOT and strategy analysis", "business_info"),
        ("presentation-generation", "Presentation Generation", "Generate a presentation outline", "business_content"),
        ("report-generation", "Report Generation", "Generate a business analysis report", "business_content"),
    ]
    return [
        SkillManifest(
            id=skill_id,
            name=name,
            description=description,
            source="builtin",
            source_path="app/api/skill_routes.py",
            entrypoint=f"chain:{skill_id}",
            inputs=[SkillField(name=input_name)],
            outputs=[SkillField(name="result")],
            executable=True,
        )
        for skill_id, name, description, input_name in definitions
    ]
