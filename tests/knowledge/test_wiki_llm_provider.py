from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

from app.promptops import PromptOpsError, PromptTask
from app.knowledge.wiki_compiler import WikiCompiler
from app.knowledge.wiki_llm_provider import _WIKI_PROPOSAL_SCHEMA, SOPWikiCompilerProvider, WikiLLMProviderError
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class SequenceStructuredClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses: Iterator[dict] = iter(responses)
        self.calls: list[dict] = []

    def chat_structured(self, system_prompt, user_prompt, temperature=0.3, max_tokens=1200):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return next(self._responses)


class RecordingPromptOps:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        return SimpleNamespace(output=self.output)


class FailingPromptOps:
    def run_structured(self, _request):
        raise PromptOpsError("payment_required")


def test_provider_preserves_a_safe_external_failure_category():
    provider = SOPWikiCompilerProvider(provider="deepseek", promptops=FailingPromptOps())

    try:
        provider.compile_wiki("[source:source-a] Evidence.", project_id="project-a")
    except WikiLLMProviderError as exc:
        assert exc.category == "payment_required"
        assert str(exc) == "Wiki LLM provider is unavailable (payment_required)"
    else:
        raise AssertionError("expected the provider failure to be surfaced")


def test_provider_repairs_missing_operation_and_compiles_a_reviewable_proposal(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "wiki-provider.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="decision.md",
            raw_content="Every customer-data export requires human approval before release.",
            trust_level="trusted",
        )
    ).source
    invalid = {
        "rationale": "Capture the approval rule.",
        "operations": [
            {
                "path": "wiki/decisions/customer-data-export.md",
                "content": "Customer-data exports require human approval.",
                "source_ids": [source["id"]],
            }
        ],
    }
    valid = {
        "rationale": "Capture the release control as a reusable decision.",
        "operations": [
            {
                "operation": "create",
                "path": "wiki/decisions/customer-data-export.md",
                "content": (
                    "---\ntitle: Customer-data export approval\nkind: decision\n---\n\n"
                    f"Customer-data exports require human approval before release. [source:{source['id']}]"
                ),
                "source_ids": [source["id"]],
            }
        ],
    }
    client = SequenceStructuredClient([invalid, valid])
    try:
        result = WikiCompiler(
            repo,
            SOPWikiCompilerProvider(provider="deepseek", client=client),
        ).compile_maintenance(
            project_id="project-a",
            source_ids=[source["id"]],
            trigger="manual",
            rules_text=build_default_agents_rules("project-a"),
        )

        assert result.proposal["status"] == "draft"
        assert result.proposal["operations"][0]["operation"] == "create"
        assert len(client.calls) == 2
        assert "\"operation\"" in client.calls[0]["system_prompt"]
        assert "previous response was rejected" in client.calls[1]["system_prompt"]
    finally:
        repo.close()


def test_provider_schema_requires_a_project_specific_increment():
    assert "factual glossary" in _WIKI_PROPOSAL_SCHEMA
    assert "named project workflow" in _WIKI_PROPOSAL_SCHEMA
    assert "applicability boundary" in _WIKI_PROPOSAL_SCHEMA


def test_provider_uses_promptops_with_project_scope_and_versioned_revision():
    valid = {
        "rationale": "Capture a durable project decision.",
        "operations": [
            {
                "operation": "create",
                "path": "wiki/decisions/approval.md",
                "content": "---\ntitle: Approval\nkind: decision\n---\n\nApproval is required. [source:source-a]",
                "source_ids": ["source-a"],
            }
        ],
    }
    promptops = RecordingPromptOps(valid)

    result = SOPWikiCompilerProvider(provider="deepseek", promptops=promptops).compile_wiki(
        "[source:source-a] Approval is required.",
        project_id="project-a",
    )

    assert result == valid
    assert len(promptops.requests) == 1
    request = promptops.requests[0]
    assert request.project_id == "project-a"
    assert request.task == PromptTask.WIKI_COMPILATION
    assert request.revision == "wiki-proposal-v1"
    assert request.provider == "deepseek"
    assert request.timeout_seconds == 90.0
    assert request.max_attempts == 1
