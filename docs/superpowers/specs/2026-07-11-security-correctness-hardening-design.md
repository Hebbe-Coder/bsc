# Round 3 安全 & 正确性加固 — 设计文档

- **日期**：2026-07-11
- **分支**：`feature/security-correctness-hardening`（基于 `feature/knowledge-hardening-round2` HEAD 派生）
- **方法**：单 feature 分支 + subagent-driven（TDD）+ 双评审（规格合规 + 代码质量/安全），沿用 Round 2 已验证流程
- **可观测性**：本轮不新增指标，保持轻量（沿用现有 `app/knowledge/metrics.py` 进程内单例即可）

---

## 0. 背景与范围决策

对知识库（RAG）子系统之外的模块做了一次技术债扫描（排除已加固的 `app/knowledge/`），按"风险 × 影响"排出了 TOP 8。用户选择 **方案 A：聚焦安全 + 正确性三大 HIGH**，范围可控、一轮可合。

三个 HIGH（均已读代码核实，非误报）：

1. **SOP 报告 HTML 注入 / XSS** —— `app/engines/sop_report_engine.py`
2. **`/dashboard` 与 `/output` 免鉴权暴露** —— `app/middleware/auth.py` + `app/main.py`
3. **编译"部分失败伪装成功"** —— `app/core/async_pipeline.py` + `app/api/bsc_api.py`

### 设计决策（用户确认）

- **Q4（鉴权收口策略）= A（意图）**：`/dashboard` 与 `/output` 都要求 admin API_KEY。但**字面"移出白名单"不可行**——`/dashboard` 是 StaticFiles 挂载的 UI（浏览器无法对其自动带 `Authorization`），`/output` 是前端 `<a href>` 直接打开的静态文件（同样无法带 Bearer）。故按**安全意图**落地为：
  - `/dashboard` 的 **JSON API** 用路由级 `Depends(require_admin)` 强制鉴权（白名单仍放行 UI 外壳，保证 UI 可加载）；
  - `/output` 改为**受保护下载端点** `GET /api/files/{filename}`，前端下载走带 token 的 URL。
- **Q5（编译上报语义）= A**：任一 Agent 阶段失败 → 返回 `ApiResponse.error(code=2001, ...)`，不再 `success:True`。这是对"永远 200 success"语义的 **breaking 修正**（预期内），前端若依赖该假设需同步调整（设计已标注）。

---

## 1. WS1 — SOP 报告 HTML 注入 / XSS 收口（HIGH #1）

### 根因
`app/engines/sop_report_engine.py` 的 `export_to_html`（:1408）与 `preview` 渲染（:492）用 f-string / `.format` 把 LLM 回灌字段（核心目标 `{obj}`、步骤名、职责、风险、finding 等，如 :1513 `{obj}`）直接拼进 HTML。全文件**无 `html.escape`**（仅 `re.escape` 用于正则）。经 `/sop-report/export`、`/preview` 渲染 → 存储型 / 反射型 XSS。导出层其他引擎已做转义，此处不一致。

### 修复
- 在引擎内新增统一 helper：
  ```python
  import html as _html
  def esc(s) -> str:
      return _html.escape(str(s), quote=True)
  ```
- 对所有 **LLM 派生字段值**在拼 HTML 前调用 `esc()`（**只转义字段值，不转义模板固定结构标签**，避免破坏既有合法布局）。
- 覆盖 `export_to_html` 与 `preview` 两条渲染路径。
- 纯文本 / Markdown 导出不受影响（它们不经过 HTML 上下文）。

### 受影响文件
- `app/engines/sop_report_engine.py`（修改）

### 测试
- 新增 `tests/test_ws1_sop_xss.py`：
  - 构造含 `<script>alert(1)</script>` 的 PRD / 报告内容 → 跑 `export_to_html` → 断言输出含 `&lt;script&gt;` 且**不含裸 `<script>`**。
  - 覆盖 `preview` 路径同样的断言。

---

## 2. WS2 — `/dashboard` 与 `/output` 鉴权收口（HIGH #2）

### 根因
- `app/middleware/auth.py` 的 `_WHITELIST_PATHS`（:15-25）含 `/dashboard/`、`/output/`，前缀匹配 → 二者完全跳过鉴权。
- `app/api/dashboard.py`（:8 `router = APIRouter(prefix="/dashboard", ...)`）**零鉴权依赖** → 看板指标 / 调用日志接口任何人可无密钥访问。
- `app/main.py:230` `app.mount("/output", StaticFiles(directory=_output_dir))` 直挂 → `output/` 下生成的 `PRD_*.docx / *.pptx / *.html` 可任意下载。
- 下载模型：各 export 端点（`sop_report_api.py`、`bsc_api.py`、`pm_report_api.py`、`asset_agent.py` 等）写文件到 `output/`，返回形如 `/output/report_{ts}.html` 的路径，前端用 `<a href>` 直接打开。

### 修复（按 Q4=A 意图落地）

#### WS2a — `/dashboard` API 路由级鉴权
> ⚠️ **不能复用知识库专属的 `require_admin`**（`knowledge_api.py:20`）：它读 `request.state.knowledge_role`，而该字段**仅由 AuthMiddleware 在 `/knowledge/*` 路径设置**（auth.py:59）。`/dashboard/*` 是非知识库路径，中间件不会设该字段 → 若复用 `require_admin`，合法 admin key 也会被误判 403。故新增一个**通用 admin key 校验依赖** `verify_admin_key`，直接校验 `Authorization: Bearer <settings.API_KEY>`（与中间件非知识库分支 auth.py:64-82 逻辑一致，且 dev 模式 `API_KEY` 未配置时放行）。

- 新增共享依赖（置于 `app/api/deps.py` 或 `app/core/auth_deps.py`）：
  ```python
  def verify_admin_key(request: Request) -> bool:
      auth = request.headers.get("Authorization", "")
      if not auth.startswith("Bearer "):
          raise HTTPException(status_code=401, detail="未提供认证信息，请在请求头添加 Authorization: Bearer <API_KEY>")
      api_key = auth[7:]
      if not settings.API_KEY:
          if not settings.is_production:
              return True  # 开发模式放行
          raise HTTPException(status_code=500, detail="服务配置不完整")
      if not hmac.compare_digest(api_key, settings.API_KEY):
          raise HTTPException(status_code=401, detail="无效的API密钥")
      return True
  ```
- `app/api/dashboard.py` 的 router 增加依赖：
  ```python
  router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(verify_admin_key)])
  ```
- **白名单 `/dashboard/` 保持不变** → 请求能到达路由；路由级依赖对全部 `/dashboard/*` JSON 接口强制 admin key。静态 UI 外壳（html/css/js，由 StaticFiles 挂载、不经 router）保持可加载（外壳无数据，可接受）。
- *偏离字面 A 的理由*：纯白名单移除会让 `/dashboard` UI 与 `/output` 浏览器下载直接打不开，且达不到"数据受保护"的真正目标；路由依赖达成同一安全意图且可用。

#### WS2b — `/output` 受保护下载端点
- 移除 `app/main.py:230` 的 `StaticFiles("/output")` 直挂。
- 新增受保护下载端点（建议放 `app/api/files_api.py` 或在 `bsc_api.py` 内）：
  ```python
  @router.get("/api/files/{filename}")
  async def download_file(
      filename: str,
      request: Request,
      token: Optional[str] = Query(None),
      _admin: bool = Depends(verify_admin_key),  # 同时接受 Bearer 与 ?token= （依赖内部读 query）
  ):
      # 路径穿越防护：仅允许 basename，解析到 output/ 下
      safe = os.path.basename(filename)
      path = os.path.join(_output_dir, safe)
      if not os.path.isfile(path):
          raise HTTPException(status_code=404, detail="文件不存在")
      return FileResponse(path, filename=safe)
  ```
  > 说明：`verify_admin_key` 同时支持 `Authorization: Bearer <key>` 与 `?token=<key>` 两种等价传入（依赖内部从 `request` + `Query` 读取），因此浏览器 `<a href="/api/files/x.html?token=<admin_key>">` 下载可正常工作。
- 各 export / asset 端点返回的下载 URL 改为 `/api/files/<filename>`，前端下载时在 URL 附 `?token=<admin_key>`（或由前端 `fetch` 带 `Authorization`）。`token` 与 `Authorization` 二选一等效（token 仅用于浏览器 `<a>` 下载场景）。
- 路径穿越防护：强制 `os.path.basename`，拒绝 `..` / 子目录。

### 受影响文件
- 新增 `app/api/deps.py`（或 `app/core/auth_deps.py`）：`verify_admin_key` 依赖（支持 Bearer 与 `?token=` 两种传入）
- `app/api/dashboard.py`（router 加 `dependencies=[Depends(verify_admin_key)]`）
- `app/main.py`（移除 `/output` StaticFiles 挂载；确认 `_output_dir` 变量仍可用于下载端点）
- 新增下载端点模块（如 `app/api/files_api.py`）或在既有 router
- 各 export / asset 端点返回 URL 处（`sop_report_api.py`、`bsc_api.py`、`pm_report_api.py`、`app/agents/asset_agent.py` 等）改为返回 `/api/files/...` 形式

### 测试
- 新增 `tests/test_ws2_auth_gating.py`：
  - 无 Bearer 访问 `/dashboard/overview`（或日志接口）→ 401；带 admin key → 200。
  - 无 token 访问 `/api/files/x.html` → 401/403；带 token → 200 且内容正确。
  - `/api/files/../secret` 或 `/api/files/subdir/x` → 被拦截（404 或 400，不得穿越）。

---

## 3. WS3 — 编译部分失败真实上报（HIGH #3）

### 根因
- `app/core/async_pipeline.py:294-305`：并行 Agent 阶段异常被吞成 `status:"failed", result:{}`，仅记日志，`execute()` 继续跑 composer。
- `app/api/bsc_api.py:140` 的 `compile_prd`（异步）与 `compile_prd_sync`（:168，同步）**始终** `return ApiResponse.ok(...)` → 调用方拿到成功信封却内含空 / 残缺阶段，掩盖真实失败。
- `compile_to_business_system_async` 返回结构含 `result["pipeline"]["stages"]`（阶段状态列表，每项有 `"status": "failed"/"success"`），失败信息本就在返回里，只是被顶层 `ok` 掩盖。

### 修复（按 Q5=A）
在两处 compile 入口检测失败阶段：
```python
stages = result["pipeline"].get("stages", [])
failed = [s for s in stages if s.get("status") == "failed"]
if failed:
    agents = ", ".join(s.get("agent", "?") for s in failed)
    return ApiResponse.error(
        code=2001,
        message=f"编译有 {len(failed)} 个分析阶段失败：{agents}",
        data={"stages": stages, "partial_business_system": bs},
    )
# 全部成功才走原 ok 路径
return ApiResponse.ok({...})
```
- `compile_prd` 与 `compile_prd_sync` 都做相同处理（同步版从 `compile_to_business_system_sync` 取 stages，结构一致）。
- `partial_business_system` 仍回传，便于前端展示"部分结果"而非完全空白。

### 受影响文件
- `app/api/bsc_api.py`（`compile_prd` :124 / `compile_prd_sync` :168）

### 测试
- 新增 `tests/test_ws3_compile_failure.py`：
  - mock 一个 Agent 阶段抛异常 → 断言返回 `success:False`、`code==2001`、`data.stages` 含 `failed` 状态。
  - 断言**不再** `success:True`（即破除了"部分失败伪装成功"）。
  - 同步端点同覆盖。
  - 反例：所有阶段成功 → 仍 `success:True`（回归保护）。

---

## 4. 任务拆分（TDD + subagent-driven + 双评审）

| 任务 | 工作流 | 内容 |
|------|--------|------|
| **T1** | WS1 | SOP HTML 转义（加 `esc` helper，覆盖 export_to_html + preview）+ `test_ws1_sop_xss.py` |
| **T2** | WS2a | `dashboard.py` router 加 `verify_admin_key` 依赖（新增 `app/api/deps.py`）+ `test_ws2_auth_gating.py`（dashboard 部分） |
| **T3** | WS2b | 移除 `/output` StaticFiles；新增 `/api/files/{filename}` 受保护下载（token/Bearer + 路径穿越防护）；导出端点改返回 token URL + 测试（output 部分） |
| **T4** | WS3a | `compile_prd` 失败上报（code=2001 + stages + partial_bs）+ `test_ws3_compile_failure.py` |
| **T5** | WS3b | `compile_prd_sync` 失败上报 + 同步测试 |
| **T6** | 收尾前 | 全量回归（目标 0 failed；基线 ~368 passed / 2 skipped + 新增 WS 测试）+ 漂移检查（仅登记漂移文件，不提交） |

每任务：派发实现子代理（TDD）→ 两阶段评审（规格合规 + 代码质量/安全）→ 评审发现的 P0/P1/P2 就地修复 → 提交仅任务相关文件。

---

## 5. 明确范围外（本轮不做）

- MEDIUM 项（留待下一轮）：错误信封双重嵌套（`sop_report_api.py`/`dialog_api.py`/`stream_api.py` 把 `ApiResponse.error().dict()` 当 `HTTPException.detail` 二次包裹）、DB 连接泄漏（`chat_api.py`/`dialog_api.py` 每请求 `Repository()` 不 `close()`）、同步重 IO 阻塞事件循环、裸 dict / 假数据、`sop_report_engine.py` 2039 行瘦身、`async_pipeline.py:595` 校验告警被 `_` 丢弃。
- `/metrics`（知识库指标端点，已加固子系统的内部端点）维持现状。

---

## 6. 验证标准

- 每个 WS 均有对应集成/单元测试，覆盖"攻击/失败输入 → 正确拒绝/上报"。
- 全量 `pytest` 0 failed（含既有 ~368 passed/2 skipped + 本轮新增）。
- 漂移文件（`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`、本轮新增的 `app/agents/protocol.py` 等未提交本地改动）**不入库**。
- 双评审全部 APPROVED。

---

## 7. 收尾

全部任务完成后，调用 `superpowers:finishing-a-development-branch` 将 `feature/security-correctness-hardening` 合回 `master`（沿用用户在 Round 2 选择的"合并回 master"）。

> **注意（基线状态）**：`feature/knowledge-hardening-round2`（Round 2）当前仍有 16 个提交未合 master，且 T10 全量回归在上轮对话中被中断未捕获结果。建议本轮启动前或合 master 前先完成 Round 2 的 T10 回归与合并，避免两条加固分支长期并行。本设计文档不阻塞 Round 3 执行，但合 master 时应按顺序处理。
