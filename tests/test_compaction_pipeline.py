import app.core.compaction_pipeline as compaction


ContextManager = compaction.ContextManager


def test_token_estimate_accounts_for_utf8_width():
    assert compaction.estimate_tokens("业务流程") > compaction.estimate_tokens("flow")
    assert compaction.estimate_tokens("") == 0


def test_context_reports_compaction_that_just_happened():
    manager = ContextManager(
        max_chars=160,
        compaction_threshold_pct=0.5,
        keep_last_n_agents=1,
    )
    manager.add_agent_result("planner", {"detail": "A" * 80})
    manager.add_agent_result("architect", {"detail": "B" * 80})

    context = manager.get_context_for_next_agent("reviewer")

    assert context["compacted"] is True
    assert context["compaction_count"] == 1
    assert context["tokens_before"] > context["estimated_tokens"]
    assert all(
        "agent" in entry and "result" in entry
        for entry in context["agent_results"]
    )


def test_context_stats_preserve_compaction_savings():
    manager = ContextManager(
        max_chars=160,
        compaction_threshold_pct=0.5,
        keep_last_n_agents=1,
    )
    manager.add_agent_result("planner", {"detail": "A" * 80})
    manager.add_agent_result("architect", {"detail": "B" * 80})
    manager.get_context_for_next_agent("reviewer")

    stats = manager.get_stats()

    assert stats["compaction_count"] == 1
    assert stats["tokens_saved"] > 0
    assert stats["estimated_tokens"] < stats["peak_tokens"]
