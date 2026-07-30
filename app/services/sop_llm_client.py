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
from app.core.llm_policy import ensure_mock_allowed
from app.core.llm_usage import ModelUsage, extract_model_usage

logger = logging.getLogger(__name__)


PROVIDER_REGISTRY: Dict[str, Dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash"},
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
    """LLM request failure with a safe category for callers and run manifests."""

    def __init__(self, message: str, *, category: str = "request_failed") -> None:
        super().__init__(message)
        self.category = category


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


def _message_content(message: Any) -> str:
    """Normalize OpenAI-compatible string and segmented text message payloads."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "value", "content"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return ""
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
            continue
        if isinstance(text, dict):
            value = text.get("value") or text.get("content")
            if isinstance(value, str):
                parts.append(value)
                continue
        value = item.get("content")
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts)


def _choice_content(choice: Any) -> str:
    """Read documented chat and legacy completion text fields, never reasoning."""
    if not isinstance(choice, dict):
        return ""
    content = _message_content(choice.get("message"))
    if content:
        return content
    # A few OpenAI-compatible proxies still emit the legacy completion shape.
    text = choice.get("text")
    return text if isinstance(text, str) else ""


def _response_shape(data: Any) -> dict[str, Any]:
    """Describe an incompatible completion without retaining provider content."""
    shape: dict[str, Any] = {"payload_type": type(data).__name__}
    if not isinstance(data, dict):
        return shape
    shape["payload_keys"] = sorted(str(key) for key in data.keys())[:32]
    choices = data.get("choices")
    shape["choices_type"] = type(choices).__name__
    if not isinstance(choices, list) or not choices:
        return shape
    first_choice = choices[0]
    shape["choice_type"] = type(first_choice).__name__
    if not isinstance(first_choice, dict):
        return shape
    shape["choice_keys"] = sorted(str(key) for key in first_choice.keys())[:32]
    finish_reason = first_choice.get("finish_reason")
    if isinstance(finish_reason, str):
        shape["finish_reason"] = finish_reason
    message = first_choice.get("message")
    shape["message_type"] = type(message).__name__
    if not isinstance(message, dict):
        shape["legacy_text_type"] = type(first_choice.get("text")).__name__
        return shape
    shape["message_keys"] = sorted(str(key) for key in message.keys())[:32]
    shape["content_type"] = type(message.get("content")).__name__
    # Presence flags are safe operational diagnostics. They deliberately do
    # not retain response text, tool arguments, or private reasoning.
    shape["private_reasoning_present"] = "reasoning_content" in message
    shape["refusal_present"] = "refusal" in message
    shape["tool_calls_present"] = "tool_calls" in message
    return shape


def _response_format_rejected(response: httpx.Response) -> bool:
    """Detect a JSON-mode-only rejection without exposing provider response text."""
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error", payload) if isinstance(payload, dict) else ""
    if isinstance(error, dict):
        error = error.get("message", "")
    if not isinstance(error, str):
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in ("response_format", "json_object", "json mode"))


def _request_rejection_category(response: Any) -> str:
    """Classify provider 4xx errors without retaining or exposing their text."""
    if not isinstance(response, httpx.Response):
        return "request_rejected"
    if _response_format_rejected(response):
        return "response_format_rejected"
    try:
        payload = response.json()
    except ValueError:
        return "request_rejected"
    error = payload.get("error", payload) if isinstance(payload, dict) else ""
    if isinstance(error, dict):
        error = error.get("message", "")
    if not isinstance(error, str):
        return "request_rejected"
    lowered = error.lower()
    if any(marker in lowered for marker in ("context length", "input length", "too many tokens", "token limit", "maximum context", "request too large")):
        return "request_too_large"
    if any(marker in lowered for marker in ("model not found", "model does not exist", "unknown model")):
        return "model_unavailable"
    if any(marker in lowered for marker in ("unsupported parameter", "invalid parameter", "not supported")):
        return "unsupported_request_parameter"
    return "request_rejected"


class SOPLLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
        keys: Optional[list] = None,
    ):
        self.provider = (provider or settings.SOP_LLM_PROVIDER or "mock").lower()
        self.timeout = timeout
        self._http = http_client
        self.last_structured_failure = ""
        self.last_response_shape: dict[str, Any] = {}
        self.last_structured_attempts: list[dict[str, Any]] = []
        self.last_usage: ModelUsage | None = None
        self.last_call_usages: list[ModelUsage] = []

        if self.provider == "mock":
            ensure_mock_allowed("SOP")
            self.base_url = ""
            self.model = "mock"
            self.api_key = ""
            return

        if self.provider not in PROVIDER_REGISTRY:
            raise SOPLLMError(
                f"未知 SOP LLM provider: {self.provider}",
                category="provider_unsupported",
            )
        key_attr, url_attr, model_attr = PROVIDER_KEY_MAP[self.provider]
        reg = PROVIDER_REGISTRY[self.provider]
        self.base_url = (base_url or getattr(settings, url_attr) or reg["base_url"]).rstrip("/")
        self.model = model or getattr(settings, model_attr) or reg["model"]
        self.api_key = api_key if api_key is not None else getattr(settings, key_attr, "")
        if keys:
            self.keys = list(keys)
        elif self.api_key:
            self.keys = [self.api_key]
        else:
            self.keys = []
        if not self.api_key and not self.keys:
            raise SOPLLMError(
                f"provider={self.provider} 需要配置 {key_attr} 或 RAG_LLM_KEYS",
                category="provider_not_configured",
            )

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
            return {
                "content": self._mock_content(system_prompt),
                "_meta": {
                    "usage": ModelUsage(
                        provider="mock", model="mock"
                    ).model_dump(mode="json"),
                },
            }

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

        keys = self.keys or [self.api_key]
        last_err = None
        last_category = "request_failed"
        for key in keys:
            try:
                client = self._http or httpx.Client(timeout=self.timeout)
                try:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code in (401, 402, 429):
                        last_category = {
                            401: "credential_rejected",
                            402: "payment_required",
                            429: "rate_limited",
                        }[resp.status_code]
                        last_err = f"HTTP {resp.status_code} (key 被拒)"
                        logger.warning("LLM key 被拒(%s),切换下一 key", resp.status_code)
                        continue
                    if resp.status_code >= 500:
                        last_category = "server_error"
                        last_err = f"HTTP {resp.status_code} (服务端错误)"
                        logger.warning("LLM 服务端错误(%s),尝试下一 key", resp.status_code)
                        continue
                    # 其余 4xx(如 400/403/404/422)为不可重试的客户端错误,直接上报,不切换 key
                    if (
                        use_json_mode
                        and resp.status_code == 400
                        and _response_format_rejected(resp)
                    ):
                        raise SOPLLMError(
                            "LLM provider rejected JSON response mode",
                            category="response_format_rejected",
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    self.last_response_shape = _response_shape(data)
                    choices = data.get("choices") if isinstance(data, dict) else None
                    first_choice = choices[0] if isinstance(choices, list) and choices else None
                    content = _choice_content(first_choice)
                    if not content:
                        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else ""
                        raise SOPLLMError(
                            "LLM completion ended before structured content was emitted"
                            if finish_reason == "length"
                            else "LLM returned an unsupported completion payload",
                            category="response_truncated" if finish_reason == "length" else "response_payload_invalid",
                        )
                    usage = extract_model_usage(data, provider=self.provider, model=self.model)
                    self._record_usage(usage)
                    return {
                        "content": content,
                        "_meta": {
                            "usage": usage.model_dump(mode="json"),
                        },
                    }
                finally:
                    if self._http is None:
                        client.close()
            except httpx.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status not in (401, 402, 429):
                    safe_category = _request_rejection_category(getattr(e, "response", None))
                    raise SOPLLMError(
                        f"LLM request rejected (HTTP {status})",
                        category=safe_category,
                    ) from e
                # 网络/超时等瞬时异常,尝试下一 key
                last_err = e
                if isinstance(e, httpx.TimeoutException):
                    last_category = "transport_timeout"
                elif isinstance(e, httpx.NetworkError):
                    last_category = "network_error"
                else:
                    last_category = "request_failed"
                logger.warning("LLM 请求失败(尝试下一 key): %s", e)
                continue
        raise SOPLLMError(f"所有 LLM key 均不可用: {last_err}", category=last_category)

    def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        max_structured_attempts: int = 2,
    ) -> Optional[dict]:
        """返回解析后的 dict,或 None(调用方走兜底)。内置一次降温度重试。"""
        if not 1 <= max_structured_attempts <= 3:
            raise ValueError("max_structured_attempts must be between 1 and 3")
        self.reset_usage_tracking()
        if self.provider == "mock":
            try:
                return json.loads(self._mock_content(system_prompt))
            except (json.JSONDecodeError, ValueError):
                return None
        # Keep the repair attempt in JSON mode unless the provider explicitly
        # rejects that mode. A prose retry cannot repair a structured contract.
        repair_budget = min(max(max_tokens * 2, max_tokens + 800), 6_000)
        attempts = (
            (temperature, True, max_tokens),
            (0.0, True, repair_budget),
        )[:max_structured_attempts]
        self.last_structured_failure = ""
        for attempt_number, (t, use_json_mode, token_budget) in enumerate(attempts, start=1):
            try:
                raw = self.chat(
                    system_prompt,
                    user_prompt,
                    temperature=t,
                    max_tokens=token_budget,
                    use_json_mode=use_json_mode,
                )
                parsed = _parse_json(raw.get("content", ""))
                if parsed is not None:
                    self.last_structured_failure = ""
                    self.last_structured_attempts.append({
                        "attempt": attempt_number,
                        "json_mode": use_json_mode,
                        "max_tokens": token_budget,
                        "result": "valid_json",
                    })
                    return parsed
                finish_reason = str(self.last_response_shape.get("finish_reason") or "")
                self.last_structured_failure = (
                    "response_truncated" if finish_reason == "length" else "response_payload_invalid"
                )
                self.last_structured_attempts.append({
                    "attempt": attempt_number,
                    "json_mode": use_json_mode,
                    "max_tokens": token_budget,
                    "result": self.last_structured_failure,
                })
            except SOPLLMError as e:
                self.last_structured_failure = e.category
                self.last_structured_attempts.append({
                    "attempt": attempt_number,
                    "json_mode": use_json_mode,
                    "max_tokens": token_budget,
                    "result": self.last_structured_failure,
                })
                if (
                    e.category == "response_format_rejected"
                    and use_json_mode
                    and max_structured_attempts > 1
                ):
                    try:
                        raw = self.chat(
                            system_prompt,
                            user_prompt,
                            temperature=0.0,
                            max_tokens=repair_budget,
                            use_json_mode=False,
                        )
                        parsed = _parse_json(raw.get("content", ""))
                        if parsed is not None:
                            self.last_structured_failure = ""
                            self.last_structured_attempts.append({
                                "attempt": attempt_number,
                                "json_mode": False,
                                "max_tokens": repair_budget,
                                "result": "valid_json",
                            })
                            return parsed
                        self.last_structured_failure = "response_payload_invalid"
                        self.last_structured_attempts.append({
                            "attempt": attempt_number,
                            "json_mode": False,
                            "max_tokens": repair_budget,
                            "result": self.last_structured_failure,
                        })
                    except SOPLLMError as fallback_error:
                        self.last_structured_failure = fallback_error.category
                        self.last_structured_attempts.append({
                            "attempt": attempt_number,
                            "json_mode": False,
                            "max_tokens": repair_budget,
                            "result": self.last_structured_failure,
                        })
                        logger.warning("SOP LLM plain JSON fallback failed: %s", fallback_error)
                    break
                # A repair prompt cannot fix an account, credential, model,
                # or request-contract rejection. Preserve the first safe
                # diagnostic and return control to the governed fallback.
                if e.category in {
                    "credential_rejected",
                    "payment_required",
                    "provider_not_configured",
                    "provider_unsupported",
                    "model_unavailable",
                    "unsupported_request_parameter",
                    "request_rejected",
                }:
                    logger.warning("SOP LLM returned a non-retryable structured failure: %s", e.category)
                    break
                logger.warning("SOP LLM 解析失败(retry): %s", e)
        logger.warning("SOP LLM 结构化解析最终失败,返回 None")
        return None

    def reset_usage_tracking(self) -> None:
        """Start a new request-scoped provider usage ledger."""
        self.last_usage = None
        self.last_call_usages = []
        self.last_response_shape = {}
        self.last_structured_attempts = []

    def _record_usage(self, usage: ModelUsage) -> None:
        self.last_usage = usage
        self.last_call_usages.append(usage)

    def _mock_content(self, system_prompt: str) -> str:
        sp = system_prompt.lower()
        if "query rewrite" in sp or "查询改写" in system_prompt or "expanded_queries" in sp:
            return json.dumps(
                {
                    "expanded_queries": ["扩展查询1", "扩展查询2", "扩展查询3"],
                    "intent": "general",
                    "keywords": ["关键词1", "关键词2"],
                    "sub_queries": [],
                    "rewritten_query": "扩展查询1 扩展查询2 扩展查询3",
                },
                ensure_ascii=False,
            )
        if "optimization_suggestions" in sp or "优化建议" in system_prompt:
            return json.dumps(
                {
                    "optimization_suggestions": [
                        {
                            "id": "opt_001",
                            "title": "风险缓解方案制定",
                            "description": "当前识别到高风险项，建议优先制定针对性缓解方案，建立风险预警机制。",
                            "priority": "高",
                            "estimated_impact": "降低运营风险",
                            "implementation_steps": ["风险评估", "方案设计", "措施实施", "效果跟踪"],
                            "related_risks": ["流程步骤超时", "数据安全泄露"],
                        },
                        {
                            "id": "opt_002",
                            "title": "流程自动化优化",
                            "description": "针对高频重复性步骤引入自动化工具，预计节省人力成本60%。",
                            "priority": "高",
                            "estimated_impact": "节省人力成本",
                            "implementation_steps": ["识别高频步骤", "选择自动化工具", "试点实施", "推广落地"],
                        },
                        {
                            "id": "opt_003",
                            "title": "建立SLA监控预警机制",
                            "description": "开发流程执行监控看板，实时跟踪SLA达成情况，缩短问题响应时间。",
                            "priority": "中",
                            "estimated_impact": "提升流程可预测性",
                            "implementation_steps": ["定义关键指标", "开发监控面板", "配置预警规则", "培训推广"],
                        },
                    ],
                    "prioritized_actions": [
                        {"action": "优先处理风险缓解，当前有高风险需立即关注", "timeline": "1-2周", "priority": "紧急"},
                        {"action": "实施流程自动化，提升效率降低成本", "timeline": "1-2个月", "priority": "高"},
                        {"action": "建立SLA监控预警机制", "timeline": "2-3个月", "priority": "中"},
                    ],
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
