import asyncio

from app.artifacts import ArtifactGraphStore
from app.artifacts.types import ArtifactType
from app.capabilities.executor import NanobotAgentBackend
from app.capabilities.registry import build_default_registry


class ProjectSpecificLLM:
    last_mode = "real"
    last_usage = None

    def __init__(self):
        self.prompts = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "Process Designer" in prompt:
            return """{
              "title": "New-media content signal loop",
              "summary": "Turn each weekly topic into an evidence-led publishing and review loop.",
              "differentiators": ["Audience-signal gate before drafting"],
              "sections": [{"title": "Signal triage", "details": ["Score audience questions before assigning a topic"]}],
              "actions": [{"title": "Select weekly signal", "owner": "Audience editor", "trigger": "Friday review", "action": "Rank questions by repeat demand", "output": "ranked editorial brief", "metric": "three validated themes", "timebox": "45 minutes"}],
              "evidence_gaps": ["No baseline retention data yet"],
              "source_refs": ["source-editorial-01"]
            }"""
        return """{
          "title": "Pilot decision brief",
          "summary": "Run one content lane for four weeks before scaling.",
          "differentiators": ["Retain rejected ideas as learning evidence"],
          "sections": [{"title": "Pilot boundary", "details": ["One audience segment and one content lane"]}],
          "actions": [{"title": "Review pilot", "owner": "Editor lead", "trigger": "Week four", "action": "Compare retention with baseline", "output": "scale or revise decision", "metric": "returning-reader rate", "timebox": "30 minutes"}],
          "evidence_gaps": ["No competitor baseline"]
        }"""


def test_sop_and_report_outputs_are_persisted_as_project_specific_deliverables(tmp_path):
    registry = build_default_registry()
    sop = registry.get("sop_design")
    report = registry.get("report_composition")

    assert sop is not None
    assert report is not None
    assert sop.output_artifact_types == [ArtifactType.DELIVERABLE]
    assert report.output_artifact_types == [ArtifactType.DELIVERABLE]

    store = ArtifactGraphStore(str(tmp_path / "artifacts"))
    llm = ProjectSpecificLLM()
    backend = NanobotAgentBackend(store, llm_service=llm)

    async def execute_deliverables():
        sop_result = await backend.execute(sop, "New-media content operations", "project-1")
        report_result = await backend.execute(report, "New-media content operations", "project-1")
        return sop_result, report_result

    sop_result, report_result = asyncio.run(execute_deliverables())

    assert sop_result.status == "success"
    assert report_result.status == "success"
    assert len(sop_result.artifacts_produced) == 1
    assert len(report_result.artifacts_produced) == 1

    exported = store.export("project-1")
    deliverables = exported["_artifact_graph"]["deliverables"]
    assert [item["kind"] for item in deliverables] == ["sop", "decision_brief"]
    assert deliverables[0]["actions"][0]["trigger"] == "Friday review"
    assert deliverables[0]["differentiators"] == ["Audience-signal gate before drafting"]
    assert deliverables[0]["evidence_refs"] == ["source-editorial-01"]
    assert "PROJECT BRIEF" in llm.prompts[0]
    assert "New-media content operations" in llm.prompts[0]
