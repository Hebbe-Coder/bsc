from app.core.context_policy import ContextItem, ContextManager, ContextPolicy


def test_fresh_keeps_current_input_without_inherited_prompt_wrapper():
    packet = ContextManager(max_tokens=256).build(
        "  preserve this request  ",
        policy=ContextPolicy.FRESH,
        inherited_items=[ContextItem(role="user", content="parent secret")],
    )

    assert packet.rendered_input == "  preserve this request  "
    assert packet.usage.inherited_items == 0
    assert packet.usage.included_items == 0


def test_fork_is_bounded_and_keeps_current_request_last():
    packet = ContextManager(max_tokens=256, max_verbatim_items=1).build(
        "new request",
        policy=ContextPolicy.FORK,
        inherited_items=[
            ContextItem(role="user", content="older context", priority=10),
            ContextItem(role="runtime", content="important context", priority=90),
        ],
    )

    assert packet.rendered_input.endswith("[current request]\nnew request")
    assert packet.usage.inherited_items == 2
    assert packet.usage.included_items == 1
    assert packet.usage.summarized_items == 1
    assert packet.usage.estimated_tokens <= packet.usage.max_tokens


def test_resume_requires_a_source_session():
    try:
        ContextManager().build("continue", policy=ContextPolicy.RESUME)
    except ValueError as exc:
        assert "source session" in str(exc)
    else:
        raise AssertionError("resume without source must fail closed")


def test_fresh_keeps_project_knowledge_as_persistent_context():
    packet = ContextManager(max_tokens=256).build(
        "Create a project-specific SOP",
        policy=ContextPolicy.FRESH,
        persistent_items=[ContextItem(
            role="project_knowledge",
            content="The audience rejects generic templates and requires a Friday evidence review.",
            priority=100,
        )],
    )

    assert "[persistent project context]" in packet.rendered_input
    assert "Friday evidence review" in packet.rendered_input
    assert packet.rendered_input.endswith("[current request]\nCreate a project-specific SOP")
    assert packet.usage.persistent_items == 1
    assert packet.usage.persistent_included == 1


def test_fork_and_resume_keep_project_knowledge_outside_chat_history():
    for policy in (ContextPolicy.FORK, ContextPolicy.RESUME):
        packet = ContextManager(max_tokens=256).build(
            "Produce the next project-specific SOP",
            policy=policy,
            inherited_items=[ContextItem(role="session", content="prior user decision")],
            persistent_items=[ContextItem(
                role="project_knowledge",
                content="Publishing requires the project's Friday evidence review.",
                priority=100,
            )],
        )

        assert "[persistent project context]" in packet.rendered_input
        assert "Friday evidence review" in packet.rendered_input
        assert "[inherited context]" in packet.rendered_input
        assert packet.rendered_input.endswith(
            "[current request]\nProduce the next project-specific SOP"
        )
        assert packet.usage.persistent_items == 1
        assert packet.usage.persistent_included == 1


def test_context_manifest_tracks_compacted_segments_without_exposing_content():
    older_secret = "Older draft detail that must not be copied into an audit record."
    packet = ContextManager(max_tokens=96, max_verbatim_items=1).build(
        "Create a tailored follow-up SOP",
        policy=ContextPolicy.RESUME,
        inherited_items=[
            ContextItem(
                role="user",
                content=older_secret,
                source_session_id="parent-session",
                priority=10,
            ),
            ContextItem(
                role="runtime",
                content="The release gate requires evidence review before publishing.",
                source_session_id="parent-session",
                priority=90,
            ),
        ],
    )

    manifest = packet.manifest.model_dump_json()
    assert packet.usage.manifest_id == packet.manifest.manifest_id
    assert packet.manifest.source_session_ids == ["parent-session"]
    assert packet.usage.recoverable_source_sessions == ["parent-session"]
    assert "parent-session" in manifest
    assert older_secret not in manifest
    assert any(item.disposition == "included" for item in packet.manifest.inherited)
    assert any(item.disposition in {"summarized", "omitted"} for item in packet.manifest.inherited)


def test_context_manifest_is_stable_for_an_identical_context_composition():
    kwargs = {
        "input_text": "Prepare a project-specific operating routine.",
        "policy": ContextPolicy.FORK,
        "inherited_items": [ContextItem(
            role="runtime",
            content="The project requires a Friday source review.",
            source_session_id="session-7",
            priority=80,
        )],
    }

    first = ContextManager(max_tokens=256).build(**kwargs)
    second = ContextManager(max_tokens=256).build(**kwargs)

    assert first.manifest.manifest_id == second.manifest.manifest_id
    assert first.manifest.current_input_fingerprint == second.manifest.current_input_fingerprint
