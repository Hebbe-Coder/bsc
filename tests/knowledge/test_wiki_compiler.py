import pytest

from app.knowledge.wiki_compiler import WikiCompilationError, WikiCompiler
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class FakeCompilerProvider:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def compile_wiki(self, prompt):
        self.prompts.append(prompt)
        return self.response


def _eligible_source(repo):
    return SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="brief.md",
            raw_content="# Product brief\nHuman approval is mandatory.",
            trust_level="trusted",
        )
    ).source


def test_compiler_persists_draft_proposal_without_mutating_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "compiler.db"))
    source = _eligible_source(repo)
    provider = FakeCompilerProvider(
        {
            "rationale": "Capture the explicit approval rule.",
            "operations": [
                {
                    "operation": "create",
                    "path": "wiki/decisions/human-approval.md",
                    "content": "# Human approval\n\nHuman approval is mandatory. [source:%s]" % source["id"],
                    "source_ids": [source["id"]],
                }
            ],
        }
    )
    try:
        result = WikiCompiler(repo, provider).compile_maintenance(
            project_id="project-a",
            source_ids=[source["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
        )

        assert result.proposal["status"] == "draft"
        assert result.proposal["source_ids"] == [source["id"]]
        assert result.run["status"] == "completed"
        assert repo.get_source("project-a", source["id"])["status"] == "eligible"
        assert "wiki/log.md" in [item["path"] for item in result.proposal["operations"]]
        assert {"wiki/overview.md", "wiki/index.md", "wiki/log.md"} <= {item["path"] for item in result.proposal["operations"]}
        assert provider.prompts
    finally:
        repo.close()


@pytest.mark.parametrize(
    "response, message",
    [
        ("not-json", "object"),
        ({"operations": [{"operation": "create", "path": "raw/private.md", "content": "x", "source_ids": ["source-a"]}]}, "wiki/"),
        ({"operations": [{"operation": "create", "path": "wiki/a.md", "content": "x", "source_ids": ["unknown"]}]}, "unknown source"),
    ],
)
def test_compiler_records_failed_run_for_invalid_provider_output(tmp_path, response, message):
    repo = WikiRepository(db_path=str(tmp_path / "compiler-failure.db"))
    source = _eligible_source(repo)
    try:
        with pytest.raises(WikiCompilationError, match=message):
            WikiCompiler(repo, FakeCompilerProvider(response)).compile_maintenance(
                project_id="project-a",
                source_ids=[source["id"]],
                trigger="manual",
                rules_text=build_default_agents_rules("project-a"),
            )

        run = repo.list_runs("project-a")[0]
        assert run["status"] == "failed"
        assert repo.list_sources("project-a", status="eligible")[0]["id"] == source["id"]
    finally:
        repo.close()
