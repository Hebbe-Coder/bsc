from app.knowledge.context_pack import ContextPackBuilder
from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules
from app.orchestrator.agents.sop_builder import SopBuilderAgent
from app.orchestrator.methodology import MethodologyBridge


class FakeKnowledgeService:
    def retrieve(self, **_kwargs):
        return []


class FakeWikiContextProvider:
    def __init__(self):
        self.projects = []

    def build_context(self, *, project_id, task_constraints):
        self.projects.append(project_id)
        return ContextPackBuilder(max_characters=2_000).build(
            project_id=project_id,
            rules=parse_project_rules(build_default_agents_rules(project_id)),
            task_constraints=task_constraints,
            sources=[
                {
                    "id": f"source-{project_id}",
                    "project_id": project_id,
                    "raw_content": f"Evidence only for {project_id}.",
                }
            ],
        )


def test_methodology_bridge_keeps_wiki_context_opt_in_and_project_scoped():
    provider = FakeWikiContextProvider()
    bridge = MethodologyBridge(
        service=FakeKnowledgeService(),
        wiki_context_provider=provider,
        wiki_enabled=True,
    )

    project_a = bridge.retrieve_wiki_context("project-a", "approval workflow")
    project_b = bridge.retrieve_wiki_context("project-b", "marketing workflow")
    disabled = MethodologyBridge(service=FakeKnowledgeService()).retrieve_wiki_context("project-a", "approval")

    assert project_a["knowledge_context_used"] is True
    assert "project-a" in project_a["context_block"]
    assert "project-b" not in project_a["context_block"]
    assert project_b["source_ids"] == ["source-project-b"]
    assert disabled == {
        "knowledge_context_used": False,
        "context_block": "",
        "context_pack_id": "",
        "page_ids": [],
        "source_ids": [],
        "assumptions": [],
    }


class RecordingLLM:
    def __init__(self):
        self.prompt = ""

    def chat(self, _system_prompt, user_prompt, **_kwargs):
        self.prompt = user_prompt
        return {"sop": {"sops": []}}


class FakeSopEngine:
    def generate_full_sop_report(self, *_args, **_kwargs):
        return {"workflow": [], "roles": [], "sla": []}


def test_sop_builder_exposes_wiki_context_metadata_and_prompt():
    provider = FakeWikiContextProvider()
    llm = RecordingLLM()
    agent = SopBuilderAgent(
        llm_service=llm,
        bridge=MethodologyBridge(
            service=FakeKnowledgeService(), wiki_context_provider=provider, wiki_enabled=True
        ),
    )

    result = agent.run({"name": "approval"}, _engine=FakeSopEngine(), project_id="project-a")

    assert "Project Wiki Context" in llm.prompt
    assert result["sop"]["_knowledge_context"]["knowledge_context_used"] is True
    assert result["sop"]["_knowledge_context"]["source_ids"] == ["source-project-a"]
