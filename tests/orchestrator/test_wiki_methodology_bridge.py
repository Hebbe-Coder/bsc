from app.knowledge.context_pack import ContextPackBuilder
from app.knowledge.growth_context import GrowthContextBuilder
from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules
from app.orchestrator.agents.sop_builder import SopBuilderAgent
from app.orchestrator.methodology import MethodologyBridge
from types import SimpleNamespace


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
        growth_enabled=False,
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


class RecordingPromptOps:
    def __init__(self, output):
        self.output = output
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        return SimpleNamespace(output=self.output)


class FakeSopEngine:
    def generate_full_sop_report(self, *_args, **_kwargs):
        return {"workflow": [], "roles": [], "sla": []}


def test_sop_builder_exposes_wiki_context_metadata_and_prompt():
    provider = FakeWikiContextProvider()
    llm = RecordingLLM()
    agent = SopBuilderAgent(
        llm_service=llm,
        bridge=MethodologyBridge(
            service=FakeKnowledgeService(), wiki_context_provider=provider, wiki_enabled=True,
            growth_enabled=False,
        ),
    )

    result = agent.run({"name": "approval"}, _engine=FakeSopEngine(), project_id="project-a")

    assert "Project Wiki Context" in llm.prompt
    assert result["sop"]["_knowledge_context"]["knowledge_context_used"] is True
    assert result["sop"]["_knowledge_context"]["source_ids"] == ["source-project-a"]


class FakeGrowthContextProvider:
    def build_context(self, *, project_id, task):
        return GrowthContextBuilder(max_characters=2_000).build(
            project_id=project_id,
            profile={
                "project_id": project_id,
                "revision": 3,
                "audience": "operators",
            },
            rules=f"Rules for {project_id}",
            rules_revision="rules-v3",
            task=task,
            pages=[
                {
                    "id": "page-a",
                    "project_id": project_id,
                    "revision": "page-r2",
                    "status": "published",
                    "content": "Published operating constraint",
                }
            ],
            sources=[
                {
                    "id": "source-a",
                    "project_id": project_id,
                    "revision": "source-r1",
                    "status": "eligible",
                    "raw_content": "External evidence",
                }
            ],
            methods=[
                {
                    "id": "method-a",
                    "project_id": project_id,
                    "revision": "method-r4",
                    "status": "published",
                    "body": "Approved method",
                }
            ],
            outputs=[
                {
                    "id": "output-a",
                    "project_id": project_id,
                    "revision": "output-r2",
                    "status": "accepted",
                    "content": "Accepted example",
                }
            ],
            assumptions=["Audience remains operators"],
            research_gaps=["Confirm regional policy"],
        )


def test_growth_context_takes_precedence_and_preserves_exact_revisions():
    wiki_provider = FakeWikiContextProvider()
    llm = RecordingLLM()
    bridge = MethodologyBridge(
        service=FakeKnowledgeService(),
        wiki_context_provider=wiki_provider,
        wiki_enabled=True,
        growth_context_provider=FakeGrowthContextProvider(),
        growth_enabled=True,
    )
    agent = SopBuilderAgent(llm_service=llm, bridge=bridge)

    result = agent.run(
        {"name": "approval"}, _engine=FakeSopEngine(), project_id="project-a"
    )
    metadata = result["sop"]["_knowledge_context"]

    assert "Project Growth Context" in llm.prompt
    assert "Project Wiki Context" not in llm.prompt
    assert wiki_provider.projects == []
    assert metadata["context_type"] == "growth"
    assert metadata["profile_revision"] == 3
    assert metadata["page_ids"] == ["page-a"]
    assert metadata["source_ids"] == ["source-a"]
    assert metadata["method_revision_ids"] == ["method-r4"]
    assert metadata["output_ids"] == ["output-a"]
    assert metadata["assumptions"] == [
        "assumption:unresolved_claims",
        "Audience remains operators",
    ]
    assert metadata["research_gaps"] == ["Confirm regional policy"]


def test_sop_builder_routes_default_composition_through_project_scoped_promptops():
    promptops = RecordingPromptOps({"sop": {"sops": []}})
    agent = SopBuilderAgent(
        bridge=MethodologyBridge(service=FakeKnowledgeService()),
        promptops=promptops,
    )

    result = agent.run(
        {"name": "approval"},
        _engine=FakeSopEngine(),
        project_id="project-a",
    )

    assert result["sop"]["sops"] == []
    assert len(promptops.requests) == 1
    request = promptops.requests[0]
    assert request.project_id == "project-a"
    assert request.task.value == "sop_composition"
    assert request.revision == "sop-builder-v1"
    assert request.resolved_agent_definition.agent_id == "sop_composer"
