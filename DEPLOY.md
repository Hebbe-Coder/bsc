# BSC Backend 部署指南

## 1. 环境与依赖
- Python 3.11+（Dockerfile 用 `python:3.11-slim`）
- 依赖见 `requirements.txt`。关键导出依赖：`openpyxl`(XLSX)、`reportlab`(PDF，纯 Python 跨平台)、`python-pptx`(PPT)、`python-docx`(Word)、`weasyprint`(PDF 可选后端)。
- 安装：`pip install -r requirements.txt`

## 2. 配置（环境变量）
- 复制 `.env.example` 为 `.env` 并填入真实值。**切勿提交 `.env` / `.env.private`**（已在 `.gitignore` 中排除）。
- 关键变量：
  - `LLM_PROVIDER`：默认 `mock`。设为 `deepseek`/`doubao`/`qwen` 启用真实 LLM（需对应 `XXX_API_KEY`）。
  - `ANALYSIS_PROVIDER` / `GENERATION_PROVIDER`：按阶段路由不同模型（SOP/Risk/Strategy/Optimization 用 ANALYSIS；BU/Report 用 GENERATION）。
  - `API_KEY`：生产环境必填（开发环境留空放行全部）。
  - `DB_TYPE`：`sqlite`（默认）或 `postgresql`（`DB_URL`）。

## 3. 本地运行
```bash
# 开发模式（mock LLM，无需 key）
LLM_PROVIDER=mock ENVIRONMENT=development uvicorn app.main:app --host 127.0.0.1 --port 8000

# 真实 LLM（需 .env 中已配置且账户有余额）
LLM_PROVIDER=deepseek ENVIRONMENT=production API_KEY=xxx uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- 健康检查：`GET /health` → `{"status":"ok", ...}`

## 4. Docker
```bash
docker build -t bsc-backend .
docker run -d -p 8000:8000 --env-file .env bsc-backend
```
- `docker-compose.yml` 已提供（含 redis / 可选 postgres）。
- 容器内 `HEALTHCHECK` 每 30s 探 `/health`。

## 5. 已知限制（部署前必读）
1. **真实 LLM 账户需有余额**：当前 deepseek / doubao 账户返回 `402 Insufficient Balance`，真实智能分析暂不可用；离线模式使用 PRD 感知的 mock 兜底。
2. **离线 mock 输出不稳定**：管线在多次运行间可能返回空/部分模型（与 402 回退及进行中的代码改动有关）。接真实 LLM 或稳定化 mock 后恢复。
3. **数据模型未完全统一**：管线同时输出 `risk`(单数 dict) 与 `risks`(列表) 等并存字段；导出层已做兼容，但建议后续统一为单一规范模型。
4. **无版本控制历史（本次才初始化 git）**：基线提交见 `git log`。

## 6. 验证导出（6 种格式）
```bash
python -c "
from exporters import export_html, export_xlsx, export_impeccable
from exporters.markdown_exporter import MarkdownExporter
from exporters.word_exporter import WordExporter
from exporters.pdf_exporter import PDFExporter
# 传入合法的 business_system dict 即可产出 html/xlsx/ppt/md/docx/pdf
"
```
