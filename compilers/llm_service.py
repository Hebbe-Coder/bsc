"""LLM Service - JSON mode with configurable retries."""
import json as _json, time as _time
from openai import OpenAI

_client = None
MAX_REPAIR_RETRIES = 3

def _get_client():
    global _client
    if _client is None:
        try:
            from app.core.config import settings
            api_key = settings.DEEPSEEK_API_KEY or settings.DOUBAO_API_KEY or settings.YUANBAO_API_KEY
            base_url = settings.DEEPSEEK_BASE_URL
            provider = settings.LLM_PROVIDER
            
            if provider == "doubao":
                api_key = settings.DOUBAO_API_KEY
                base_url = settings.DOUBAO_BASE_URL
            elif provider == "yuanbao":
                api_key = settings.YUANBAO_API_KEY
                base_url = settings.YUANBAO_BASE_URL
            
            _client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )
        except ImportError:
            import os as _os
            _client = OpenAI(
                api_key=_os.environ.get("OPENAI_API_KEY"),
                base_url=_os.environ.get("OPENAI_BASE_URL")
            )
    return _client

def chat_json(system_prompt: str, user_message: str,
              model: str = "gpt-4o", temperature: float = 0.1,
              max_retries: int = MAX_REPAIR_RETRIES) -> dict:
    """LLM -> JSON with repair: if output is invalid JSON, retry with error context."""
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            kwargs = {
                "model": model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            }
            if last_error:
                kwargs["messages"].append({
                    "role": "user",
                    "content": "Your previous output was invalid JSON. Error: " + last_error + ". Please output ONLY valid JSON matching the exact schema."
                })
            resp = _get_client().chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"): raw = raw[4:]
            return _json.loads(raw.strip())
        except _json.JSONDecodeError as e:
            last_error = str(e)
            if attempt < max_retries:
                _time.sleep(0.3 * (attempt + 1))
        except Exception as e:
            return {"error": str(e)[:300], "fallback": True}
    return {"error": "JSON repair failed after " + str(max_retries) + " retries: " + last_error, "fallback": True}
