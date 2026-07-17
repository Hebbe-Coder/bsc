from app.orchestrator.agents.risk_architect import RiskArchitectAgent


class FakeLLM:
    def chat(self, system_prompt, user_prompt, temperature=0.1, max_tokens=None, use_cache=True):
        return {"risk": {"overall_score": "medium",
                          "risks": [{"id": "rk1", "category": "compliance",
                                     "description": "缺合规", "likelihood": "low",
                                     "impact": "medium", "mitigation": "补审计",
                                     "owner_role": "法务"}]}}


def test_risk_agent_produces_risk_segment():
    bm = {"flows": [{"id": "r1", "name": "受理"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "受理约束", "priority": "mid"}]
    agent = RiskArchitectAgent(llm_service=FakeLLM())
    out = agent.run(business_model=bm, requirements=reqs)
    assert "risk" in out
    assert out["risk"]["overall_score"] == "medium"
    assert out["risk"]["coverage"]["coverage_pct"] == 100  # r1 覆盖该 flow（id 匹配）
    assert out["risk"]["gate"]["decision"] in ("pass", "warn", "block")
    assert out["risk"]["audit"]  # 审计链已随段落库
    # LLM 产出的风险清单必须随 risk 段落地，不能被 evaluate 丢弃
    assert out["risk"]["risks"], "risk 段不应丢失 LLM 风险清单"
    assert out["risk"]["risks"][0]["id"] == "rk1"
