import json

from app.artifacts import ArtifactGraphStore, ArtifactStatus, DiagnosisArtifact, MissionArtifact, SOPVersionArtifact
from app.core.config import settings
from app.knowledge.context_pack import WikiContextProvider
from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import SourceRecord
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.pbos.context import PBOSGovernedContextProvider, PBOSVaultContextBuilder
from app.pbos.compiler import PBOSPlanCompiler
from app.pbos.service import PBOSService


def _mission(store: ArtifactGraphStore, artifact_id: str, title: str, intent: str) -> MissionArtifact:
    mission = MissionArtifact(
        artifact_id=artifact_id,
        mission_id=artifact_id,
        project_id="personal",
        label=title,
        title=title,
        intent=intent,
        context={"goal": intent, "constraints": ["solo delivery", "evidence-first"]},
    )
    store.add(mission)
    return mission


def test_settings_compiler_uses_the_isolated_pbos_request_timeout(monkeypatch):
    monkeypatch.setattr(settings, "SOP_LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "configured-test-key")

    compiler = PBOSPlanCompiler.from_settings()

    assert compiler.client is not None
    assert compiler.client.timeout == settings.PBOS_LLM_TIMEOUT_SECONDS


def test_vault_context_is_bounded_and_excludes_raw_sources(tmp_path):
    active = tmp_path / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text("# Delivery boundary\n\nShip the evidence loop before connectors.", encoding="utf-8")
    raw = tmp_path / "01_Sources"
    raw.mkdir()
    (raw / "unreviewed.md").write_text("this must not enter a PBOS plan", encoding="utf-8")

    context = PBOSVaultContextBuilder(tmp_path).build()

    assert context["availability"] == "available"
    assert [item["path"] for item in context["documents"]] == ["03_Projects/active/delivery.md"]
    assert "unreviewed" not in str(context)


def test_vault_context_prioritizes_working_methods_and_skips_unpublished_wiki_files(tmp_path):
    active = tmp_path / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "boundary.md").write_text("---\ntitle: Boundary\n---\n# Delivery boundary\nUse an evidence gate.", encoding="utf-8")
    (active / "map.excalidraw.md").write_text("# Drawing\nThis is not planning context.", encoding="utf-8")
    method = tmp_path / "methods" / "delivery-loop"
    method.mkdir(parents=True)
    (method / "SKILL.md").write_text("# Verified delivery method\nKeep outcomes reviewable.", encoding="utf-8")
    wiki = tmp_path / "wiki" / "concepts"
    wiki.mkdir(parents=True)
    (wiki / "evidence.md").write_text("# Evidence governance\nSeparate fact from inference.", encoding="utf-8")
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "legacy.md").write_text("# Legacy output\nDo not prioritize this over the method.", encoding="utf-8")

    context = PBOSVaultContextBuilder(tmp_path).build()

    assert [item["path"] for item in context["documents"]][:2] == [
        "03_Projects/active/boundary.md",
        "methods/delivery-loop/SKILL.md",
    ]
    assert "wiki/concepts/evidence.md" not in [item["path"] for item in context["documents"]]
    assert not any("excalidraw" in item["path"] for item in context["documents"])
    assert "title: Boundary" not in context["documents"][0]["excerpt"]


def test_governed_context_retrieves_only_published_wiki_with_source_lineage(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "governed-context.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = repo.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            origin="evidence.md",
            content_hash="a" * 64,
            raw_content="Published evidence about plugin extension delivery.",
            trust_level="trusted",
        )
    )
    published = (
        "---\ntitle: Published plugin extension\nkind: concept\nstatus: published\n---\n"
        "Use the governed plugin extension boundary. [source:source-a]\n"
    )
    contents = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/index.md": "# Index\n- [[wiki/concepts/published.md]]\n",
        "wiki/log.md": "# Log\n",
        "wiki/concepts/published.md": published,
    }
    vault = FilesystemWikiVault(vault_root, "project-a", "projects/project-a")
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[source["id"]])
    (project_root / "wiki" / "concepts" / "unpublished.md").write_text(
        "# Unpublished\nThis file must not enter a governed plan.", encoding="utf-8"
    )

    class Retrieval:
        def retrieve(self, *_args, **_kwargs):
            return [{"source": "wiki://project-a/wiki/concepts/published.md"}]

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=WikiContextProvider(repo, vault_root=vault_root, retrieval_service=Retrieval()),
    )
    try:
        context = provider.build(task_constraints=["plugin extension delivery"])

        assert context["availability"] == "available"
        assert context["documents"][0]["path"] == "wiki/concepts/published.md"
        assert context["documents"][0]["ref"].startswith("wiki:")
        assert context["documents"][0]["supporting_refs"] == ["source:source-a@" + "a" * 64]
        assert context["governed_wiki"]["page_ids"]
        assert "unpublished" not in str(context)
    finally:
        repo.close()


def test_governed_context_exposes_metadata_only_operational_state_for_completed_mirror(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    mirror = project_root / "01_Sources" / "bsc-evidence"
    mirror.mkdir(parents=True)
    # This deliberately proves the operational projection does not include
    # evidence bodies even when the managed mirror exists.
    (mirror / "source-a.md").write_text("private source body must remain out of plan state", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "operational-state.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            origin="evidence.md",
            content_hash="a" * 64,
            raw_content="private source body must remain out of plan state",
            trust_level="trusted",
            metadata={"obsidian_source_mirror": {"path": "01_Sources/bsc-evidence/source-a.md"}},
        )
    )

    class NoGovernedContext:
        def build_context(self, **_kwargs):
            return None

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=NoGovernedContext(),
    )
    try:
        context = provider.build(task_constraints=["delivery"])

        assert context["operational_state"]["source_lifecycle_counts"] == {"captured": 1}
        assert context["operational_state"]["managed_source_mirror"] == {
            "state": "available",
            "path": "01_Sources/bsc-evidence",
            "file_count": 1,
            "file_count_truncated": False,
            "recorded_source_count": 1,
        }
        assert "private source body" not in json.dumps(context, ensure_ascii=False)
    finally:
        repo.close()


def test_governed_context_exposes_configured_plugin_route_without_plugin_settings(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    clipper_path = project_root / "00_Inbox" / "web-clipper"
    clipper_path.mkdir(parents=True)
    settings_path = vault_root / ".obsidian" / "plugins" / "obsidian-clipper"
    settings_path.mkdir(parents=True)
    (settings_path / "data.json").write_text(
        json.dumps({
            "advancedStorageFolder": "projects/project-a/00_Inbox/web-clipper",
            "unrelated_secret": "must-not-reach-pbos-context",
        }),
        encoding="utf-8",
    )
    manifest = ObsidianPluginManifest.from_payload({
        "plugins": [{
            "id": "obsidian-clipper",
            "name": "Clipper",
            "adapter": "filesystem_drop",
            "input_paths": ["00_Inbox/web-clipper"],
        }],
    })
    manifest.write_to(project_root)
    manifest.set_trust(
        project_root,
        plugin_ids=["obsidian-clipper"],
        trusted=True,
        actor_id="test",
        reason="test route only",
    )
    repo = WikiRepository(db_path=str(tmp_path / "plugin-state.db"))
    repo.configure_vault("project-a", "projects/project-a")

    class NoGovernedContext:
        def build_context(self, **_kwargs):
            return None

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=NoGovernedContext(),
    )
    try:
        context = provider.build()

        assert context["operational_state"]["plugin_bridges"] == {
            "ready_route_count": 1,
            "routes": [{
                "id": "obsidian-clipper",
                "adapter": "filesystem_drop",
                "route_state": "configured_awaiting_export",
                "capture_state": "ready_for_first_export",
            }],
        }
        serialized = json.dumps(context, ensure_ascii=False)
        assert "must-not-reach-pbos-context" not in serialized
        assert "00_Inbox/web-clipper" not in serialized
        assert "projects/project-a" not in serialized
    finally:
        repo.close()


def test_governed_context_projects_declared_output_routes_and_registered_outputs(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    (project_root / "04_Outputs" / "codex").mkdir(parents=True)
    (project_root / "04_Outputs" / "copilot").mkdir(parents=True)
    manifest = ObsidianPluginManifest.from_payload({
        "plugins": [
            {
                "id": "codex-agent",
                "name": "Codex",
                "adapter": "filesystem_output",
                "input_paths": ["04_Outputs/codex"],
            },
            {
                "id": "copilot-agent",
                "name": "Copilot",
                "adapter": "filesystem_output",
                "input_paths": ["04_Outputs/copilot"],
            },
        ],
    })
    manifest.write_to(project_root)
    manifest.set_trust(
        project_root,
        plugin_ids=["codex-agent", "copilot-agent"],
        trusted=True,
        actor_id="test",
        reason="output bridge fixture",
    )
    repo = GrowthRepository(db_path=str(tmp_path / "output-route-state.db"))
    repo.configure_vault("project-a", "projects/project-a")
    repo.register_output(OutputAsset(
        id="codex-output",
        project_id="project-a",
        kind="external_plugin_output",
        content_hash="a" * 64,
        vault_path="outputs/2026/pending/codex.md",
        idempotency_key="codex-output",
        metadata={
            "obsidian_plugin": "codex-agent",
            "obsidian_adapter": "filesystem_output",
        },
    ))

    class NoGovernedContext:
        def build_context(self, **_kwargs):
            return None

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=NoGovernedContext(),
    )
    try:
        routes = provider.build()["operational_state"]["plugin_bridges"]

        assert routes == {
            "ready_route_count": 2,
            "routes": [
                {
                    "id": "codex-agent",
                    "adapter": "filesystem_output",
                    "route_state": "registered_output",
                    "capture_state": "registered_output",
                },
                {
                    "id": "copilot-agent",
                    "adapter": "filesystem_output",
                    "route_state": "configured_awaiting_output",
                    "capture_state": "ready_for_first_output",
                },
            ],
        }
    finally:
        repo.close()


def test_governed_context_does_not_treat_an_unledgered_managed_file_as_completed_mirror(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    mirror = project_root / "01_Sources" / "bsc-evidence"
    mirror.mkdir(parents=True)
    (mirror / "unledgered.md").write_text("a file alone must not claim BSC projection", encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "unledgered-mirror.db"))
    repo.configure_vault("project-a", "projects/project-a")

    class NoGovernedContext:
        def build_context(self, **_kwargs):
            return None

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=NoGovernedContext(),
    )
    try:
        state = provider.build()["operational_state"]["managed_source_mirror"]

        assert state["file_count"] == 1
        assert state["recorded_source_count"] == 0
        assert state["state"] == "awaiting_projection"
    finally:
        repo.close()


def test_governed_context_retains_a_retrieved_published_page_when_source_budget_displaces_it(tmp_path):
    vault_root = tmp_path / "vault"
    project_root = vault_root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repo = WikiRepository(db_path=str(tmp_path / "governed-context-budget.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = repo.create_source(
        SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            origin="evidence.md",
            content_hash="a" * 64,
            raw_content="Published evidence about plugin extension delivery. " * 300,
            trust_level="trusted",
        )
    )
    published = (
        "---\ntitle: Published plugin extension\nkind: concept\nstatus: published\n---\n"
        "Use the governed plugin extension boundary. [source:source-a]\n"
        + ("Published plugin extension evidence. " * 340)
    )
    contents = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/index.md": "# Index\n- [[wiki/concepts/published.md]]\n",
        "wiki/log.md": "# Log\n",
        "wiki/concepts/published.md": published,
    }
    vault = FilesystemWikiVault(vault_root, "project-a", "projects/project-a")
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[source["id"]])

    class Retrieval:
        def retrieve(self, *_args, **_kwargs):
            return [
                {"source": "wiki://project-a/wiki/concepts/published.md"},
                {"source": "evidence://project-a/source-a"},
            ]

    provider = PBOSGovernedContextProvider(
        project_root,
        project_id="project-a",
        vault_root=vault_root,
        repository=repo,
        wiki_context_provider=WikiContextProvider(repo, vault_root=vault_root, retrieval_service=Retrieval()),
    )
    try:
        context = provider.build(task_constraints=["plugin extension delivery"])

        assert context["governed_wiki"]["page_ids"] == []
        assert context["documents"][0]["path"] == "wiki/concepts/published.md"
        assert context["documents"][0]["ref"].startswith("wiki:")
        assert context["documents"][0]["supporting_refs"] == ["source:source-a@" + "a" * 64]
    finally:
        repo.close()


def test_vault_context_prioritizes_latest_weekly_next_context_before_full_active_root(tmp_path):
    active = tmp_path / "03_Projects" / "active"
    active.mkdir(parents=True)
    for index in range(PBOSVaultContextBuilder.MAX_DOCUMENTS):
        (active / f"active-{index}.md").write_text(
            f"# Active {index}\nA governed active note for context ordering.",
            encoding="utf-8",
        )
    older = tmp_path / "distillations" / "每周蒸馏" / "2026-W30"
    latest = tmp_path / "distillations" / "每周蒸馏" / "2026-W31"
    older.mkdir(parents=True)
    latest.mkdir(parents=True)
    (older / "03-下周上下文包.md").write_text(
        "# Older context\nThis must not displace the latest context package.",
        encoding="utf-8",
    )
    (latest / "03-下周上下文包.md").write_text(
        "# Latest context\nCarry forward only cited evidence and open verification questions.",
        encoding="utf-8",
    )

    context = PBOSVaultContextBuilder(tmp_path).build()

    assert context["documents"][0]["path"] == "distillations/每周蒸馏/2026-W31/03-下周上下文包.md"
    assert "distillations/每周蒸馏/2026-W30/03-下周上下文包.md" not in [
        item["path"] for item in context["documents"]
    ]
    assert len(context["documents"]) == PBOSVaultContextBuilder.MAX_DOCUMENTS


def test_compiler_changes_execution_system_by_mission_and_cites_vault_context(tmp_path):
    root = tmp_path / "vault"
    active = root / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text("# Current delivery\nFreeze contracts before platform expansion.", encoding="utf-8")
    context = PBOSVaultContextBuilder(root).build()
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "engineering", "Agent runtime delivery", "Deliver the verified Agent runtime loop")
    _mission(store, "growth", "Content growth experiment", "Improve short-video retention for an AI product")
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: context,
        plan_compiler=PBOSPlanCompiler(),
    )
    service.save_profile({
        "focus": ["AI systems", "knowledge engineering"],
        "goals": ["ship an evidence-backed personal operating system"],
        "preferences": {"architecture_first": True},
        "resources": ["Obsidian", "BSC"],
        "constraints": ["solo delivery"],
    })

    engineering = service.compile_plan("engineering")
    growth = service.compile_plan("growth")

    assert engineering.compilation_state == "context_grounded"
    assert engineering.knowledge_context_refs == ["vault:03_Projects/active/delivery.md"]
    assert engineering.compiler_metadata["mode"] == "contextual_deterministic"
    assert engineering.phases[0]["title"] != growth.phases[0]["title"]
    assert any("contract" in action.lower() for phase in engineering.phases for action in phase["actions"])
    assert any("audience" in action.lower() or "retention" in action.lower() for phase in growth.phases for action in phase["actions"])
    assert any("Governed source available for review" in item for item in engineering.rationale)
    assert "Freeze contracts before platform expansion." not in engineering.model_dump_json()
    assert any("Review Current delivery (vault:03_Projects/active/delivery.md)" in action for phase in engineering.phases for action in phase["actions"])
    assert engineering.personalization_basis[0]["kind"] == "declared_profile"
    assert engineering.phases[0]["inputs"]
    assert engineering.phases[0]["outputs"]
    assert engineering.phases[0]["decision_point"]["question"]
    assert "side_effect_boundary" in engineering.execution_contract


def test_matching_strategy_genome_guides_the_next_plan_without_leaking_to_other_contexts(tmp_path):
    root = tmp_path / "vault"
    active = root / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text("# Delivery boundary\nShip a reviewable runtime slice before platform expansion.", encoding="utf-8")
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "matching", "Agent runtime delivery", "Deliver one verified Agent runtime slice")
    _mission(store, "other", "Content growth experiment", "Improve short-video retention for an AI product")
    matching = SOPVersionArtifact(
        artifact_id="strategy-matching",
        project_id="personal",
        strategy_name="AI project delivery",
        version=2,
        status=ArtifactStatus.ACTIVE,
        genome={
            "comparison_key": "engineering",
            "comparison_context": "engineering",
            "decision_rules": ["Freeze the API contract before implementation."],
            "execution_paths": ["Run the focused API contract tests."],
            "failure_boundaries": ["Stop after two unreviewable contract changes."],
            "success_metrics": ["One accepted contract test run."],
            "confidence": 0.83,
        },
    )
    unrelated = SOPVersionArtifact(
        artifact_id="strategy-unrelated",
        project_id="personal",
        strategy_name="Content growth",
        version=1,
        status=ArtifactStatus.ACTIVE,
        genome={
            "comparison_key": "growth",
            "comparison_context": "growth",
            "decision_rules": ["Use an audience retention experiment."],
        },
    )
    store.add(matching)
    store.add(unrelated)
    service = PBOSService(
        store,
        "personal",
        context_provider=PBOSVaultContextBuilder(root).build,
        plan_compiler=PBOSPlanCompiler(),
    )
    service.save_profile({"focus": ["AI systems"]})

    plan = service.compile_plan("matching")
    other = service.compile_plan("other")

    assert plan.compilation_state == "personalized"
    assert plan.strategy_refs == [matching.artifact_id]
    assert plan.compiler_metadata["active_strategy_assets"][0]["artifact_id"] == matching.artifact_id
    assert any(item["kind"] == "verified_strategy_genome" for item in plan.personalization_basis)
    assert any("Freeze the API contract" in action for phase in plan.phases for action in phase["actions"])
    assert any("Stop after two unreviewable contract changes" in check for phase in plan.phases for check in phase["checks"])
    assert other.strategy_refs == [unrelated.artifact_id]
    assert all(matching.artifact_id not in str(value) for value in other.model_dump().values())


def test_model_prompt_receives_only_the_matching_strategy_genome(tmp_path):
    class CapturingClient:
        provider = "test"
        model = "strategy-aware"

        def __init__(self):
            self.payload: dict = {}

        def chat_structured(self, **kwargs):
            self.payload = json.loads(kwargs["user_prompt"])
            return {
                "title": "Strategy-aware runtime plan",
                "phases": [
                    {"title": "Contract gate", "actions": ["Implement the bounded contract"]},
                    {"title": "Verification", "actions": ["Run the focused verification"]},
                    {"title": "Reflection", "actions": ["Record the reviewable result"]},
                ],
            }

    root = tmp_path / "vault"
    active = root / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text("# Delivery boundary\nKeep one reviewable runtime slice.", encoding="utf-8")
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "Agent runtime delivery", "Deliver one verified Agent runtime slice")
    strategy = SOPVersionArtifact(
        artifact_id="strategy-runtime",
        project_id="personal",
        strategy_name="AI project delivery",
        version=3,
        status=ArtifactStatus.ACTIVE,
        genome={
            "comparison_key": "engineering",
            "comparison_context": "engineering",
            "decision_rules": ["Freeze one public contract before coding."],
            "execution_paths": ["Run focused contract tests."],
          "failure_boundaries": ["Do not widen the public API before verification."],
          "success_metrics": ["A focused contract test passes."],
          "outcome_cases": [{"summary": "A bounded API slice passed focused review."}],
          "confidence": 0.88,
        },
    )
    store.add(strategy)
    client = CapturingClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=PBOSVaultContextBuilder(root).build,
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"focus": ["AI systems"]})

    plan = service.compile_plan("mission")

    assert client.payload["active_strategy_genomes"] == [{
        "artifact_id": "strategy-runtime",
        "strategy_name": "AI project delivery",
        "version": 3,
        "decision_rules": ["Freeze one public contract before coding."],
        "execution_paths": ["Run focused contract tests."],
        "failure_boundaries": ["Do not widen the public API before verification."],
        "success_metrics": ["A focused contract test passes."],
        "outcome_patterns": ["A bounded API slice passed focused review."],
        "confidence": 0.88,
    }]
    assert plan.strategy_refs == [strategy.artifact_id]
    assert any("Freeze one public contract" in action for phase in plan.phases for action in phase["actions"])


def test_structured_model_output_is_traceable_to_the_same_context(tmp_path):
    class StubClient:
        provider = "test"
        model = "contextual-test"
        last_structured_failure = ""

        def chat_structured(self, **_kwargs):
            return {
                "title": "Evidence-bound delivery system",
                "rationale": ["Use the active delivery boundary before expanding scope."],
                "phases": [
                    {"title": "Contract gate", "why_now": "A prior scope failure needs an early boundary.", "actions": ["Freeze the API contract"], "decision_point": {"question": "Is the contract bounded?", "proceed_when": "The owner accepts it.", "adapt_when": "Capture the missing constraint."}},
                    {"title": "Evidence loop", "why_now": "The bounded contract needs a verifiable result.", "actions": ["Run the focused tests"]},
                    {"title": "Review outcome", "why_now": "The result must inform the next decision.", "actions": ["Record the review receipt"]},
                ],
                "risks": ["Scope expansion before a verified receipt"],
                "success_criteria": ["One reviewable loop is complete"],
                "evidence_gap_plan": [],
            }

    root = tmp_path / "vault"
    active = root / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text("# Delivery boundary\nUse one visible proof.", encoding="utf-8")
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "Agent runtime delivery", "Deliver the verified runtime loop")
    service = PBOSService(
        store,
        "personal",
        context_provider=PBOSVaultContextBuilder(root).build,
        plan_compiler=PBOSPlanCompiler(client=StubClient()),
    )
    service.save_profile({"focus": ["AI systems"]})

    plan = service.compile_plan("mission")

    assert plan.title == "Evidence-bound delivery system"
    assert plan.compiler_metadata["mode"] == "llm_contextual"
    assert plan.compiler_metadata["provider"] == "test"
    assert plan.knowledge_context_refs == ["vault:03_Projects/active/delivery.md"]
    assert any("Mission intent:" in item for item in plan.rationale)
    assert any("Personal focus: AI systems" in item for item in plan.rationale)
    assert plan.phases[0]["why_now"] == "A prior scope failure needs an early boundary."
    assert plan.phases[0]["decision_point"]["adapt_when"] == "Capture the missing constraint."


def test_completed_evidence_mirror_replaces_repeated_projection_with_mission_action(tmp_path):
    class RepeatingProjectionClient:
        provider = "test"
        model = "repeat-projection"

        def __init__(self):
            self.prompts: list[dict] = []

        def chat_structured(self, **kwargs):
            self.prompts.append(json.loads(kwargs["user_prompt"]))
            return {
                "title": "Growth delivery system",
                "phases": [
                    {"title": "Source projection", "actions": ["Project BSC evidence into Obsidian"]},
                    {"title": "Experiment", "actions": ["Run the audience experiment"]},
                    {"title": "Reflection", "actions": ["Record the experiment outcome"]},
                ],
            }

    context = {
        "availability": "available",
        "documents": [{"ref": "vault:03_Projects/active/growth.md", "path": "03_Projects/active/growth.md", "title": "Growth brief", "excerpt": "Improve retention for the named audience."}],
        "refs": ["vault:03_Projects/active/growth.md"],
        "operational_state": {
            "source_lifecycle_counts": {"processed": 12},
            "managed_source_mirror": {"state": "available", "file_count": 12, "recorded_source_count": 12},
            "published_wiki": {"page_count": 3},
            "weekly_handoff": {"state": "available", "path": "distillations/weekly/next-context.md"},
        },
    }
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "growth", "Content growth experiment", "Improve short-video retention for an AI product")
    client = RepeatingProjectionClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: context,
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"focus": ["content growth"]})

    plan = service.compile_plan("growth")

    assert client.prompts[0]["operational_state"]["managed_source_mirror"]["state"] == "available"
    assert plan.phases[0]["title"] == "Audience and signal diagnosis"
    assert all("project bsc evidence into obsidian" not in action.casefold() for phase in plan.phases for action in phase["actions"])
    assert plan.compiler_metadata["completed_operation_guard"] == {
        "operation": "bsc_obsidian_evidence_projection",
        "replacement_phase_indexes": [1],
        "reason": "managed_source_mirror_available",
    }


def test_absent_mirror_does_not_hide_a_requested_projection_action(tmp_path):
    class RepeatingProjectionClient:
        provider = "test"
        model = "repeat-projection"

        def chat_structured(self, **_kwargs):
            return {
                "title": "Growth delivery system",
                "phases": [
                    {"title": "Source projection", "actions": ["Project BSC evidence into Obsidian"]},
                    {"title": "Experiment", "actions": ["Run the audience experiment"]},
                    {"title": "Reflection", "actions": ["Record the experiment outcome"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "growth", "Content growth experiment", "Improve short-video retention for an AI product")
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {
            "availability": "available",
            "documents": [],
            "refs": [],
            "operational_state": {"managed_source_mirror": {"state": "awaiting_projection"}},
        },
        plan_compiler=PBOSPlanCompiler(client=RepeatingProjectionClient()),
    )
    service.save_profile({"focus": ["content growth"]})

    plan = service.compile_plan("growth")

    assert plan.phases[0]["actions"] == ["Project BSC evidence into Obsidian"]
    assert "completed_operation_guard" not in plan.compiler_metadata


def test_configured_plugin_route_replaces_repeated_setup_with_mission_action(tmp_path):
    class RepeatingPluginSetupClient:
        provider = "test"
        model = "repeat-plugin-setup"

        def __init__(self):
            self.prompt: dict = {}
            self.system_prompt = ""

        def chat_structured(self, **kwargs):
            self.prompt = json.loads(kwargs["user_prompt"])
            self.system_prompt = kwargs["system_prompt"]
            return {
                "title": "Plugin-first delivery system",
                "phases": [
                    {"title": "Clipper setup", "actions": ["Configure Obsidian Clipper plugin"]},
                    {"title": "Implementation", "actions": ["Implement the delivery path"]},
                    {"title": "Reflection", "actions": ["Record the observed result"]},
                ],
            }

    context = {
        "availability": "available",
        "documents": [{
            "ref": "vault:03_Projects/active/delivery.md",
            "path": "03_Projects/active/delivery.md",
            "title": "Delivery brief",
            "excerpt": "Deliver one bounded engineering result.",
        }],
        "refs": ["vault:03_Projects/active/delivery.md"],
        "operational_state": {
            "plugin_bridges": {
                "ready_route_count": 1,
                "routes": [{
                    "id": "obsidian-clipper",
                    "adapter": "filesystem_drop",
                    "route_state": "configured_awaiting_export",
                    "capture_state": "ready_for_first_export",
                }],
            },
        },
    }
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "engineering", "Agent runtime delivery", "Deliver one verified Agent runtime slice")
    client = RepeatingPluginSetupClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: context,
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"focus": ["AI systems"]})

    plan = service.compile_plan("engineering")

    assert client.prompt["operational_state"]["plugin_bridges"]["ready_route_count"] == 1
    assert client.prompt["operational_state"]["plugin_bridges"]["routes"] == [{
        "id": "obsidian-clipper",
        "adapter": "filesystem_drop",
        "route_state": "configured_awaiting_export",
        "capture_state": "ready_for_first_export",
    }]
    assert "never install, configure, or reconfigure" in client.system_prompt
    assert plan.phases[0]["title"] == "Architecture and boundary gate"
    assert all("configure obsidian clipper" not in action.casefold() for phase in plan.phases for action in phase["actions"])
    assert plan.compiler_metadata["plugin_bridge_guard"] == {
        "operation": "obsidian_plugin_setup",
        "route_ids": ["obsidian-clipper"],
        "replacement_phase_indexes": [1],
        "reason": "configured_route_awaiting_real_export",
    }


def test_knowledge_delivery_uses_project_specific_fallback_when_source_projection_is_blocked(tmp_path):
    class RepeatingProjectionClient:
        provider = "test"
        model = "repeat-projection"

        def chat_structured(self, **_kwargs):
            return {
                "title": "Knowledge delivery system",
                "phases": [
                    {"title": "Projection", "actions": ["Mirror BSC sources into the Obsidian Vault"]},
                    {"title": "SOP", "actions": ["Write a generic content experiment"]},
                    {"title": "Review", "actions": ["Record a result"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(
        store,
        "knowledge-delivery",
        "Governed LLM Wiki delivery",
        "Turn Horizon evidence and Obsidian Wiki context into a custom PRD-to-SOP delivery loop.",
    )
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {
            "availability": "available",
            "documents": [],
            "refs": [],
            "operational_state": {
                "managed_source_mirror": {"state": "available", "file_count": 1, "recorded_source_count": 1},
            },
        },
        plan_compiler=PBOSPlanCompiler(client=RepeatingProjectionClient()),
    )
    service.save_profile({"focus": ["knowledge delivery"], "preferences": {"language": "en-US"}})

    plan = service.compile_plan("knowledge-delivery")

    assert plan.compiler_metadata["task_kind"] == "knowledge_delivery"
    assert plan.compiler_metadata["completed_operation_guard"]["replacement_phase_indexes"] == [1]
    assert plan.compiler_metadata["domain_specificity_guard"] == {
        "task_kind": "knowledge_delivery",
        "replacement_phase_indexes": [2, 3],
        "reason": "unrelated_growth_template",
    }
    assert plan.phases[0]["title"] == "Evidence triage and boundary"
    assert "content experiment" not in " ".join(
        action.casefold() for phase in plan.phases for action in phase["actions"]
    )


def test_knowledge_delivery_localizes_the_fallback_from_a_chinese_profile(tmp_path):
    class EnglishClient:
        provider = "test"
        model = "english-output"

        def __init__(self):
            self.prompt: dict = {}

        def chat_structured(self, **kwargs):
            self.prompt = json.loads(kwargs["user_prompt"])
            return {
                "title": "Knowledge delivery system",
                "phases": [
                    {"title": "Triage", "actions": ["Review source evidence"]},
                    {"title": "SOP", "actions": ["Create a custom SOP"]},
                    {"title": "Review", "actions": ["Record a result"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(
        store,
        "knowledge-delivery-zh",
        "Governed LLM Wiki delivery",
        "Turn Horizon evidence and Obsidian Wiki context into a custom PRD-to-SOP delivery loop.",
    )
    client = EnglishClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "available", "documents": [], "refs": []},
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"preferences": {"language": "zh-CN"}})

    plan = service.compile_plan("knowledge-delivery-zh")

    assert plan.compiler_metadata["response_language"] == "Chinese"
    assert client.prompt["response_language"] == "Chinese"
    assert "PRD" in plan.phases[1]["actions"][0]
    assert all(
        any("\u4e00" <= character <= "\u9fff" for character in action)
        for phase in plan.phases
        for action in phase["actions"]
    )


def test_chinese_mission_replaces_complete_english_llm_actions_with_localized_mission_actions(tmp_path):
    class EnglishClient:
        provider = "test"
        model = "english-output"

        def __init__(self):
            self.prompt: dict = {}

        def chat_structured(self, **kwargs):
            self.prompt = json.loads(kwargs["user_prompt"])
            return {
                "title": "Content delivery system",
                "phases": [
                    {"title": "Metric selection", "actions": ["Select a primary engagement metric from the dashboard"]},
                    {"title": "Experiment design", "actions": ["Create two content variants with one changed variable"]},
                    {"title": "Review", "actions": ["Record the outcome and decide the next experiment"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "growth", "新媒体运营", "提升短视频完播率")
    client = EnglishClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "available", "documents": [], "refs": []},
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"focus": ["内容增长"]})

    plan = service.compile_plan("growth")

    assert client.prompt["response_language"] == "Chinese"
    assert all(
        any("\u4e00" <= character <= "\u9fff" for character in action)
        for phase in plan.phases
        for action in phase["actions"]
    )
    assert plan.compiler_metadata["language_guard"]["mission_language"] == "zh"
    assert plan.compiler_metadata["language_guard"]["replacement_phases"] == [
        {"phase_index": 1, "action_count": 1},
        {"phase_index": 2, "action_count": 1},
        {"phase_index": 3, "action_count": 1},
    ]


def test_chinese_mission_localizes_the_deterministic_completed_projection_replacement(tmp_path):
    class RepeatingProjectionClient:
        provider = "test"
        model = "repeat-projection"

        def chat_structured(self, **_kwargs):
            return {
                "title": "内容执行计划",
                "phases": [
                    {"title": "Source projection", "actions": ["Project BSC evidence into Obsidian"]},
                    {"title": "实验", "actions": ["设计一个内容变量实验"]},
                    {"title": "复盘", "actions": ["记录结果并决定下一次实验"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "growth", "新媒体运营", "提升短视频完播率")
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {
            "availability": "available",
            "documents": [],
            "refs": [],
            "operational_state": {
                "managed_source_mirror": {"state": "available", "file_count": 1, "recorded_source_count": 1},
            },
        },
        plan_compiler=PBOSPlanCompiler(client=RepeatingProjectionClient()),
    )
    service.save_profile({"focus": ["内容增长"]})

    plan = service.compile_plan("growth")

    assert plan.compiler_metadata["completed_operation_guard"]["replacement_phase_indexes"] == [1]
    assert plan.compiler_metadata["language_guard"]["replacement_phases"][0]["phase_index"] == 1
    assert all(any("\u4e00" <= character <= "\u9fff" for character in action) for action in plan.phases[0]["actions"])


def test_compiler_replaces_verbatim_vault_echoes_with_traceable_references(tmp_path):
    raw_source_line = "Do not expose this confidential raw Vault sentence in a persisted plan."

    class EchoingClient:
        provider = "test"
        model = "echoing-test"

        def chat_structured(self, **_kwargs):
            return {
                "title": "Evidence-bound delivery system",
                "rationale": [raw_source_line],
                "phases": [
                    {
                        "title": "Boundary gate",
                        "why_now": raw_source_line,
                        "inputs": [raw_source_line],
                        "actions": [f"Follow this source exactly: {raw_source_line}"],
                        "outputs": [raw_source_line],
                        "checks": [raw_source_line],
                        "decision_point": {
                            "question": raw_source_line,
                            "proceed_when": raw_source_line,
                            "adapt_when": raw_source_line,
                        },
                    },
                    {"title": "Verify boundary", "why_now": "A bounded result needs a receipt.", "actions": ["Run the focused proof"]},
                    {"title": "Record learning", "why_now": "The next action needs observed feedback.", "actions": ["Record the reflection"]},
                ],
                "risks": [raw_source_line],
                "success_criteria": [raw_source_line],
                "evidence_gap_plan": [raw_source_line],
            }

    root = tmp_path / "vault"
    active = root / "03_Projects" / "active"
    active.mkdir(parents=True)
    (active / "delivery.md").write_text(f"# Delivery boundary\n{raw_source_line}", encoding="utf-8")
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "Agent runtime delivery", "Deliver the verified runtime loop")
    service = PBOSService(
        store,
        "personal",
        context_provider=PBOSVaultContextBuilder(root).build,
        plan_compiler=PBOSPlanCompiler(client=EchoingClient()),
    )
    service.save_profile({"focus": ["AI systems"]})

    plan = service.compile_plan("mission")

    assert raw_source_line not in plan.model_dump_json()
    assert plan.compiler_metadata["mode"] == "llm_contextual"
    assert "vault:03_Projects/active/delivery.md" in plan.phases[0]["actions"][0]
    assert plan.phases[0]["decision_point"]["question"] == "Is the cited evidence sufficient for the next bounded decision?"


def test_compiler_bounds_llm_context_and_preserves_execution_contracts(tmp_path):
    class CapturingClient:
        provider = "test"
        model = "fast-structured-test"
        last_structured_failure = ""
        last_response_shape = {"finish_reason": "stop", "private_reasoning_present": False}
        last_structured_attempts = [
            {"attempt": 1, "json_mode": True, "max_tokens": 1000, "result": "valid_json"}
        ]

        def chat_structured(self, **kwargs):
            self.kwargs = kwargs
            return {
                "title": "Receipt-first research intake",
                "phases": [
                    {"title": "Source gate", "actions": ["Approve one source"]},
                    {"title": "Receipt loop", "actions": ["Run one signed batch"]},
                    {"title": "Review decision", "actions": ["Inspect the receipt"]},
                ],
            }

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "Research intake", "Deliver one governed information loop")
    documents = [
        {
            "ref": f"wiki:policy-{index}",
            "title": f"Policy {index}",
            "path": f"wiki/policy-{index}.md",
            "excerpt": "Source policy evidence. " * 100,
        }
        for index in range(6)
    ]
    client = CapturingClient()
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "available", "documents": documents, "refs": []},
        plan_compiler=PBOSPlanCompiler(client=client),
    )
    service.save_profile({"focus": ["knowledge operations"], "constraints": ["no automatic publication"]})

    plan = service.compile_plan("mission")
    payload = json.loads(client.kwargs["user_prompt"])
    usage = plan.compiler_metadata["llm_prompt_context"]

    assert client.kwargs["max_tokens"] == settings.PBOS_LLM_MAX_OUTPUT_TOKENS
    assert client.kwargs["max_structured_attempts"] == settings.PBOS_LLM_MAX_STRUCTURED_ATTEMPTS
    assert len(payload["vault_context"]) == settings.PBOS_LLM_MAX_CONTEXT_DOCUMENTS
    assert usage["documents_available"] == 6
    assert usage["documents_included"] == 4
    assert usage["documents_omitted"] == 2
    assert usage["estimated_input_tokens"] > 0
    assert plan.compiler_metadata["mode"] == "llm_contextual"
    assert plan.compiler_metadata["llm_attempts"] == client.last_structured_attempts
    assert plan.compiler_metadata["llm_response_shape"]["finish_reason"] == "stop"
    assert plan.phases[0]["title"] == "Source gate"
    assert plan.phases[0]["why_now"]
    assert plan.phases[0]["inputs"]
    assert plan.phases[0]["outputs"]
    assert plan.phases[0]["checks"]
    assert "side_effect_boundary" in plan.execution_contract


def test_structured_model_fallback_records_safe_shape_and_attempts(tmp_path):
    class InvalidClient:
        provider = "test"
        model = "contextual-test"
        last_structured_failure = "response_truncated"
        last_response_shape = {
            "payload_type": "dict",
            "finish_reason": "length",
            "private_reasoning_present": True,
        }
        last_structured_attempts = [
            {"attempt": 1, "json_mode": True, "max_tokens": 1000, "result": "response_truncated"},
        ]

        def chat_structured(self, **_kwargs):
            return None

    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "Agent runtime delivery", "Deliver the verified runtime loop")
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "unavailable", "documents": [], "refs": []},
        plan_compiler=PBOSPlanCompiler(client=InvalidClient()),
    )

    plan = service.compile_plan("mission")

    assert plan.compiler_metadata["llm_failure"] == "response_truncated"
    assert plan.compiler_metadata["llm_response_shape"] == {
        "payload_type": "dict",
        "finish_reason": "length",
        "private_reasoning_present": True,
    }
    assert plan.compiler_metadata["llm_attempts"] == [
        {"attempt": 1, "json_mode": True, "max_tokens": 1000, "result": "response_truncated"}
    ]


def test_diagnosis_defines_the_personal_comparison_context(tmp_path):
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "AI delivery", "Deliver an evidence-backed AI feature")
    diagnosis = DiagnosisArtifact(
        artifact_id="diagnosis",
        project_id="personal",
        mission_id="mission",
        role="AI product lead",
        industry="SaaS",
        organization_stage="scale-up",
        goal="Ship a verified AI feature",
        constraints=["Solo delivery"],
    )
    store.add(diagnosis)
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "available", "documents": [], "refs": []},
    )
    service.save_profile({"focus": ["AI systems"], "constraints": ["Limited time"]})

    plan = service.compile_plan("mission", diagnosis.artifact_id)

    assert plan.diagnosis_id == diagnosis.artifact_id
    assert plan.comparison_key == "engineering:ai-product-lead:saas:scale-up"
    assert plan.comparison_context == "AI product lead / SaaS / scale-up"
    assert plan.personal_context_fingerprint
    assert plan.compiler_metadata["diagnosis_context"]["industry"] == "SaaS"


def test_declared_personal_profile_context_makes_an_empty_diagnosis_specific_without_claiming_evidence(tmp_path):
    store = ArtifactGraphStore(str(tmp_path / "ledger"), project_id="personal")
    _mission(store, "mission", "AI delivery", "Deliver an evidence-backed AI feature")
    service = PBOSService(
        store,
        "personal",
        context_provider=lambda: {"availability": "available", "documents": [], "refs": []},
    )
    service.save_profile({
        "role": "Independent AI product builder",
        "industry": "AI productivity software",
        "organization_stage": "solo validation",
        "focus": ["AI systems"],
        "goals": ["Ship one reviewable AI feature"],
        "work_style": ["architecture first"],
        "decision_style": ["evidence before expansion"],
    })

    plan = service.compile_plan("mission")

    assert plan.comparison_key == "engineering:independent-ai-product-builder:ai-productivity-software:solo-validation"
    assert plan.comparison_context == "Independent AI product builder / AI productivity software / solo validation"
    assert plan.compiler_metadata["effective_personal_context"]["role"] == "Independent AI product builder"
    assert plan.compiler_metadata["effective_personal_context_sources"]["role"] == "declared_profile"
    assert plan.compilation_state == "capture_required"
    assert not plan.strategy_refs
