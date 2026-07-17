# 方案 A — 编译器接入方法论库 + 产物可溯源引用

> 计划日期：2026-07-17
> 分支：`feat/methodology-citations`（从 master 切出，保护用户其它未提交改动）
> 方法论：TDD（red→green），每任务含完整代码 + pytest 命令，复用既有 BaseAgent / KnowledgeService / RAG citation 形态
> 参考：`docs/awesome-llm-apps-integration-analysis.md` 方案 A；`app/knowledge/answer.py`（build_context / validate_citations）

---

## 0. 用户体感（为什么做这个）

现在编译器生成 SOP / 业务架构时，是**凭 LLM 记忆猜方法论**——你无法知道某条 SOP 步骤到底依据哪份方法论文档、哪一段。产物是"AI 说的"，不可核验，也无法追责。

做完这一步后：
- 编译器在生成 SOP / 业务架构时，**实时检索方法论库**（你项目里已上传的方法论文档）；
- 产物里每条建议都带 `source_ref`（指向 `文档标题 + 章节 + 段落编号`），可一键溯源；
- 多出来的"引用覆盖率"指标，让你一眼看出这条 SOP 是"有据可查"还是"拍脑袋"。

这正好是方案 B（Risk=Constraint）的**证据底座**——约束检查未来要查方法论，先把检索通道打通。

---

## 1. 真实现状核对（实测，非假设）

| 事实 | 证据 |
|------|------|
| 方法论库是生产级 RAG，但**编译器完全没接** | `grep -rn "app.knowledge"` 在 `app/orchestrator/` 下 **0 匹配** |
| 检索已带 provenance | `KnowledgeService.retrieve()` 返回 chunk dict：`chunk_id / content / section / idx / score / doc_title / domain` |
| 引用机制已存在，但只在 `/knowledge/ask` 内部 | `answer.py::build_context()` 产出 `citations[{index,chunk_id,doc_title,section,offset,score,snippet}]`；`validate_citations()` 校验 `[n]` |
| 编译器 agent 覆写 `run()` 自行拼 prompt | `SopBuilderAgent.run(business_model,_engine,context,fix_instructions)` 直接 `llm_service.chat(...)` |
| `retrieve()` 强隔离：`project_id` 必填，否则返 `[]` | `service.py:251-252` |

**结论**：脚手架齐全，方案 A 是"接线 + 契约"，不是"造轮子"。风险低。

---

## 2. 范围（YAGNI）

**包含（MVP）**：
- 检索桥：编译器 agent 可调 `KnowledgeService.retrieve(project_id, query)` 拿带 provenance 的 chunks
- 接入 **2 个最具方法论依赖的 agent**：`sop_builder` + `business_architect`
- 产物带 `source_ref`（每条建议指向 chunk_id）
- 引用校验 + 覆盖率指标（`citation_coverage`）
- 优雅降级：项目无方法论文档时，不报错、不挂引用

**不包含（留给其它方案）**：
- 前端渲染引用 UI（方案 D）
- risk agent 接入（后续，复用同一桥）
- 把引用并入哈希审计链（方案 E）
- 检索 query 的智能生成（先用 business_model 启发式，后续可升级）

---

## 3. 任务清单（TDD）

### Task 1 — 方法论检索桥 `MethodologyBridge`
- 新增 `app/orchestrator/methodology.py`：
  - `class MethodologyBridge`：`__init__(self, service=None)`（DI，可注入 FakeRetriever）
  - `retrieve(project_id, query, top_k=5) -> dict`：
    - 调 `service.retrieve(query, project_id=project_id, top_k=top_k)`
    - 复用 `answer.build_context` 的 citations 形态，产出：
      - `context_block: str`（拼进 user_prompt 的"方法论依据"文本）
      - `citations: list[dict]`（每项 `{index, chunk_id, doc_title, section, offset, snippet, score}`，供校验）
    - 无结果 → `{"context_block":"", "citations":[]}`
- 测试 `tests/orchestrator/test_methodology_bridge.py`：
  - 用 FakeService 返回 2 个带 provenance 的 chunk → 断言 `citations[0]` 含 `chunk_id/doc_title/section/offset`
  - 空结果 → 断言 `context_block==""` 且 `citations==[]`
- 命令：`venv/Scripts/python.exe -m pytest tests/orchestrator/test_methodology_bridge.py -q`

### Task 2 — SopBuilderAgent 接入检索 + source_ref
- 改 `app/orchestrator/agents/sop_builder.py`：
  - `run(self, business_model, _engine=None, context=None, fix_instructions=None, project_id=None)`
  - 若 `project_id`：用 `_derive_query(business_model)` 取查询词；`bridge.retrieve(project_id, query)` 拿 `context_block`+`citations`；预置到 `user_prompt` 顶部（"## 方法论依据\n{context_block}"）
  - `system_prompt` 增加："每个 sop 项必须含 `source_ref: [<chunk_id>, ...]`，只能引用上方方法论依据里出现的 chunk_id；无依据可引时 `source_ref: []`"
  - 保存 `_last_citations = citations` 供校验
  - 新增 `_derive_query(business_model)`：从 domain + 前 N 个 process 名拼查询（启发式，纯函数，可单测）
- 测试 `tests/orchestrator/test_sop_methodology.py`：
  - FakeLLM 返回 `sops` 每项带 `source_ref:["c1"]` → 断言 result 透传 `source_ref`，且 `source_ref` 均在 retrieved chunk_ids 内
  - `project_id=None` → 不走检索（无"方法论依据"块）
- 命令：`venv/Scripts/python.exe -m pytest tests/orchestrator/test_sop_methodology.py -q`

### Task 3 — BusinessArchitectAgent 接入（同模式）
- 改 `app/orchestrator/agents/business_architect.py`：`run(..., project_id=None)` + 检索注入 + `source_ref` 指令（按该 agent 的 element 结构：process/role/rule 每项带 `source_ref`）
- 测试 `tests/orchestrator/test_ba_methodology.py`：同 Task 2 形态
- 命令：`venv/Scripts/python.exe -m pytest tests/orchestrator/test_ba_methodology.py -q`

### Task 4 — 引用校验 + 覆盖率指标
- `app/orchestrator/methodology.py` 加：
  - `validate_source_refs(generated_items, citations) -> dict`：
    - 复用 `answer.validate_citations` 思路：统计有 `source_ref` 且全部命中 `citations` chunk_id 的 item 比例
    - 返回 `{coverage: float, flagged: [item_refs with missing/bad refs]}`
  - 在 `sop_builder` / `business_architect` 的 `run()` 末尾调用，把 `citation_coverage` 写进返回的 dict（`result["_citation_coverage"]`）
- 测试：
  - 全部命中 → `coverage==1.0`，`flagged==[]`
  - 有 item `source_ref` 指向未检索 chunk → `coverage<1.0`，进 `flagged`
  - item 无 `source_ref` 字段 → 计入"未覆盖"
- 命令：`venv/Scripts/python.exe -m pytest tests/orchestrator/test_methodology_bridge.py -q`（追加用例）

### Task 5 — Pipeline 接通 project_id
- 改 `app/orchestrator/engine.py`：在调用 `sop_builder` / `business_architect` 处传入 `project_id`（从 `ProjectDraft` 取，需确认 engine 持有 project 对象；若无则经 `context` 透传）
- 测试 `tests/orchestrator/test_methodology_e2e.py`：
  - 用 seeded 项目（含方法论文档）跑 golden pipeline → `result["sop"]` 带 `source_ref` 且 `citation_coverage>0`
  - 用无文档项目跑 → 不报错，`sop` 无 `source_ref`（优雅降级）
- 命令：`venv/Scripts/python.exe -m pytest tests/orchestrator/test_methodology_e2e.py -q`

### Task 6 — 全量回归 + 收尾
- `venv/Scripts/python.exe -m pytest tests/constraint tests/orchestrator tests/agent -q` → 全绿（守住现有门槛）
- 更新本文档 Execution Log + 偏差记录
- 写 memory（追加 `.workbuddy/memory/2026-07-17.md`）

---

## 4. 关键设计决策

- **复用而非新建**：citation 形态直接对齐 `answer.build_context` 的 dict 结构，未来方案 E 合并审计链时零改造成本。
- **依赖注入**：`MethodologyBridge(service=...)` 可注入 FakeRetriever，测试不依赖真实 SQLite / embedding。
- **优雅降级**：`project_id` 为空或无文档 → 检索返空 → 不挂引用、不报错。生产路径（有项目）才生效。
- **不碰 master**：全程 `feat/methodology-citations` 分支，合并需你点头。

---

## 5. 预期交付

- `app/orchestrator/methodology.py`（桥 + 校验）
- `sop_builder.py` / `business_architect.py` 接检索 + source_ref
- `engine.py` 透传 project_id
- 5+ 测试文件，全绿
- 编译器产物从"AI 说的"升级为"有据可查"

---

## 6. Execution Log（Subagent-Driven，2026-07-17）

分支 `feat/methodology-citations`（从 master `6ca8a92` 切出，保护 258 个未提交改动）。

| 提交 | 任务 | 内容 |
|------|------|------|
| `a40614d` | plan | TDD 计划文档 |
| `fa98471` | Task 1 | MethodologyBridge + provenance citations + 测试（2 passed） |
| `93b745d` | Task 2 | SopBuilderAgent 接检索 + source_ref（2 passed） |
| `23d4892` | Task 3 | BusinessArchitectAgent 接检索 + source_ref（2 passed） |
| `25f31cc` | Task 4 | validate_source_refs + _citation_coverage 指标（10 passed） |
| `9393a64` | Task 5 | engine 透传 project_id + golden e2e（8 passed） |
| `50b9757` | fix | **覆盖率指标存活修复**（见偏差 1） |

**全量回归**：`venv/Scripts/python.exe -m pytest tests/constraint tests/orchestrator tests/agent -q` → **53 passed**（A 前 41）。

### 偏差 / 发现
1. **覆盖率指标会被引擎丢弃（已修 `50b9757`）**：Task 4 的 subagent 把 `_citation_coverage` 放在 `run()` 返回值的**顶层**，而引擎 `state["sop"] = out.get("sop")` 只取子段 → 指标在生产里丢失（类比 B 那次风险清单被丢）。修复：agent 改为把 `_citation_coverage` **内联进 `sop`/`business_model` 子段**，引擎入库即保留。e2e 测试本就按子段位置断言，故一并修正 sop 单测断言位置。
2. `derive_methodology_query` 入参不同：sop_builder 用 `business_model`，business_architect 用 `project`（其 `run` 标准入参是 project dict）——两处均合理，保持。
3. `KnowledgeService.retrieve(project_id, query, ...)` 形参顺序与计划示例不同；桥统一用**关键字参数**调用，兼容真实/Fake 服务。
4. `ProjectDraft` 无 `project_id` 字段 → 引擎以 `session_id` 作为知识库 `project_id`（已知简化；生产后续显式传 `knowledge_project_id`）。
5. 仅动 `feat/methodology-citations` 分支；258 个无关 dirty 文件始终未暂存、未丢失。
