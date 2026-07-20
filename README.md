# BSC Studio — Business System Compiler

AI 驱动的企业级业务系统自动设计平台。输入 PRD（产品需求文档），自动输出完整的业务系统设计方案。

## 核心能力

- **智能编译**：6 阶段 LLM Agent Pipeline（业务理解 → SOP 流程 → 风险评估 → 战略分析 → 优化建议 → 报告组装）
- **多模型支持**：DeepSeek / 豆包 / 通义千问 / Kimi / 元宝 / Ollama / 本地模型
- **多格式导出**：JSON / HTML / PPT / Word / PDF / Excel / Markdown
- **RAG 知识库**：内置检索增强生成系统，支持文档检索问答
- **交互式工作台**：React 前端 + Studio 自然语言交互 + 技能市场
- **生产就绪**：Docker / K8s 部署、健康检查、Prometheus 监控、认证鉴权

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 启动开发服务器（mock 模式无需 Key）
LLM_PROVIDER=mock uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 创建一次可查询、可订阅的业务编排任务
curl -X POST http://localhost:8000/api/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"idea": "零售电商系统：提升用户转化率并优化供应链效率"}'
```

## Orchestrator lifecycle

- `POST /api/orchestrate` creates a queued analysis and returns status/event URLs.
- `GET /api/orchestrate/{session_id}` returns the persisted lifecycle state.
- `DELETE /api/orchestrate/{session_id}` requests cooperative cancellation.
- `GET /api/orchestrate/{session_id}/events` streams ordered SSE events and closes at the terminal event.
- `GET /api/orchestrate/dashboard/{session_id}` returns the completed analysis projection.

The `/api/orchestrate/stream?session_id=...` endpoint is a temporary compatibility alias.
`/bsc/*` remains available only as a deprecated compatibility surface through
2026-12-31; new product integrations must use `/api/orchestrate`.

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | Python 3.11 + FastAPI |
| AI/LLM | LangChain + 多 Provider 适配（DeepSeek/豆包/千问/Kimi/元宝/Ollama） |
| 数据模型 | Pydantic v2 + pydantic-settings |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 缓存 | L1 内存 + L2 Redis |
| 异步任务 | Celery + Redis |
| 前端 | React 18 + TypeScript + Vite + Tailwind |
| 可视化 | ECharts + ReactFlow |
| 部署 | Docker + docker-compose + Kubernetes |

## 项目结构

```
app/
├── agents/        # LLM Agent（BU/SOP/Risk/Strategy/Optimization/Composer）
├── api/           # FastAPI 路由（22 个模块）
├── chains/        # LangChain 技能链（8 个）
├── core/          # 核心服务（Pipeline/Config/LLM/Document/Parser）
├── engines/       # 本地计算引擎
├── knowledge/     # RAG 知识库系统
├── schemas/       # Pydantic 数据模型
├── orchestrator/  # 新版编排器
├── exporters/     # 多格式导出层
└── services/      # 服务层
src/               # React 前端
tests/             # 测试（93 个文件）
```

## 文档

- `DEPLOY.md` — 部署指南
- `bsc-backend-MODELS.md` — 数据模型分析报告
- `plans/` — ECC 分析产出（架构蓝图、API 审查、Agent 评估等）
- `.tours/` — CodeTour 代码走查引导

## License

MIT
