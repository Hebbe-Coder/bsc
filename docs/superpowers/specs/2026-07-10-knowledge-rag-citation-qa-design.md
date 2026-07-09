---
title: 知识库 RAG 引用溯源与问答
status: approved
created: 2026-07-10
author: WorkBuddy
direction: 知识库 / 检索增强生成（RAG）引用溯源 + 问答 + 质量评估
---

# 知识库 RAG 引用溯源与问答设计

## 1. 背景与目标

知识库 RAG 骨架（keyword + tfidf + vector 三路 RRF 检索）已落地（`2026-07-09-knowledge-rag-design.md` 与 `2026-07-09-knowledge-dense-vector-design.md`）。现有 `KnowledgeService.retrieve()` 已能返回带 `doc_title`/`section`/`content`/`score` 的 chunk 列表，`/knowledge/retrieve` 端点可对外提供检索结果。

但**只到「检索」为止**——RAG 设计文档当初明确列为 **Out of Scope** 的三件事尚未做：
1. **分节精准注入 / 引用补全**：生成时按命中 chunk 的 section 结构化注入 prompt，并回传 section 路径。
2. **RAG 问答端到端端点**：retrieve → 生成带引用的答案 → 校验引用。
3. **RAG 质量评估**：precision@k / recall@k / faithfulness（引标评估）。

**本设计目标**：在上述骨架上补上「引用溯源 + 问答 + 评估」三段，复用既有检索层、多厂商 LLM 客户端（`app/services/sop_llm_client.py` 已是通用 OpenAI 兼容客户端），保持零新重依赖、可离线、与「检索/生成解耦」哲学一致。

### 目标（In Scope）
- `RAGAnswerGenerator`（`app/knowledge/answer.py`）：编排 retrieve → 分节结构化上下文 → 多厂商 LLM 生成带 `[n]` 引用 → 引用校验 → 返回 `{answer, citations, metrics}`。
- **分节精准注入**：`build_context` 按 `section` 归并 top chunk，生成带 `[章节]` 分段的结构化上下文，同时产出精确 `citations[]`（含 section 路径、offset、score、snippet）。
- **引用校验**：`validate_citations` 剔除答案中未命中的 `[n]`，杜绝编造引用，并算出 `citation_rate`。
- 新端点 `POST /knowledge/ask`（问答）与 `POST /knowledge/evaluate`（引标评估）。
- `RAGEvaluator`（`app/knowledge/eval.py`）：对 gold Q&A 算 P@k / R@k / faithfulness，内置 fixture 可离线跑，也接受上传 gold JSON。
- mock / 无 key 时优雅降级为「只返回检索上下文 + 出处」。

### 非目标（Out of Scope）
- 不新建 embedding 后端（已做稠密向量）；不接知识图谱检索（另议）。
- 不引入标注平台 / 外部评测服务；gold 集为内置 fixture + 可选上传 JSON。
- 不做流式生成（首版同步返回）。
- 不改 `KnowledgeService` 检索逻辑（仅复用其结果）。

## 2. 决策摘要

| 决策点 | 选择 | 理由 |
|---|---|---|
| 生成客户端 | 复用 `SOPLLMClient`（多厂商 deepseek/豆包/千问/Kimi） | 已建好、OpenAI 兼容、带 mock/重试/降级，零新依赖 |
| 配置 | 新增 `RAG_LLM_PROVIDER`（默认 mock） | 与 SOP/EMBEDDING 模式一致；可单独选模型，亦可回落 SOP 的厂商键 |
| 引用精度 | 分节精准注入 + citations 数组（含 section 路径） | 用户选定；上下文按章节归并注入，溯源到 section |
| 引用校验 | 后端剔除非命中 `[n]` + 算 `citation_rate` | 防幻觉，质量可度量 |
| 质量评估 | 引标评估（P@k/R@k/faithfulness） | 用户选定；内置 fixture 离线可算 |
| 多 Key | **同时支持多个 API Key**（轮询 + 故障转移） | 用户要求；提升配额/吞吐与可用性，单 key 失效自动切换 |
| 接地提示词 | **细分为多个子提示**（角色/任务/上下文契约/引用规则/输出 schema），可选两阶段（先引证规划再作答） | 用户要求；可控、可维护、可测试 |
| 架构形态 | 独立 `AnswerGenerator` + 新端点 | 与「检索/生成解耦」一致，改动局部 |
| 降级 | mock/无 key → 只返上下文+出处 | 与既有 degrade 哲学一致 |

## 3. 架构总览

```
POST /knowledge/ask {question, project_id, top_k}
   → RAGAnswerGenerator.answer(question, project_id, top_k)
        → KnowledgeService.retrieve(question, top_k, project_id)   # 复用三路 RRF
             → [{doc_title, section, content, score, chunk_id, offset}, ...]
        → build_context(chunks)
             → 按 section 归并 → 结构化上下文文本(带 [章节])
             → citations[] = [{index, chunk_id, doc_title, section, offset, score, snippet}]
        → if RAG_LLM_PROVIDER == "mock" (或 SOPLLMClient 构造/调用失败):
             → 返回 {answer:"", citations, degraded:True, note:"未生成答案(无可用模型)"}
        → else:
             → SOPLLMClient.chat_structured(system=接地 prompt, user=question+context)
             → parse → validate_citations(answer_text, citations)
                  → 剔除未命中 [n] → citation_rate = 命中/总数
             → 返回 {answer, citations, metrics:{citation_rate}}
   → ApiResponse.ok({answer, citations, degraded, metrics})

POST /knowledge/evaluate {gold?}   # gold: [{query, expected_chunk_ids?, expected_answer?}]
   → RAGEvaluator.evaluate(gold or 内置 fixture, top_k)
        → 遍历每条: retrieve(top_k) → 比对 expected_chunk_ids 算 P@k/R@k
        → 若可用 LLM: 调 answer() 算 faithfulness=citation_rate
        → 聚合 → {precision@k, recall@k, faithfulness, n}
   → ApiResponse.ok({...})
```

**解耦点**：`RAGAnswerGenerator` 只读 `KnowledgeService.retrieve` 的输出，不侵入检索层；生成用 `SOPLLMClient`（与 SOP AI 段共用同一客户端类，仅 provider 不同）。

## 4. 组件

**`RAGAnswerGenerator`（`app/knowledge/answer.py`）**
- `__init__(provider: Optional[str] = None, service=None, llm_client=None, keys: Optional[List[str]] = None)`：
  - `self.service = service or KnowledgeService()`（允许注入，便于测试用临时 DB）。
  - `self._llm_client = llm_client`（若提供则直接用；否则懒加载 `SOPLLMClient(provider or settings.RAG_LLM_PROVIDER, keys=keys or <该 provider 的 key 列表>)`）。
  - **多 Key**：`keys` 为 key 列表（通常来自 `RAG_LLM_KEYS` 或该 provider 的多个 key）。`SOPLLMClient` 扩展支持多 key——请求时轮询取下一个 key；遇到 `401/429/402`（鉴权/限流/配额）自动切换到下一个 key 重试，全部耗尽才抛 `SOPLLMError`。单 key 场景（列表长度 1）行为不变。
- `build_context(chunks: List[dict]) -> Tuple[str, List[dict]]`：
  - 按 `section`（空 section 归为「未分节」）归并 chunk，保留 RRF 顺序。
  - 为每个 chunk 分配 `[n]` 序号，生成形如：
    ```
    [章节：<section>]
    [1] <chunk.content 片段>
    [2] <chunk.content 片段>
    ```
  - 返回 `(context_text, citations)`，citations 每项：
    `{index, chunk_id, doc_title, section, offset, score, snippet}`。
- `answer(question, project_id=None, top_k=5) -> dict`：
  - 调 `self.service.retrieve(question, top_k, project_id)`；空 → `{answer:"", citations:[], degraded:True, note:"未检索到相关知识"}`。
  - `build_context` → `context`。
  - 若 `self.provider == "mock"` 或客户端不可用 → 返回 `{answer:"", citations, degraded:True, note:"未生成答案(无可用模型)"}`。
  - 否则进入真模型生成，使用**细分的接地提示词**（见 `app/knowledge/prompts.py`）：
    - `build_system_prompt()` 由多个**独立子提示块**拼装：`ROLE_BLOCK`（角色：基于企业知识库作答的分析师）+ `TASK_BLOCK`（任务：回答用户问题）+ `CONTEXT_CONTRACT_BLOCK`（上下文契约：下方 [n] 与章节的对应规则、必须只引用已提供内容）+ `CITATION_RULES_BLOCK`（引用规则：每事实必标 [n]、禁止无引用断言、禁止编造未标注来源）+ `OUTPUT_SCHEMA_BLOCK`（输出 schema：JSON `{answer}`）。各块为独立常量，可单独测试与调优。
    - 单阶段（默认）：`SOPLLMClient.chat_structured(system=build_system_prompt(), user=build_user_prompt(question, context))`。
    - **两阶段（可选，`RAG_TWO_PHASE=True`）**：先调一次 `build_citation_plan_prompt(question, context)` 让模型输出「支撑答案的 [n] 编号列表」（phase-1 引证规划）；再以其为约束调 `build_answer_prompt(question, context, plan)` 生成最终答案（phase-2 作答）。两阶段把「选哪些证据」与「如何组织答案」解耦，引用更精准。
    - 解析失败 → 降级为 `{answer:"", citations, degraded:True}`。
    - `validate_citations` → 返回 `{answer, citations, metrics:{"citation_rate": <float>}}`。
- `validate_citations(answer_text, citations) -> Tuple[str, float]`：
  - 正则提取答案中所有 `[n]`；仅保留 `n` 在 `citations` index 集合内的编号；移除非法 `[n]`（文本中也删掉编号，保留正文）。
  - `citation_rate = 合法引用数 / 总引用数`（无引用时为 1.0 或 0.0，约定无引用且答案非空记 0.0）。

**`prompts`（`app/knowledge/prompts.py`，新增）**——接地提示词的细分实现
- 各子提示块为**独立常量**，便于单测与调优：
  - `ROLE_BLOCK`：你是严格基于企业知识库作答的业务分析师，不得凭空杜撰。
  - `TASK_BLOCK`：根据用户问题，仅使用下方带编号的 [n] 知识给出答案。
  - `CONTEXT_CONTRACT_BLOCK`：说明 [n] 与「章节：xxx」下内容的对应关系；未提供编号的知识一律不得使用。
  - `CITATION_RULES_BLOCK`：每条事实必须带 [n]；禁止出现无 [n] 的来源断言；若知识不足以回答，明确说明「依据现有知识无法回答」。
  - `OUTPUT_SCHEMA_BLOCK`：只输出 JSON `{"answer": "<含 [n] 的答案>"}`，不要额外解释。
- 组装函数：
  - `build_system_prompt() -> str`：`"\n\n".join([ROLE_BLOCK, TASK_BLOCK, CONTEXT_CONTRACT_BLOCK, CITATION_RULES_BLOCK, OUTPUT_SCHEMA_BLOCK])`。
  - `build_user_prompt(question, context) -> str`：`f"问题：{question}\n\n知识：\n{context}"`。
  - `build_citation_plan_prompt(question, context) -> str`：仅要求模型返回「支撑回答的 [n] 编号列表」(JSON `{"cite_ids":[...]}`)，用于两阶段 phase-1。
  - `build_answer_prompt(question, context, plan) -> str`：phase-2，给定 `plan` 中的 cite_ids，要求只基于这些 [n] 撰写答案。

**`RAGEvaluator`（`app/knowledge/eval.py`）**
- `DEFAULT_GOLD: List[dict]`：内置 fixture（≥3 条，含 query + expected_chunk_ids，可选 expected_answer），离线可跑。
- `evaluate(service, gold, top_k=5, project_id=None, with_faithfulness=False) -> dict`：
  - 对每条 gold：`retrieve(query, top_k)` → `retrieved_ids`。
  - `precision@k = |retrieved ∩ expected| / min(top_k, |retrieved|)`；`recall@k = |retrieved ∩ expected| / |expected|`。
  - 若 `with_faithfulness` 且 LLM 可用：调 `RAGAnswerGenerator.answer` 取 `metrics.citation_rate` 作为该条 faithfulness；聚合均值。
  - 返回 `{precision@k, recall@k, faithfulness(可选), n, per_item:[...]}`。
- `load_gold(payload) -> List[dict]`：校验上传 gold 结构（每项需 `query`；`expected_chunk_ids`/`expected_answer` 可选），非法 → 抛 `ValueError`。

## 5. 配置（`app/core/config.py`）

在 `EMBEDDING_MODEL` 行之后追加（保留上下文空行）：
```python
    RAG_LLM_PROVIDER: str = "mock"  # RAG 问答生成使用的 LLM provider (deepseek/doubao/qwen/kimi/mock)
    RAG_LLM_KEYS: List[str] = []    # 多 Key 轮询/故障转移；为空则回落该 provider 的单 key
    RAG_TWO_PHASE: bool = False     # 两阶段生成：先引证规划再作答(更精准,延迟更高)
```
复用 `SOPLLMClient` 既有厂商注册表与对应 `*_API_KEY`/`*_BASE_URL`/`*_MODEL` 配置；`RAG_LLM_KEYS` 为该 provider 的**多个 key 列表**（env 用逗号分隔），为空时回落到该 provider 的单 key（`DEEPSEEK_API_KEY` 等）。`SOPLLMClient` 扩展 `keys` 参数以支持多 key 轮询 + 故障转移。

## 6. 存储

无新表。citations / 答案均为响应体，不落库（gold 评测集为内置 fixture 或请求入参）。

## 7. 端点（`app/api/knowledge_api.py`）

```python
class AskRequest(BaseModel):
    question: str
    project_id: str = ""
    top_k: int = 5

@router.post("/ask")
def ask(req: AskRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    if not req.question or not req.question.strip():
        return ApiResponse.error("请提供问题", code=400)
    gen = RAGAnswerGenerator(service=service)
    result = gen.answer(req.question, project_id=req.project_id or None, top_k=req.top_k)
    return ApiResponse.ok(result)

class EvaluateRequest(BaseModel):
    gold: Optional[List[dict]] = None
    top_k: int = 5
    with_faithfulness: bool = False

@router.post("/evaluate")
def evaluate(req: EvaluateRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    try:
        gold = req.gold if req.gold else RAGEvaluator.DEFAULT_GOLD
        if not gold:
            return ApiResponse.error("gold 为空", code=400)
        ev = RAGEvaluator()
        metrics = ev.evaluate(service, gold, top_k=req.top_k, with_faithfulness=req.with_faithfulness)
        return ApiResponse.ok(metrics)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)
```

**RBAC**：`/ask` 与 `/evaluate` 为只读检索/评估，沿用既有中间件（dev 与 reader/admin 均可调用，不需 admin）。`/ingest`、`/delete` 仍限 admin（不变）。

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| 检索空 / 库无数据 | `answer=""`, `citations=[]`, `degraded:True`, `note:"未检索到相关知识"` |
| `RAG_LLM_PROVIDER=mock` / 无 key | 不调 LLM，返回上下文+出处，`degraded:True` |
| LLM 网络/解析失败（SOPLLMClient 返回 None/抛错） | 捕获 → 降级为上下文+出处，`degraded:True`，不向上抛 |
| 答案含非法 `[n]` | `validate_citations` 剔除，引用率如实反映 |
| eval gold 为空 / 结构非法 | 返回 400 |
| 工具/生成异常 | 内层捕获，返回安全结果，不崩 |

## 9. 测试（全离线、确定性，`tests/knowledge/`）

复用注入式 fake `httpx.Client`（同 `sop_llm_client` 测试模式），远程调用不真发。

1. `test_build_context_groups_by_section`：同/异 section 的 chunk → 上下文按章节归并、分配 `[n]`、citations 含 `section` 与 `offset`。
2. `test_answer_mock_returns_citations_degraded`：`RAG_LLM_PROVIDER=mock` → `answer=""`, `citations` 非空, `degraded:True`。
3. `test_answer_with_fake_llm_returns_cited`：注入 fake `llm_client`（实现 `chat_structured` 返回带 `[1]` 的 answer）→ `RAGAnswerGenerator(llm_client=fake)` → 返回 `answer` + `citations` + `metrics.citation_rate`。
4. `test_validate_citations_strips_invalid`：答案含 `[1][9]`（9 未命中）→ 返回文本仅剩 `[1]`，`citation_rate` 正确。
5. `test_ask_integration`：ingest 样例文档（同临时 DB）→ `RAGAnswerGenerator(service=svc).answer(相关Q)` → `citations` 非空且 top 命中正确 doc_title。
6. `test_section_injection_merges`：同 section 两 chunk → 上下文合并到单一章节标题下。
7. `test_eval_builtin_gold`：内置 fixture → `precision@k`/`recall@k` 计算正确（用已知 expected_chunk_ids）。
8. `test_eval_empty_gold_400`：gold 空 → 400。
9. `test_eval_uploaded_gold`：上传合法 gold JSON → 评估通过；非法结构 → 400。
10. `test_build_system_prompt_subblocks`：`build_system_prompt()` 含角色/任务/上下文契约/引用规则/输出 schema 五块标志文本；各子块为独立常量可单独断言。
11. `test_two_phase_citation_plan`：`RAG_TWO_PHASE=True` + 注入 fake llm（phase-1 返回 `cite_ids`、phase-2 返回 answer）→ 最终 answer 仅引用 plan 中编号，`metrics` 正常。
12. `test_multikeys_failover`：注入 fake client，前几个 key 返回 401/429/402、最后一个成功 → 不抛、返回答案（验证轮询+故障转移命中可用 key）。
13. `test_multikeys_exhausted_raises`：所有 key 均失败 → 抛 `SOPLLMError`（或降级 `degraded:True`，不静默错答）。
14. 全量回归：既有套件无破坏（285 passed 不受影响）。

## 10. 任务拆分（供 writing-plans 参考）

| 任务 | 内容 | 测试 |
|---|---|---|
| T1 | `config.py` 新增 `RAG_LLM_PROVIDER`/`RAG_LLM_KEYS`/`RAG_TWO_PHASE` + `tests/test_config_rag.py` | 1 |
| T2 | `app/services/sop_llm_client.py` 扩展 `keys` 参数：多 key 轮询 + 401/429/402 故障转移 | 12–13 |
| T3 | `app/knowledge/prompts.py`：五块子提示常量 + 组装/两阶段函数 | 10–11 |
| T4 | `app/knowledge/answer.py`：`build_context` + `validate_citations` + `RAGAnswerGenerator`（接入多 key + 细分提示词 + 两阶段） | 2–6, 11 |
| T5 | `app/knowledge/eval.py`：`RAGEvaluator` + 内置 gold fixture | 7–9 |
| T6 | `app/api/knowledge_api.py`：新增 `/ask`、`/evaluate` | 集成 |
| T7 | 全量回归 | 14 |

## 11. 风险与权衡

- **SOPLLMClient 命名**：类名带 "SOP" 但实为通用 OpenAI 兼容客户端；本期直接复用，不重命名（重命名属无关重构，留待专门清理）。
- **faithfulness 依赖 LLM**：`with_faithfulness=True` 且 `RAG_LLM_PROVIDER=mock` 时 faithfulness 退化为不可用（评测返回中省略该字段或记 null）。
- **gold 质量决定评测意义**：内置 fixture 仅供冒烟；真实评估需业务方提供 gold 集。
- **引用校验局限**：只校验 `[n]` 编号是否在 citations 内，不校验语义是否真的支撑（深度 faithfulness 需 NLI/LLM-judge，本期不做）。
- **多 Key 故障转移的边界**：仅对 `401/429/402` 等鉴权/限流/配额错误切换 key；`5xx`/`timeout` 同样可切换（按故障转移统一处理）。所有 key 耗尽才抛错/降级，避免静默错答。
- **两阶段延迟**：`RAG_TWO_PHASE=True` 会发两次 LLM 请求，延迟约翻倍；默认 `False`，仅在引用精准度要求高时开启。
- **SOPLLMClient 多 key 为共享增强**：扩展 `keys` 参数对 SOP AI 段同样生效（向后兼容，单 key 不变）；本期仅 RAG 路径显式配置 `RAG_LLM_KEYS`。
