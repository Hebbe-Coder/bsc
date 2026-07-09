# SOP 汇报 AI 段接入真实中文 LLM — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零为 SOP 汇报引擎的 AI 摘要 / 建议段接入 OpenAI 兼容的多厂商中文 LLM(DeepSeek / 豆包 / 千问 / Kimi),并配套接地提示词与稳健 JSON 解析兜底。

**Architecture:** 新建自包含客户端 `app/services/sop_llm_client.py`(OpenAI 兼容 + 厂商注册表 + mock 离线模式),复用 `app/core/config.py` 已有的 `DEEPSEEK_*/DOUBAO_*/QWEN_*` 配置并新增 `KIMI_*`;SOP 引擎 `_get_llm_service()` 改为返回该客户端,提示词改为接地上下文,解析失败/异常一律走基于真实数据的兜底。

**Tech Stack:** Python 3.13, FastAPI/Pydantic v2, `httpx`(已依赖),pytest。无新增第三方依赖(测试用注入式 fake client,不引入 respx)。

> 与 spec 的一处细化:spec 写的是新增 `SOP_LLM_API_KEY` 等独立配置;实际 `config.py` 已存在 `DEEPSEEK_API_KEY/DOUBAO_API_KEY/QWEN_API_KEY`,故客户端**复用这些已有 key**,仅新增 `KIMI_*`(配置里原本没有 Kimi)与 `SOP_LLM_PROVIDER` 选择开关。意图(spec 的"多厂商可配置、默认 mock 离线可用")完全一致,且更 DRY。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `app/core/config.py` | Modify (`:36-56` 附近) | 新增 `KIMI_API_KEY/BASE_URL/MODEL` 与 `SOP_LLM_PROVIDER` |
| `app/services/sop_llm_client.py` | **Create** | 多厂商 OpenAI 兼容客户端 + 解析/重试 + mock |
| `app/engines/sop_report_engine.py` | Modify (`_get_llm_service` / `generate_ai_summary` / `generate_ai_recommendations`) | 换客户端 + 接地提示词 + 数据感知兜底 |
| `tests/test_sop_llm_client.py` | **Create** | 客户端单测(注册表/请求构造/解析/重试/异常/mock) |
| `tests/test_sop_report_engine.py` | Modify (追加) | AI 段在 mock provider 下 schema 正确 |

---

### Task 1: 配置新增 KIMI 与 SOP_LLM_PROVIDER

**Files:**
- Modify: `app/core/config.py`(在 `QWEN_MODEL` 之后插入 `KIMI_*`,在 `OCR_PROVIDER` 之后插入 `SOP_LLM_PROVIDER`)

- [ ] **Step 1: 写失败测试**

在 `tests/test_config_sop_llm.py`(新建)中:

```python
from app.core.config import settings


def test_sop_llm_provider_default_is_mock():
    assert hasattr(settings, "SOP_LLM_PROVIDER")
    assert settings.SOP_LLM_PROVIDER == "mock"


def test_kimi_config_defaults():
    assert settings.KIMI_BASE_URL == "https://api.moonshot.cn/v1"
    assert settings.KIMI_MODEL == "moonshot-v1-8k"
    assert settings.KIMI_API_KEY == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_config_sop_llm.py -v`
Expected: FAIL(`AttributeError` / `settings` 无 `SOP_LLM_PROVIDER`)

- [ ] **Step 3: 修改 `app/core/config.py`**

在第 42 行 `QWEN_MODEL: str = "qwen-plus"` 之后插入:

```python
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"
```

在第 56 行 `OCR_PROVIDER: str = "doubao"` 之后插入:

```python
    SOP_LLM_PROVIDER: str = "mock"  # SOP AI 段使用的 LLM provider(deepseek/doubao/qwen/kimi/mock)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_config_sop_llm.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/core/config.py tests/test_config_sop_llm.py
git commit -m "feat(config): add KIMI_* and SOP_LLM_PROVIDER for SOP AI section"
```

---

### Task 2: 创建 SOP LLM 客户端

**Files:**
- Create: `app/services/sop_llm_client.py`
- Test: `tests/test_sop_llm_client.py`

- [ ] **Step 1: 写失败测试(先覆盖核心行为)**

`tests/test_sop_llm_client.py`:

```python
import httpx
import pytest

from app.services.sop_llm_client import (
    PROVIDER_REGISTRY,
    SOPLLMClient,
    SOPLLMError,
    _parse_json,
)


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        return self._handler(self.calls, url, headers, json)

    def close(self):
        pass


def test_registry_has_four_providers():
    for p in ("deepseek", "doubao", "qwen", "kimi"):
        assert p in PROVIDER_REGISTRY


def test_mock_returns_valid_summary_dict():
    c = SOPLLMClient(provider="mock")
    out = c.chat_structured("你是分析师", "数据")
    assert isinstance(out, dict)
    assert set(["executive_summary", "key_findings", "recommendations", "risk_highlights"]) <= set(out.keys())


def test_mock_returns_valid_reco_dict():
    c = SOPLLMClient(provider="mock")
    out = c.chat_structured("请给优化建议", "数据")
    assert isinstance(out, dict)
    assert "optimization_suggestions" in out
    assert "prioritized_actions" in out


def test_request_construction_deepseek():
    captured = {}

    def handler(n, url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return _FakeResp({"choices": [{"message": {"content": '{"executive_summary":"ok","key_findings":[],"recommendations":[],"risk_highlights":[]}'}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk-test", http_client=_FakeClient(handler))
    out = c.chat_structured("你是分析师", "数据")
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert out["executive_summary"] == "ok"


def test_parse_strips_code_fence():
    content = '```json\n{"a": 1}\n```'
    assert _parse_json(content) == {"a": 1}


def test_parse_extracts_embedded_json():
    content = "好的,结果是 {"a": 1} 完毕"
    assert _parse_json(content) == {"a": 1}


def test_retry_on_dirty_then_valid():
    state = {"n": 0}

    def handler(n, url, headers, body):
        state["n"] = n
        if n == 1:
            return _FakeResp({"choices": [{"message": {"content": "不是 json"}}]})
        return _FakeResp({"choices": [{"message": {"content": '{"executive_summary":"ok","key_findings":[],"recommendations":[],"risk_highlights":[]}'}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    out = c.chat_structured("你是分析师", "数据")
    assert out["executive_summary"] == "ok"
    assert state["n"] == 2  # 重试了一次


def test_http_5xx_raises_sopllmerror():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "boom"}, status=500)

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    with pytest.raises(SOPLLMError):
        c.chat("你是分析师", "数据")


def test_chat_structured_returns_none_on_persistent_failure():
    def handler(n, url, headers, body):
        return _FakeResp({"choices": [{"message": {"content": "no json"}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    assert c.chat_structured("你是分析师", "数据") is None


def test_unknown_provider_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="nope", api_key="x")


def test_missing_api_key_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="kimi")  # settings.KIMI_API_KEY 默认空
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sop_llm_client.py -v`
Expected: FAIL(`ModuleNotFoundError: app.services.sop_llm_client`)

- [ ] **Step 3: 创建 `app/services/sop_llm_client.py`**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_sop_llm_client.py -v`
Expected: PASS(全部 11 例)

- [ ] **Step 5: 提交**

```bash
git add app/services/sop_llm_client.py tests/test_sop_llm_client.py
git commit -m "feat(sop): add OpenAI-compatible multi-provider LLM client (deepseek/doubao/qwen/kimi)"
```

---

### Task 3: SOP 引擎接入客户端 + 接地提示词 + 兜底

**Files:**
- Modify: `app/engines/sop_report_engine.py`
  - `_get_llm_service()`(约 `:41-46`)
  - `generate_ai_summary()`(约 `:728-801`)
  - `generate_ai_recommendations()`(约 `:803-896`)
  - 新增辅助方法 `build_sop_context` / `_fallback_summary` / `_fallback_recommendations`
- Test: `tests/test_sop_report_engine.py`(追加)

- [ ] **Step 1: 写失败测试(追加到 `tests/test_sop_report_engine.py`)**

先确认该文件已存在的导入与 `SOPReportEngine` 引入方式,追加:

```python
def test_generate_ai_summary_schema_under_mock():
    from app.engines.sop_report_engine import SOPReportEngine

    engine = SOPReportEngine()
    bs = {
        "business_domain": "测试业务",
        "workflow": [{"name": "步骤1", "owner": "角色A", "duration": "2h"}],
        "roles": [{"role": "角色A", "department": "测试部", "headcount": 1}],
        "risks": [{"risk": "风险X", "severity": "高", "mitigation": "加强监控"}],
    }
    out = engine.generate_ai_summary(bs)
    assert out["title"] == "智能摘要"
    assert isinstance(out["executive_summary"], str) and out["executive_summary"]
    assert isinstance(out["key_findings"], list)
    assert isinstance(out["recommendations"], list)
    assert isinstance(out["risk_highlights"], list)


def test_generate_full_report_includes_ai_when_enabled():
    from app.engines.sop_report_engine import SOPReportEngine

    engine = SOPReportEngine()
    bs = {
        "business_domain": "测试业务",
        "workflow": [{"name": "步骤1", "owner": "角色A", "duration": "2h"}],
        "roles": [{"role": "角色A", "department": "测试部", "headcount": 1}],
        "risks": [{"risk": "风险X", "severity": "高", "mitigation": "加强监控"}],
    }
    report = engine.generate_full_sop_report(bs, enable_ai_analysis=True)
    assert "ai_summary" in report
    assert "ai_recommendations" in report
    assert report["ai_summary"]["executive_summary"]
    assert report["ai_recommendations"]["optimization_suggestions"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sop_report_engine.py -v -k "ai_summary or ai_when_enabled"`
Expected: FAIL(`generate_ai_summary` 当前返回写死套话且 `risk_highlights` 等来自旧逻辑;或直接因 `SOPLLMClient` 未接入而产出不符)

- [ ] **Step 3: 修改 `sop_report_engine.py`**

3a. 替换 `_get_llm_service()`(约 `:41-46`):

```python
    def _get_llm_service(self):
        """延迟加载 SOP 专用 LLM 客户端(OpenAI 兼容,多厂商)。"""
        if self._llm_service is None:
            from app.services.sop_llm_client import SOPLLMClient
            self._llm_service = SOPLLMClient()
        return self._llm_service
```

3b. 在 `generate_ai_summary` 之前新增三个辅助方法(放在 `generate_ai_summary` 上方):

```python
    def build_sop_context(self, bs: Dict[str, Any], max_chars: int = 4000) -> str:
        """把 business_system 的真实内容压成紧凑结构化文本,供 LLM 接地。"""
        parts = []
        workflow = bs.get("workflow", [])
        if workflow:
            steps = []
            for i, s in enumerate(workflow[:20], 1):
                owner = s.get("owner", s.get("role", "—"))
                dur = s.get("duration", s.get("estimated_time", "—"))
                steps.append(f"{i}. {s.get('name', s.get('step', '步骤'))} (负责人:{owner}, 时长:{dur})")
            parts.append("【流程步骤】\n" + "\n".join(steps))
        roles = bs.get("roles", [])
        if roles:
            rtxt = "; ".join(
                f"{r.get('role', '角色')}({r.get('department', '—')}, {r.get('headcount', '?')}人)"
                for r in roles[:15]
            )
            parts.append("【角色】" + rtxt)
        sla = bs.get("sla", [])
        if sla:
            parts.append("【SLA】" + "; ".join(
                f"{s.get('step', s.get('name', '环节'))}:{s.get('target', '—')}" for s in sla[:10]
            ))
        kpi = bs.get("kpi", [])
        if kpi:
            parts.append("【KPI】" + "; ".join(
                f"{k.get('name', '指标')}:{k.get('target', '—')}" for k in kpi[:10]
            ))
        risks = bs.get("risks", [])
        if risks:
            rk = [
                f"{r.get('risk', r.get('name', '风险'))}(严重度:{r.get('severity', '—')}, 缓解:{r.get('mitigation', '—')})"
                for r in risks[:10]
            ]
            parts.append("【风险】\n" + "\n".join(rk))
        ctx = "\n\n".join(parts)
        if len(ctx) > max_chars:
            ctx = ctx[:max_chars] + "\n...（已截断）"
        return ctx

    def _fallback_summary(self, bs: Dict[str, Any]) -> Dict[str, Any]:
        workflow = bs.get("workflow", [])
        roles = bs.get("roles", [])
        risks = bs.get("risks", [])
        domain = bs.get("business_domain", "业务")
        return {
            "executive_summary": f"{domain}流程共 {len(workflow)} 个步骤、{len(roles)} 个角色参与,需关注效率与风险控制。",
            "key_findings": [
                f"流程包含 {len(workflow)} 个步骤",
                f"涉及 {len(roles)} 个角色 / 部门",
                f"识别到 {len(risks)} 个风险项",
            ],
            "recommendations": ["定期回顾流程执行情况", "加强风险监控与预警", "对高频步骤考虑自动化"],
            "risk_highlights": [r.get("risk", r.get("name", "风险项")) for r in risks[:2]],
        }

    def _fallback_recommendations(self, bs: Dict[str, Any]) -> Dict[str, Any]:
        workflow = bs.get("workflow", [])
        roles = bs.get("roles", [])
        return {
            "optimization_suggestions": [
                {"id": "opt_001", "title": "流程自动化", "description": "针对重复性步骤引入自动化工具", "priority": "高", "estimated_impact": "节省人力成本", "implementation_steps": ["识别步骤", "选工具", "实施"]},
                {"id": "opt_002", "title": "建立监控机制", "description": "开发流程执行监控看板", "priority": "中", "estimated_impact": "缩短问题响应时间", "implementation_steps": ["定指标", "开发", "上线"]},
            ],
            "prioritized_actions": [
                {"action": f"优先自动化 {len(workflow)} 个步骤中的高频环节", "timeline": "1-2个月"},
                {"action": f"为 {len(roles)} 个角色建立职责看板", "timeline": "2-3个月"},
            ],
        }
```

3c. 重写 `generate_ai_summary`(原 `:728-801`):

```python
    def generate_ai_summary(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """生成智能摘要(LLM 驱动,失败自动走数据感知兜底)。"""
        domain = business_system.get("business_domain", "业务")
        context = self.build_sop_context(business_system)
        system_prompt = (
            "你是资深业务流程分析师。仅基于提供的流程数据,输出严格 JSON,不要任何解释性文字。"
            "字段:executive_summary(一句话核心摘要),key_findings(3-5条字符串),"
            "recommendations(2-3条字符串),risk_highlights(1-2条字符串)。"
        )
        user_prompt = f"业务领域:{domain}\n\n流程数据:\n{context}\n\n请生成执行摘要(JSON)。"
        try:
            client = self._get_llm_service()
            data = client.chat_structured(system_prompt, user_prompt, temperature=0.3, max_tokens=1200)
            if data is None:
                data = self._fallback_summary(business_system)
            return {
                "title": "智能摘要",
                "description": "LLM生成的汇报核心要点",
                "executive_summary": data.get("executive_summary", ""),
                "key_findings": data.get("key_findings", []),
                "recommendations": data.get("recommendations", []),
                "risk_highlights": data.get("risk_highlights", []),
            }
        except Exception as e:
            logger.warning(f"AI摘要生成异常,使用兜底: {e}")
            fb = self._fallback_summary(business_system)
            return {"title": "智能摘要", "description": "LLM生成的汇报核心要点", **fb}
```

3d. 重写 `generate_ai_recommendations`(原 `:803-896`):

```python
    def generate_ai_recommendations(self, business_system: Dict[str, Any]) -> Dict[str, Any]:
        """生成 AI 优化建议(LLM 驱动,失败自动走数据感知兜底)。"""
        domain = business_system.get("business_domain", "业务")
        context = self.build_sop_context(business_system)
        system_prompt = (
            "你是流程优化专家。仅基于提供的流程数据,输出严格 JSON,不要任何解释性文字。"
            "字段:optimization_suggestions(数组,每项 {id,title,description,priority,estimated_impact,implementation_steps[]}),"
            "prioritized_actions(数组,每项 {action,timeline})。"
        )
        user_prompt = f"业务领域:{domain}\n\n流程数据:\n{context}\n\n请提出优化建议(JSON)。"
        try:
            client = self._get_llm_service()
            data = client.chat_structured(system_prompt, user_prompt, temperature=0.5, max_tokens=2000)
            if data is None:
                data = self._fallback_recommendations(business_system)
            return {
                "title": "AI优化建议",
                "description": "LLM生成的流程改进建议",
                "optimization_suggestions": data.get("optimization_suggestions", []),
                "prioritized_actions": data.get("prioritized_actions", []),
            }
        except Exception as e:
            logger.warning(f"AI优化建议生成异常,使用兜底: {e}")
            fb = self._fallback_recommendations(business_system)
            return {"title": "AI优化建议", "description": "LLM生成的流程改进建议", **fb}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_sop_report_engine.py -v -k "ai_summary or ai_when_enabled"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/engines/sop_report_engine.py tests/test_sop_report_engine.py
git commit -m "feat(sop): wire real LLM client into AI summary/recommendations with grounded prompts + fallback"
```

---

### Task 4: 全量回归

**Files:** 无新增,仅验证

- [ ] **Step 1: 运行全量测试**

Run: `pytest -q`
Expected: `251 passed` 或更多(因新增测试),`0 failed`(若真实 provider 未配置,SOP AI 段走 mock,不影响)

- [ ] **Step 2: 提交回归结论(可选,若仅验证可不提交)**

如需要留痕:
```bash
git commit --allow-empty -m "test: full suite green after SOP LLM integration"
```

---

## 自审结果(写作时已完成)

- **Spec 覆盖:** §2 架构(client 新建)→ Task 2/3;§3 注册表 → Task 2 `PROVIDER_REGISTRY`+Task1 `KIMI_*`;§4 请求/解析/重试/异常/mock → Task 2 测试全覆盖;§5 引擎集成 → Task 3;§6 接地提示词+兜底 → Task 3 `build_sop_context`/`_fallback_*`;§7 测试 → Task 1/2/3 测试;§8 交付 → 各 Task 提交步骤。
- **无占位符:** 所有步骤含完整代码。
- **类型一致性:** `SOPLLMClient.chat_structured` 在 Task2/Task3 签名一致;`build_sop_context`/`_fallback_summary`/`_fallback_recommendations` 在 Task3 内定义并被两处 generate 方法使用,名称一致。
- **与 spec 偏差说明:** 复用已有 `DEEPSEEK_*/DOUBAO_*/QWEN_*` 配置(见文件头部注记),仅新增 `KIMI_*`,更 DRY,意图不变。
