# 架构去债（Architecture Cleanup）设计文档

- **日期**: 2026-07-08
- **状态**: 设计已确认，待实现
- **策略**: 风险分层、分笔提交（Strategy A，已确认）
- **范围**: bsc-backend 项目（`C:/Users/34216/Documents/New project 3/bsc-backend`）

## 1. 背景与已完成的清理

本设计初稿基于早前的项目检索，列出了四类技术债：死代码/分叉、k8s 配置重复、A/B 两套 business_system 模型、mock_compiler 悬空引用。

**但在设计评审过程中重新扫描项目发现：上述大部分债务已被本轮会话期间的外部改动（"文件漂移"）先行清理。** 已确认完成的部分：

| 原定清理项 | 当前状态 | 证据 |
|---|---|---|
| `app/core/orchestrator.py` 死代码 | ✅ 已移至 `archive/dead_code/` | `archive/dead_code/` 存在；全仓无 `from app.core.orchestrator` 引用（`studio_orchestrator.py` 是另一个合法模块） |
| `app/core/compiler.py`、`pipeline.py`、`mock_compiler.py` | ✅ 已移至 `archive/dead_code/` | 文件已不存在；`retrieval_engine` 全仓零引用 |
| `python-backend/` 孤儿分叉 | ✅ 已移至 `archive/orphan_fork/` | `archive/orphan_fork/` 存在 |
| `k8s/` 与 `deploy/k8s/` 重复 | ✅ 仅剩 `k8s/` | `deploy/k8s/` 已不存在 |
| A/B 两套 business_system 模型统一 | ✅ 已统一为 `ProductionBusinessSystem` | `app/schemas/production_schema.py:193` 定义唯一 canonical `ProductionBusinessSystem(BaseModel)`；`validate_business_system()` 返回它并在 `bsc_pipeline.compile_to_business_system` 中被调用；`BusinessSystemSchema` 仅残留在一条过时注释中 |

因此本设计**仅保留真实存在的剩余债务**，范围较初稿显著缩小。

## 2. 当前真实剩余债务

经全仓引用扫描（`grep -rln` 导入名 + 子串访问双重确认），以下项确为孤儿/冗余：

1. **孤儿目录 `validators/`** — 全仓零引用（无任何 `import validators` / `validators.`）。
2. **孤儿目录 `compilers/`** — 全仓零引用。
3. **孤儿目录 `prompt_library/`** — 全仓零引用（`prompts/` 被 `app/core/prompt_loader.py` 引用，保留；`prompt_library/` 不是它）。
4. **根目录散落脚本 `test_comprehensive.py`** — 本次会话早期遗留的调试脚本，非测试套件一部分（`tests/` 才被 pytest 收集），应移除。
5. **`pytest.ini` 的 `asyncio_mode = auto`** — 配置项触发 `PytestConfigWarning: Unknown config option`（pytest-asyncio 未安装），且全仓无 async 测试。属噪声配置。
6. **`app/schemas/production_schema.py:4` 的过时注释** — 提及已删除的 `business_schema.py` 与 `BusinessSystemSchema`，需更正以反映"当前 `ProductionBusinessSystem` 是唯一 canonical 模型"。

> 说明：`k8s/` 单一配置集保留并正常；本设计对其仅做"是否过期"的轻量核查（见 §3.5），不做结构性改动。

## 3. 实现计划（风险分层，分笔提交）

每段独立 commit，段末跑校验。全局约束见 §4。

### 3.1 段一 · 移除孤儿目录（低风险）

- **动作**:
  ```bash
  git mv validators compilers prompt_library archive/
  ```
  （沿用现有 `archive/` 约定，保留历史、可回滚。）
- **成功标准**: `git mv` 后 `pytest` 仍 62 passed / 2 skipped；`python -c "import app.main"` 无 import 错误；全仓 grep `validators.`/`compilers.`/`prompt_library.` 在 `app/` 内无残留引用。

### 3.2 段二 · 移除根目录散落脚本（低风险）

- **动作**: 删除 `test_comprehensive.py`（未被 git 追踪，属本次会话遗留调试脚本）。
- **成功标准**: 根目录无 `test_comprehensive.py`；`pytest` 不受影响。

### 3.3 段三 · 修复 pytest.ini 噪声配置（低风险）

- **动作**: 删除 `pytest.ini` 第 4 行 `asyncio_mode = auto`（全仓无 async 测试，pytest-asyncio 未安装）。
- **成功标准**: `pytest` 运行不再出现 `PytestConfigWarning: Unknown config option: asyncio_mode`；测试数量与结果不变。

### 3.4 段四 · 更正 production_schema 过时注释（低风险）

- **动作**: 将 `app/schemas/production_schema.py` 顶部注释中"与 business_schema.py 中的 BusinessSystemSchema 不同"等表述，更正为"`ProductionBusinessSystem` 是当前唯一 canonical 业务系统模型，实时链路经 `validate_business_system()` 校验"。
- **成功标准**: 注释与代码现状一致；无功能变更；`pytest` 不变。

### 3.5 段五（可选核查）· k8s 配置时效性（低风险）

- **动作**: 读取 `k8s/deployment.yaml`，确认镜像名/端口（应为 uvicorn `:8000`，对应 `APP_PORT=8000`、`HOST` 配置）。若引用过期镜像或端口，更新为当前值；若已正确则不动。
- **成功标准**: `k8s/deployment.yaml` 与应用实际监听端口一致；不引入结构性变更。

## 4. 全局约束与校验

- **真实 LLM 链路不受影响**：`LLM_PROVIDER` / `ANALYSIS_PROVIDER` / `GENERATION_PROVIDER` 路由逻辑与 `.env` 均不改动。
- **每段结束必跑**：`pytest -q`（期望维持 **62 passed, 2 skipped**）。
- **可选真实链路冒烟**：若 `BSC_REAL_E2E=1` 且两 key 真实，跑 `pytest tests/test_real_e2e.py -v` 确认 6 格式导出 happy path 仍绿。
- **每段独立 commit**：便于 review 与回滚；commit message 遵循现有 `fix(...)` / `chore(...)` 风格。

## 5. 不在范围内（已确认完成或刻意排除）

- 删除 `orchestrator.py` / `compiler.py` / `mock_compiler.py` / `python-backend/`：已在 `archive/` 完成。
- k8s 重复配置合并：仅 `k8s/` 存在，无需合并。
- A/B 模型统一：已统一为 `ProductionBusinessSystem`。
- 任何新功能、前端改动、业务逻辑修改：本设计纯去债，不增不改行为。

## 6. 验收标准（Done Definition）

- [ ] `validators/`、`compilers/`、`prompt_library/` 已移入 `archive/`，全仓无残留引用。
- [ ] 根目录无 `test_comprehensive.py`。
- [ ] `pytest.ini` 无 `asyncio_mode`，`pytest` 无 config 警告。
- [ ] `production_schema.py` 注释与现状一致。
- [ ] `pytest` 全套 **62 passed, 2 skipped** 维持绿灯。
- [ ] （可选）真实 LLM 冒烟通过。
