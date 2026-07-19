import sys, asyncio, json
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.core.config import settings
print(f"Provider: {settings.LLM_PROVIDER}")
print(f"API Key: {settings.DEEPSEEK_API_KEY[:15]}...")
print(f"Model: {settings.DEEPSEEK_MODEL}")
print(f"Base URL: {settings.DEEPSEEK_BASE_URL}")

from app.services.llm_service import LLMService
svc = LLMService(provider="deepseek", force_mock=False)
print(f"Service provider: {svc.provider}")
print(f"Service model: {svc.model}")
print(f"Service api_key: {svc.api_key[:15] if svc.api_key else 'EMPTY'}...")

# Try direct chat
result = svc.chat(
    system_prompt="你是一个商业分析专家。",
    user_prompt="用一句话说：什么是商业模式？",
    max_tokens=100,
)
print(f"Result type: {type(result)}")
print(f"Result: {str(result)[:300]}")
