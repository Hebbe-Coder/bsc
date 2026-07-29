from app.artifacts import ArtifactGraphStore, DiagnosisArtifact, MissionArtifact
from app.pbos.context import PBOSVaultContextBuilder
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


def test_vault_context_prioritizes_governed_methods_and_skips_drawing_exports(tmp_path):
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

    assert [item["path"] for item in context["documents"]][:3] == [
        "03_Projects/active/boundary.md",
        "methods/delivery-loop/SKILL.md",
        "wiki/concepts/evidence.md",
    ]
    assert not any("excalidraw" in item["path"] for item in context["documents"])
    assert "title: Boundary" not in context["documents"][0]["excerpt"]


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
    assert any("Governed context signal" in item for item in engineering.rationale)


def test_structured_model_output_is_traceable_to_the_same_context(tmp_path):
    class StubClient:
        provider = "test"
        model = "contextual-test"
        last_structured_failure = ""

        def chat_structured(self, **_kwargs):
            return {
                "title": "Evidence-bound delivery system",
                "rationale": ["Use the active delivery boundary before expanding scope."],
                "phases": [{"title": "Contract gate", "actions": ["Freeze the API contract"], "checks": ["Run the focused tests"]}],
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
            {"attempt": 1, "json_mode": True, "max_tokens": 2600, "result": "response_truncated"},
            {"attempt": 2, "json_mode": True, "max_tokens": 5200, "result": "response_truncated"},
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
    assert plan.compiler_metadata["llm_attempts"][1]["max_tokens"] == 5200


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
