from app.api.orchestrate import build_agents
from app.services.llm_service import LLMService


def test_build_agents_includes_risk():
    agents = build_agents(LLMService())
    assert "risk" in agents
    assert agents["risk"].__class__.__name__ == "RiskArchitectAgent"
