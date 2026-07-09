# SOP 汇报 AI 段接入真实中文 LLM — 设计文档

- 日期: 2026-07-09
- 状态: 已评审(用户批准),待写实现计划
- 范围: 仅 SOP 汇报引擎的 AI 段(`generate_ai_summary` / `generate_ai_recommendations`)

## 1. 背景与目标

当前 `app/engines/sop_report_engine.py` 的 AI 段(`enable_ai_analysis=True` 时产出)
虽然调用了 `LLMAgentService.chat`,但存在两个问题:

1. **内容泛泛**:提示词只塞了 `business_domain / len(workflow) / len(risks)` 等计数,
   没有把流程步骤、角色、SLA、KPI、风险等真实内容喂给模型,即使真模型也只会套话。
2. **解析脆弱**:`json.loads` 一旦失败就掉进一段写死的套话兜底;本环境未配真实
   provider 时 `chat()` 走 mock,看到的也是假数据。

目标: **从零为 SOP AI 段接入真实中文 LLM**(DeepSeek / 豆包 / 千问 / Kimi),
并顺带把提示词做"接地"、把解析做"稳健",让 AI 摘要与建议真正可用、可落地。

非目标(本次不做): 不接入知识库 RAG grounding、不做双阶段生成、不修改漂移中的
`app/services/llm_service.py`、不触碰 `.db*` / `dashboard.html` / `orphan_fork` 等外部漂移。

## 2. 架构与边界

- **新建 `app/services/sop_llm_client.py`**:自包含、零依赖 `llm_service.py`。
  职责单一:构造并发送 OpenAI 兼容的 `/v1/chat/completions` 请求,接收并稳健解析 JSON,
  处理超时/重试/兜底。
- SOP 引擎 `SOPReportEngine._get_llm_service()` 改为返回 `SOPLLMClient`
  (按配置惰性构造,复用 engine 现有惰性加载模式)。
- 不修改 `llm_service.py`,不触碰任何外部漂移文件。

## 3. 多厂商注册表

四家厂商均提供 **OpenAI 兼容** 的 chat completions 协议,因此只需一个客户端 + 注册表。

| provider key | base_url | 默认模型 |
|---|---|---|
| `deepseek` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| `doubao`(豆包) | `https://ark.cn-beijing.volces.com/api/v3` | 用户 endpoint id(如 `doubao-pro-4-preview`) |
| `qwen`(千问) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| `kimi`(月之暗面) | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |

配置(`app/core/config.py` 新增,均为可选、带默认值):

- `SOP_LLM_PROVIDER: str = "deepseek"`
- `SOP_LLM_API_KEY: str = ""`
- `SOP_LLM_BASE_URL: str = ""`(为空则用注册表默认)
- `SOP_LLM_MODEL: str = ""`(为空则用注册表默认)

选择逻辑: `SOP_LLM_PROVIDER` 命中注册表取默认 `base_url` / `model`;
环境变量 `SOP_LLM_BASE_URL` / `SOP_LLM_MODEL` 可逐项覆盖。`SOP_LLM_PROVIDER="mock"`
为离线/测试模式。新增厂商只需在注册表加一行,无需改客户端逻辑。

## 4. 客户端行为

### 4.1 请求
- `POST {base_url}/chat/completions`
- Headers: `Authorization: Bearer {api_key}`, `Content-Type: application/json`
- Body:
  - `model`: 选定模型
  - `messages`: `[{role:"system",...}, {role:"user",...}]`
  - `temperature`: 摘要 `0.3`、建议 `0.5`
  - `max_tokens`: 摘要 `1200`、建议 `2000`
  - `response_format`: `{"type":"json_object"}`(当 provider 支持时启用;不支持则省略,靠解析兜底)
- 使用 `httpx`(项目已依赖)同步客户端;`SOPLLMClient` 可注入 `httpx.Client` 便于测试。

### 4.2 解析与重试
1. 取 `choices[0].message.content`。
2. 去 ```json 代码围栏 → `json.loads`。
3. 失败则正则抽取首个 `{...}`(贪婪匹配到对应闭合)再 `json.loads`。
4. 仍失败 → 降温度(`temperature*0.5`)重试一次。
5. 仍失败 → 返回 `None`,由调用方走数据感知兜底(见 §6)。

### 4.3 健壮性
- 超时:默认 `30s`(`httpx` timeout)。
- 重试:解析失败重试 1 次(见 §4.2.4);网络/HTTP 非 2xx 不盲目重试(避免雪崩),
  直接抛 `SOPLLMError` 并由调用方兜底。
- **绝不**让异常中断整份 SOP 报告生成:所有 AI 段失败都降级到兜底内容。

### 4.4 离线 / 测试模式
- `SOP_LLM_PROVIDER="mock"`(或 `SOP_LLM_API_KEY` 为空且非显式配置)时,
  `chat()` 直接返回**基于真实数据拼接**的结构化 JSON(同 §6 兜底逻辑),
  保证 30 个 sop 测试与新增单测无需联网即可通过。

## 5. 与 SOP 引擎集成

- `generate_ai_summary` / `generate_ai_recommendations`:
  将 `self._get_llm_service()` 的返回类型由 `LLMAgentService` 改为 `SOPLLMClient`;
  system_prompt 改为"你是资深业务流程分析师,只输出严格 JSON"。
- `generate_full_sop_report(business_system, enable_ai_analysis=True)` 接口签名不变,
  仅在底层使用新客户端。
- 已存在的 API 端点 `/ai-summary`、`/ai-recommendations`(`app/api/sop_report_api.py`)
  无需修改,只换底层客户端。

## 6. 提示词接地(内容质量核心)

新增模块内辅助函数 `build_sop_context(bs: dict) -> str`:
- 抽取 `workflow`(步骤名 / 负责人 / 时长)、`roles`(角色 / 部门 / 人数)、
  `sla`、`kpi`、`risks`(风险点 / 严重度 / 缓解措施)、`csf`、`cost_estimate`。
- 压成紧凑结构化文本,**限长**(约 4000 字符上限,超出截断最不重要的段落)以防超 token。
- 作为 user_prompt 主体传入。

AI 段输出 schema(与现有前端/API 消费字段保持一致):

- 摘要 `{executive_summary, key_findings[], recommendations[], risk_highlights[]}`
- 建议 `{optimization_suggestions[{id,title,description,priority,estimated_impact,implementation_steps[]}], prioritized_actions[]}`

**兜底(任意失败)**:用真实数据拼出同样 schema 的内容(例如 key_findings 直接由
roles/sla/kpi 计数与风险列表生成),不再是写死的固定套话。

## 7. 测试

- `tests/test_sop_llm_client.py`(新增):
  - 用 `respx`(或 monkeypatch `httpx`)分别验证 4 家厂商的请求 URL / headers / body 构造正确。
  - JSON 解析:正常 JSON、带 ```json 围栏、脏数据(前后缀文本)均能抽出。
  - 重试:首次脏数据、重试成功。
  - 超时 / HTTP 5xx → 抛 `SOPLLMError` 且不重试。
  - `mock` 模式返回结构化 JSON。
- `tests/test_sop_report_engine.py`(扩展):
  - `enable_ai_analysis=True` 下断言 `ai_summary` / `ai_recommendations` 字段齐全、schema 正确
    (mock provider 也过)。
- 全量回归保持绿(不回退已有的 251 passed)。

## 8. 交付与回滚

- 提交文件:
  - `app/services/sop_llm_client.py`(新增)
  - `app/core/config.py`(新增 SOP LLM 配置项)
  - `app/engines/sop_report_engine.py`(换客户端 + 接地提示词 + 兜底)
  - `tests/test_sop_llm_client.py`(新增)、`tests/test_sop_report_engine.py`(扩展)
- 默认 `SOP_LLM_PROVIDER="mock"` 时离线可用;配置真实 `SOP_LLM_API_KEY` 后自动走真模型,无需改代码。
- 外部漂移(`.db*`、`llm_service.py`、`dashboard.html`、`orphan_fork/*` 删除)一律不碰、不提交。

## 9. 风险与权衡

- **厂商 JSON 模式差异**:部分厂商旧模型不支持 `response_format=json_object`,
  已通过"解析兜底"覆盖,不阻塞主流程。
- **token 成本**:接地上下文 + 重试会增加 token 消耗;通过限长与单重试控制。
- **密钥安全**:仅从环境变量/配置读取,不写死、不入库。
- **与现有 `llm_service.py` 并存**:本次刻意新建独立客户端,避免改动漂移文件;
  后续若有统一 LLM 抽象需求可再抽公共层(不在本次范围)。
