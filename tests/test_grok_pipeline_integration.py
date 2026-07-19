from app.agents.unified_agent import AgentResult
from app.core.bsc_pipeline import BSCPipeline
from app.enums import PipelineStage


def test_parallel_pipeline_retries_failed_agent_results(monkeypatch):
    attempts = 0

    def flaky_run(self, agent_key, ctx):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return AgentResult(
                data={},
                status="failed",
                error="temporary provider failure",
                agent_name="SOP Agent",
            )
        return AgentResult(
            data={"sop": {"steps": ["done"]}},
            status="completed",
            agent_name="SOP Agent",
        )

    monkeypatch.setattr(
        "app.agents.unified_agent.AgentExecutionContext.run_agent",
        flaky_run,
    )
    monkeypatch.setattr("app.core.agent_pool.time.sleep", lambda _: None)

    pipeline = BSCPipeline(llm_service=object())
    result = pipeline._execute_parallel_with_keys(
        [PipelineStage.SOP],
        chunks=[{"content": "test PRD"}],
        context={"business_understanding": {}},
        prd_content="test PRD",
    )

    assert attempts == 3
    assert result[PipelineStage.SOP]["stage"]["status"] == "success"
    assert result[PipelineStage.SOP]["result"]["sop"]["steps"] == ["done"]
