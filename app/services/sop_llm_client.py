"""SOP 汇报专用轻量 LLM 客户端(OpenAI 兼容,多厂商)。

支持 deepseek / doubao / qwen / kimi 等 OpenAI 兼容端点。
默认 mock 模式离线可用;配置对应 provider 的 API Key 后自动走真实模型。
复用 app.core.config 中已有的 DEEPSEEK_*/DOUBAO_*/QWEN_* 配置,kimi 为新增。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


PROVIDER_REGISTRY: Dict[str, Dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-pro-32k"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
}

# provider -> (api_key 配置项, base_url 配置项, model 配置项)
PROVIDER_KEY_MAP = {
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
    "doubao": ("DOUBAO_API_KEY", "DOUBAO_BASE_URL", "DOUBAO_MODEL"),
    "qwen": ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL"),
}


class SOPLLMError(Exception):
    """LLM 调用失败(网络/HTTP/超时),由调用方决定兜底。"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_json(content: str) -> Optional[dict]:
    """尽力解析 JSON:去围栏 → 直接 loads → 抽取首个 {..}。失败返回 None。"""
    if not content:
        return None
    try:
        return json.loads(_strip_code_fence(content))
    except (json.JSONDecodeError, ValueError):
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return None


class SOPLLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ):
        self.provider = (provider or settings.SOP_LLM_PROVIDER or "mock").lower()
        self.timeout = timeout
        self._http = http_client

        if self.provider == "mock":
            self.base_url = ""
            self.model = "mock"
            self.api_key = ""
            return

        if self.provider not in PROVIDER_REGISTRY:
            raise SOPLLMError(f"未知 SOP LLM provider: {self.provider}")
        key_attr, url_attr, model_attr = PROVIDER_KEY_MAP[self.provider]
        reg = PROVIDER_REGISTRY[self.provider]
        self.base_url = (base_url or getattr(settings, url_attr) or reg["base_url"]).rstrip("/")
        self.model = model or getattr(settings, model_attr) or reg["model"]
        self.api_key = api_key if api_key is not None else getattr(settings, key_attr, "")
        if not self.api_key:
            raise SOPLLMError(f"provider={self.provider} 需要配置 {key_attr}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        use_json_mode: bool = True,
    ) -> Dict[str, Any]:
        """返回 {"content": <str>}。mock 模式返回内置有效 JSON 字符串。"""
        if self.provider == "mock":
            return {"content": self._mock_content(system_prompt)}

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if use_json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            client = self._http or httpx.Client(timeout=self.timeout)
            try:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return {"content": data["choices"][0]["message"]["content"]}
            finally:
                if self._http is None:
                    client.close()
        except httpx.HTTPError as e:
            raise SOPLLMError(f"LLM 请求失败: {e}") from e

    def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> Optional[dict]:
        """返回解析后的 dict,或 None(调用方走兜底)。内置一次降温度重试。"""
        if self.provider == "mock":
            try:
                return json.loads(self._mock_content(system_prompt))
            except (json.JSONDecodeError, ValueError):
                return None
        for t in (temperature, temperature * 0.5):
            try:
                raw = self.chat(system_prompt, user_prompt, temperature=t, max_tokens=max_tokens)
                parsed = _parse_json(raw.get("content", ""))
                if parsed is not None:
                    return parsed
            except (SOPLLMError, KeyError) as e:
                logger.warning("SOP LLM 解析失败(retry): %s", e)
        logger.warning("SOP LLM 结构化解析最终失败,返回 None")
        return None

    def _mock_content(self, system_prompt: str) -> str:
        if "优化建议" in system_prompt or "recommend" in system_prompt.lower():
            return json.dumps(
                {
                    "optimization_suggestions": [
                        {
                            "id": "opt_001",
                            "title": "（离线mock）流程自动化",
                            "description": "针对重复性步骤引入自动化工具",
                            "priority": "高",
                            "estimated_impact": "节省人力成本",
                            "implementation_steps": ["识别步骤", "选工具", "实施"],
                        }
                    ],
                    "prioritized_actions": [{"action": "（离线mock）实施自动化", "timeline": "1-2个月"}],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "executive_summary": "（离线mock）基于结构化数据生成的执行摘要。",
                "key_findings": ["（离线mock）流程设计完整", "（离线mock）已设定 SLA 目标"],
                "recommendations": ["（离线mock）定期回顾流程", "（离线mock）加强风险监控"],
                "risk_highlights": ["（离线mock）部分步骤存在潜在风险"],
            },
            ensure_ascii=False,
        )
