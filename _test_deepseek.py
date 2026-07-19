import sys, json
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")
from app.services.llm_service import LLMService

svc = LLMService(provider="deepseek", force_mock=False)
print(f"Provider: {svc.provider}, Model: {svc.model}")

system = "你是 CEO Agent，负责从战略高度审视商业方案。"
user = """
{artifacts}

输出 JSON:
{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "strategic_analysis": "核心判断"
}
"""
result = svc.chat(system_prompt=system, user_prompt=user, max_tokens=300)
print(f"Result keys: {list(result.keys())}")
print(f"Content: {result.get('content', 'NO CONTENT')[:500]}")
print(f"Meta: {result.get('_meta', {})}")
