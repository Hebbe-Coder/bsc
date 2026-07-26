# awesome-llm-apps 深度架构解析与 BSC 采用标准

**审计日期：** 2026-07-25
**审计对象：** C:\Users\34216\Downloads\awesome-llm-apps-main.zip
**SHA-256：** 8D6504BB9D5DB7CCB7DA670669D7261077A1313F71BA706F918672B9B656A008
**审计方式：** 完整归档清单、运行时依赖统计、核心实现追踪、离线确定性验证。
**关联文档：** 2026-07-25-awesome-llm-apps-deep-architecture-audit.md

## 1. 结论先行

awesome-llm-apps 不是一个可整体部署或整体引入的 Agent 平台。它是一个由
100 多个相互独立示例组成的学习目录，覆盖 Agent、RAG、MCP、生成式界面、
语音、定时任务和 Agent Skill。其价值不在于引入某一个框架，而在于抽取已被
不同示例验证过的工程决策。

对 BSC 的正确策略是：

1. 继续以 BSC Artifact Graph、项目隔离、权限、MCP 传输、PromptOps、Wiki
   生命周期和 Dynamic SOP 为唯一系统事实来源。
2. 吸收其中五项高价值模式：确定性数据处理、任务级交付验证、正负样本路由
   评测、可见工具轨迹、可回滚的单变量方法改进。
3. 不把 Agno、Google ADK、AG2/AutoGen、LangGraph、CopilotKit、Streamlit
   或示例 MCP 子进程启动器嵌入 BSC 请求路径。
4. Horizon 只作为受治理的信息源适配器，绝不能成为绕开 SourceRecord、
   CitationLink、项目授权和审计的第二套知识库。

这份结论不表示所有案例都具有生产级安全性。归档层面已完整枚举；核心模式已
按源码追踪；未对所有 508 个 Python 文件和 297 个 TypeScript/TSX 文件逐行做
行为或安全证明，不能把这种审计称为“每行代码形式化验证”。

## 2. 证据覆盖

### 2.1 归档与技术栈

压缩包含 2,253 个条目，已核验 SHA-256。归档顶层分布如下：

| 目录 | 条目数 | 主要角色 | BSC 价值 |
| --- | ---: | --- | --- |
| advanced_ai_agents | 683 | 单 Agent、团队、研究、信号情报 | 工作流分层和信息处理 |
| generative_ui_agents | 654 | Next.js、CopilotKit、MCP UI | 运行台与工具可视化 |
| ai_agent_framework_crash_course | 326 | ADK、OpenAI Agents SDK 教程 | 角色、交接、追踪概念 |
| advanced_llm_apps | 234 | 记忆、RAG、优化、微调 | 上下文和检索模式 |
| rag_tutorials | 133 | CRAG、图谱、诊断、混合检索 | 证据、失败分类、可回建索引 |
| starter_ai_agents | 68 | 小型单文件样例 | 不建议直接采用 |
| agent_skills | 55 | Skill、评测、扫描器 | 方法库治理 |
| voice_ai_agents | 32 | 实时语音和语音 RAG | 仅作为未来输入通道参考 |
| mcp_ai_agents | 27 | MCP 客户端与工具路由 | 最小工具集模式 |
| always_on_agents | 17 | 定时观察与投递 | 自动化状态诚实性 |

源文件构成：508 个 Python、204 个 TSX、93 个 TypeScript、55 个 JavaScript、
256 个 Markdown。存在 124 个 Streamlit 文件、57 个 CopilotKit 引用文件、
105 个 Agno 引用文件、52 个 Google ADK 引用文件、59 个 OpenAI Agents SDK
引用文件。这些数字证明它是多运行时目录，而不是可升级的单一产品。

### 2.2 运行时边界

| 运行时 | 主要用途 | 不能直接带入 BSC 的原因 |
| --- | --- | --- |
| Streamlit | 快速样例 UI | 状态通常在 session_state 或进程内，无法满足 BSC 多项目审计 |
| Agno | 工具型 Agent | 示例普遍将模型、工具、状态和展示混合在单应用中 |
| Google ADK | 教程和 Skill 优化 | 依赖专属会话模型，示例使用 InMemorySessionService |
| OpenAI Agents SDK | handoff、trace 教学 | 交接并不等于 BSC 的权限、决策和 Artifact 约束 |
| AG2/AutoGen | 角色式研究示例 | JSON 用正则解析且无持久证据 |
| LangGraph/Deep Agents | 研究图和文件工作流 | 示例 checkpoint 和文件系统都在内存或演示目录 |
| CopilotKit/AG-UI | 工具调用可视化 | 前端本地状态不是运行真相 |
| MCP SDK | 本地 stdio 工具连接 | 示例会临时启动 npx 包并继承环境变量 |

## 3. 最值得学习的架构

### 3.1 Advisor - Orchestrator - Worker 是职责分离，不是多模型堆叠

agent_skills/advisor-orchestrator-worker 定义了一条清晰的控制循环：

1. 编排者先写出交付物和可检查的成功标准。
2. 强模型 Advisor 只审查拆分、风险和最终质量，不承担执行。
3. Worker 在隔离临时目录中执行单一简报。
4. Verifier 必须运行真实命令或读取真实产物，不能以“回调未抛异常”替代验证。
5. 失败、重试、模型回退和升级决策形成可见台账。

其真正值得采用的是“交付物验证优先于传输成功”。BSC 已将这一规则映射为：

Mission/Decision -> Dynamic SOP 任务 -> 授权 Capability -> Artifact Graph
产物 -> TaskVerificationArtifact -> verified 或 failed。

禁止照搬的部分：

- Skill 建议通过 agy 和 claude CLI 调度外部模型，且 Worker 参数包含
  dangerously-skip-permissions。
- 状态板是普通文件，不具备项目权限、恢复、审计事务或产物血缘。
- 外部 Worker 的出站数据、费用、隔离、凭据和速率没有 BSC 所需的治理合同。

### 3.2 Self-Improving Skill 的正确核心是单变量实验

self-improving-agent-skills/backend/adk_optimizer.py 实现：

baseline -> 执行测试场景 -> 分析最差失败 -> 单次定向修改 -> 重评分 ->
仅在得分提高时保留。

它使用 Pydantic schema 输出 FailureAnalysis 和 SkillMutation，保留 mutation
log，并通过 SSE 向界面推送 baseline、experiment_start、experiment_result 和
complete。这些都是好的产品交互。

不能直接采用其“得分增加即发布”的决策：

- 同一模型系既生成场景、模拟 Skill、评分、诊断又修改内容，评测不独立。
- InMemorySessionService 和 FastAPI 模块级 sessions 在重启后丢失。
- API key 在请求体进入服务，CORS 为通配符。
- 没有项目隔离、版本冲突、负样本、保留集、人工门禁、回滚和成本证据。

BSC 中的等价能力必须是：

MethodProposal -> MethodRevision -> MethodEvaluation -> MethodGate -> 发布或回滚。

每次实验须持久化 baseline、训练样本、保留样本、负样本、模型与费用、变更
diff、评审决定、发布目标和回滚 revision。一次实验只能产生一个有边界的修改。

### 3.3 多 Agent 的三个层次

| 模式 | 示例 | 可学习点 | BSC 替代实现 |
| --- | --- | --- | --- |
| 路由交接 | OpenAI SDK handoffs | 专家边界、结构化交接输入、回调 | CapabilitySelectionArtifact 与任务输入契约 |
| 顺序研究 | AG2 Adaptive Research Team | triage -> local/web -> verifier -> synthesis | Dynamic SOP 任务、证据状态和引用门禁 |
| 信任展示 | trust_gated_agent_team | 角色准入检查、哈希链动作记录 | 项目角色和授权决定，Artifact Graph 负责持久审计 |

AG2 示例的不足很具体：local search 只是词重叠；模型 JSON 通过正则提取；
verifier verdict 为 insufficient 时仍可能要求 synthesizer 输出答案；证据只在
请求内存中存在。BSC 必须让“证据不足”成为可返回结果，而不是被流畅回答掩盖。

trust_gated 示例的 SHA-256 链可用作篡改可见记录的教学，但它的信任分数是手工
设定且重跑即重建。数值信誉不能授予 BSC capability，授权只能来自项目范围、
用户角色、Mission 和任务绑定 Decision。

## 4. Horizon 和外部信息采集

### 4.1 DevPulse 的合理分层

DevPulse AI 采用的流水线非常适合 Horizon 适配层：

适配器抓取 -> SignalCollector 归一化/去重 -> RelevanceAgent ->
RiskAgent -> SynthesisAgent -> digest。

五个适配器使用公开接口或 RSS：GitHub repository search、arXiv Atom API、
HackerNews Algolia、HuggingFace models API、Medium/工程博客 RSS。抓取有 10 至
15 秒 timeout；SignalCollector 以 source:id 做确定性去重；相关性和风险使用
低成本模型，综合阶段才使用强模型。这个“机械步骤不用 Agent、判断步骤才用
模型”的原则应该成为 BSC 默认规范。

### 4.2 DevPulse 不足与 BSC 目标合同

| DevPulse 行为 | 生产风险 | BSC 必须补足 |
| --- | --- | --- |
| 网络异常打印后返回空数组 | 用户看不到源失败，可能把不完整采集当完成 | SourceCaptureAttempt 记录状态、HTTP 类别、重试、失败原因 |
| 只保留摘要和元数据 | 原文与证据链不可复核 | 不可变 SourceRecord、原始正文/附件 hash、抓取时间 |
| source:id 去重 | 同文不同源、URL 变化不能识别 | canonical URL、正文 hash、相似内容候选、人工合并 |
| 模型和 heuristic 结果均放同字段 | 把降级评分误作模型判断 | assessment_provenance: deterministic/heuristic/model |
| relevance * risk 排序 | 排序被误当发布判断 | 仅作为阅读排序，发布仍需引用与评测门禁 |
| 没有来源信誉策略 | RSS 和论坛内容与一手资料等价 | SourcePolicy: allowlist、authority、内容类型、保留期 |

Horizon 的 BSC 接入应该产出 SourceRecord，而不是直接产出 WikiPage 或 SOP：

Horizon/公开源 -> CaptureAttempt -> Raw SourceRecord ->
去重候选 -> 证据评估 -> WikiProposal -> 引用图校验 -> 发布。

这样在没有额外私钥时仍可以抓取公开信息；需要付费检索、私有账号、受限网站或
LLM 总结时，必须显式配置对应运行时密钥和出站数据策略，绝不能假装已完成。

## 5. RAG、知识图谱与知识库自生长

### 5.1 Corrective RAG

corrective_rag 使用 LangGraph 实现 retrieve -> grade_documents ->
generate，若文档被判为不相关，则 transform_query -> web_search ->
generate。可复用的不是它的共享 Qdrant collection，而是以下分支语义：

- 已检索证据满足问题：仅用本地证据回答。
- 证据不够：记录为何不够，再升级为受政策控制的外部检索。
- 外部检索失败：保留失败和缺口，不生成无证据结论。

示例会删除并重建名为 rag-qdrant 的 collection，因此绝不能作为 BSC 的索引
管理实现。BSC 的检索索引必须能从项目内不可变 SourceRecord 重建，并与权威
Wiki/数据库状态分离。

### 5.2 Knowledge Graph RAG with Citations

knowledge_graph_rag_citations 提供 Entity、Relationship、Citation 和
AnswerWithCitations 数据模型，特别适合作为 BSC CitationLink 与知识关系图的
界面参考。其风险同样明确：clear_graph 执行全局 DETACH DELETE，图没有项目
边界，模型提取关系没有审核门禁。

BSC 关系边必须至少带上：

- project_id、source_record_id、source_fragment_id、提取时间和提取方法；
- 关系置信度与状态 proposed/published/retracted；
- 可定位的引用片段，而非只有页面 URL；
- 所属 proposal/revision 和回滚关系。

### 5.3 失败分类库

rag_failure_diagnostics_clinic 给出一组可迁移的 P01-P12 分类：

| 分类 | BSC 用途 |
| --- | --- |
| P01 Grounding drift | 回答或 SOP 结论与引用矛盾 |
| P02 Chunk boundary | 资料切分导致证据断裂 |
| P03 Embedding mismatch | 向量相似度不等于语义相关 |
| P04 Index staleness | 索引与 Wiki/资料权威状态不同步 |
| P05 Router misalignment | 方法、工具或项目上下文路由错误 |
| P06 Long-chain drift | 长 SOP 漏掉早期硬约束 |
| P07 Tool misuse | MCP/API 参数或前置证据错误 |
| P08 Memory defect | 会话、项目或 Vault 上下文丢失/泄露 |
| P09 Eval blind spot | 离线测试通过但真实任务失败 |
| P10 Dependency readiness | Docker/Celery/索引依赖未就绪 |
| P11 Config drift | 环境、密钥或模型配置不一致 |
| P12 Tenant interference | 项目间资料、运行或 Agent 状态串扰 |

BSC 应把失败分类做成结构化 FailureRecord，并连接到 run、task、source、
method revision、retry 决策和最终 resolution，而不是只写进日志文本。

## 6. MCP 采用边界

multi_mcp_agent_router 的优点是一个任务只挂载该专家声明的 MCP 工具，而不是把
所有工具交给总 Agent。它还在 UI 中显示路由结果和工具服务器集合。这应转化为
BSC 的“任务级最小 capability 集”。

示例不能用于生产，因为它：

- 用关键词自动选择 Agent；
- 使用 npx -y 动态下载并启动 MCP server；
- 继承完整 os.environ；
- session 仅在 Streamlit 进程内；
- 无项目授权、server allowlist、出站策略、Artifact 记录或恢复语义。

BSC 只能在既有 HTTP/SSE/stdio MCP transport 上，按 project + mission + task
生成 allowlisted、审计化的工具子集。MCP 工具调用必须把输入、输出引用、失败
和产物 ID 写入 Artifact Graph。

## 7. 自动化与运行状态

always_on_hn_briefing_agent 的最高价值是“默认 dry_run，绝不声称已投递”。
scheduler API 的 dry_run 默认 true，只有 dry_run=false 且配置完整时才调用
delivery。采集、渲染 Brief 和投递分层，测试覆盖空请求、无配置和 Pub/Sub
payload。

它仍然不是调度基础设施：触发端点无认证、无持久 schedule/run/idempotency、
无 retry ledger。BSC 的自动化应沿用 Celery/Redis、KnowledgeSchedule、
KnowledgeRun、幂等键、RunCheckpointArtifact 和失败记录；周蒸馏的最终结果
应同步为可阅读的 Obsidian 文件和可审计的 Artifact，而不是只有发送结果。

## 8. 前端交互与可视化

ai-deep-research-agent 的前端是当前归档最有价值的 UI 参考。它把聊天室和
Workspace 并排，Workspace 独立显示：

1. 可展开的研究计划，状态为 pending/in_progress/completed；
2. 真实生成的文件，支持预览和下载；
3. 来源卡片，明确 found/scraped/failed；
4. 对已知工具的专用卡片，对未知工具才退回 JSON。

BSC 应采用这些“证据优先”的交互原则，但不复用其本地状态实现：

| 参考交互 | BSC 应有的数据来源 |
| --- | --- |
| 计划任务 | DynamicSOPArtifact 和 RunCheckpointArtifact |
| 工具卡片 | MCP/API invocation artifact 与状态事件 |
| 来源卡片 | SourceRecord、CaptureAttempt、CitationLink |
| 文件/Diff | Artifact Graph、WikiProposal、MethodRevision |
| 完成状态 | TaskVerificationArtifact，而非 UI 定时器或回调 |

原示例也有明确问题：React state 存储运行状态、手写 result hash 去重、内存
LangGraph checkpoint、演示文件系统、CORS 通配符。它的“视觉语言”可借鉴，
它的“状态真相”不能借鉴。

对于 BSC，知识工作区必须在一个界面中让用户审阅 Vault 树、原始资料、来源
质量、Wiki Diff、运行轨迹、失败原因、发布决策、健康趋势和关系图；所有可视
数值必须来自 API 返回的项目范围真实记录，不能为填充效果伪造运行。

## 9. Agent Skill 治理是该仓库最成熟的部分

agent_skills/evals 提供四层确定性守卫：

1. strict lint：前置元数据、文件引用、长度和包装约束；
2. scanner：安装诱导、远程 pipe-to-shell、混淆、网络与凭据共现等静态扫描；
3. trigger routing：正样本必须胜过 near-miss 负样本，Skill 描述不能近碰撞；
4. behavior test：对 project-graveyard 的分类、脱敏、状态、复发和 JSON 报告
   做离线断言。

本次复跑结果：

| 命令 | 结果 |
| --- | --- |
| skill_lint advisor-orchestrator-worker --strict | PASS，0 error，0 warning |
| skill_lint project-graveyard --strict | PASS，0 error，0 warning |
| skill_scanner agent_skills | 2 个可发现 Skill，0 critical/warn/info |
| run_trigger_evals.py | 2 个 Skill 的正负样本均通过 |
| test_graveyard.py | PASS，16/16 |

注意：self-improving-agent-skills 没有根 SKILL.md，未被扫描器和路由评测发现。
因此“两个 Skill 通过”不能推导为“整个 agent_skills 目录都通过”。

BSC 方法库和 SOP 路由应实现等价门禁：声明触发词、项目范围、输入/输出合同、
正样本、近似负样本、保留案例、静态安全扫描、人工发布门槛和回滚版本。

## 10. BSC 采用路线

### 已有可确认基础

- 项目范围 Artifact Graph、知识资料和提案生命周期。
- Dynamic SOP、capability selection、任务绑定人工决策和运行 checkpoint。
- MCP HTTP/SSE 与本地服务端的既有授权边界。
- 知识增长、方法评测、Obsidian 输出同步和知识工作区的现有代码基础。
- DBOS 对真实产物的 TaskVerificationArtifact 验证路径。

### P0：先补闭环，不引入新框架

1. SourceCaptureAttempt：使每个 Horizon/公开源抓取都有成功、失败、重试和原始
   hash 记录。
2. SourcePolicy：按项目规定一手源、可信媒体、社区信号和禁止源的权重及保留期。
3. FailureRecord：以上 P01-P12 为起点，强制记录证据、原因、重试决定和修复。
4. 任务级工具子集：根据已批准 Dynamic SOP 任务，而非关键词或通用聊天，选择
   MCP/HTTP capability。
5. 研究运行台：将计划、来源状态、工具调用、Diff、验证结果接入现有
   UnifiedWorkspace，全部使用真实 API 状态。

### P1：受治理的自我改进

1. 给每个 Method/SOP 路由添加正样本、近似负样本和保留集。
2. 实现一次仅一处的 MethodProposal 变更，带 baseline、candidate、成本和
   holdout 结果。
3. 只有通过 non-regression、citation lint 和人工 gate 的 revision 才能发布。
4. 发布后观察真实 run 的失败分类和用户反馈，触发新的提案，而不是直接覆写规则。

### P2：可选的外部 Worker

任何 provider-neutral advisor/worker adapter 都必须先具备：

- 可撤销的项目级出站数据许可；
- 凭据在服务端 secret store，不经浏览器或普通请求体；
- 模型、最大调用数、费用和并发配额；
- 可审计输入摘要和输出产物；
- 隔离执行、取消、超时和两次失败后升级；
- 非生产项目集成测试和 fail-closed 权限行为。

在这些条件满足前，BSC 不启用外部 CLI Worker，也不对用户宣称“多 Agent 已执行”。

## 11. 一个符合 BSC 的端到端实例

以“每周为某项目生成定制行业研究和 SOP 建议”为例：

1. Celery 触发 KnowledgeSchedule，创建 KnowledgeRun，初始状态 queued。
2. Horizon adapters 拉取允许的公开源，逐条写入 SourceCaptureAttempt 和不可变
   SourceRecord；失败源也被记录。
3. 去重服务按 source external id、canonical URL、content hash 形成候选，不删
   原始资料。
4. 低成本模型只生成 relevance/risk 建议，字段带 provenance；强模型只在已选
   证据集合上综合。
5. Wiki compiler 生成 WikiProposal 和 CitationLink，不直接写 published Wiki。
6. 图、引用、陈旧/孤儿检测和方法评测写入 evaluation artifacts。
7. 门禁通过后发布 Wiki revision；不通过则保留 proposal 和 failure reason。
8. SOP compiler 只接收当前项目的已发布知识、AGENTS.md 规则和用户目标，生成
   定制方案及其引用包。
9. BSC Workspace 同屏显示 run、来源、Diff、验证、失败和产物；Obsidian 同步
   可读页面与每周蒸馏文件。
10. 实际交付和用户反馈回流为 SourceRecord/Artifact，供下一轮方法评测使用。

这个循环同时满足“原始资料不被篡改”“知识由证据增长”“方法由真实任务校正”
和“系统不把未执行或未验证描述为完成”。

## 12. 完成标准

awesome-llm-apps 的深度分析不应以“引用了几个案例”结束。BSC 对其采用达到完成
状态的最低证据是：

- 任意知识结论可回到项目范围的原始 SourceRecord 和具体引用片段；
- 任意 Horizon 抓取失败可在界面和 API 中查询，且重试不产生重复资料；
- 任意 SOP 选择可说明命中/排除的 Method 及正负样本证据；
- 任意 Agent/MCP 任务可显示被授权的最小 capability 集、调用记录和真实产物；
- 任意发布可指向评测、Decision、revision 和回滚目标；
- 任意可视化指标来自持久 API 数据，断网、失败和未配置状态不被渲染为成功；
- 自动化在无投递凭据、无来源或失败时诚实显示状态，不伪造“已同步/已发送”。

在上述条目逐项有测试和浏览器验收前，只能说 BSC 已吸收设计原则，不能说已
完成全部生产级融合。

## 13. 本轮落地状态（2026-07-25）

本轮没有把示例仓库当作运行时引入；已把最优先的来源证据闭环落入 BSC 的现有
知识增长边界：

1. `SourceCaptureAttempt` 已作为独立持久账本记录 `captured`、`duplicate`、
   `rejected_by_policy` 和 `projection_failed`。账本仅存来源标识、内容哈希、
   策略快照和索引投影，不复制 `raw_content`。
2. Horizon 导入会把 BSC `KnowledgeRun` 与每条采集尝试关联；通道错误会写入
   `FailureRecord` 和 run event，而不是伪装成“空结果”。
3. `GET /knowledge/projects/{project_id}/capture-attempts`（兼容 growth 别名）
   已按项目权限、run、source 和分页查询账本。运行台将同时读取事件、采集
   尝试和失败记录，并显示策略/投影摘要。
4. Obsidian 文件系统输出测试现在必须显式声明插件信任；仅写入插件路径不会被
   读取或注册为 D 层产物。

验证：后端来源采集、Horizon 失败、Obsidian 输出回流、growth API 和项目级
`SourcePolicy` 共 53 项通过；运行台和 API 客户端 48 项通过；`npm run check` 与
`npm run build` 通过。

### 13.1 项目级 SourcePolicy 已落地（2026-07-25）

`ProjectSourcePolicy` 复用现有 Profile 的 CAS、修订历史和项目权限，不新建第二套
配置存储。它定义一手来源、可信媒体、社区信号和禁止来源前缀，可信/强制分诊的
来源类型，以及四级保留期。每次采集都在 `SourceRecord` 和
`SourceCaptureAttempt` 中保留非敏感策略快照、Profile 修订、权威层级、保留到期
时间与判定原因；禁止来源会留下拒绝审计记录，但不会进入检索投影。Horizon 仍需
项目分诊，却会使用同一份来源权威和保留期策略。

尚未达到“全部生产级融合”的项目包括：方法路由的完整正负样本/保留集门禁；以及
需要出站许可、密钥托管、成本预算与隔离执行的外部 Advisor/Worker 层。它们保留为
后续受治理开发，不会以“已经运行”对外声明。

### 13.2 Method 与 Dynamic SOP 路由评测已落地（2026-07-25）

此前列为待办的路由门禁已进入实际运行路径，而非保留在文档中。Method 更新继续
使用不可变 revision、单一变更维度、正样本/近负样本/隔离 holdout、non-regression
和人工发布门禁。Dynamic SOP 新增 `SOPRoutingEvaluationArtifact`：每个新编译的
Mission 都会持久化 selector 指纹、3 个正样本、2 个近负样本和 2 个隔离 holdout 的
确定性复放结果。

复放会真正经过诊断、CapabilitySelection 和 SOP 编译，但不调用模型、浏览器、
provider 或外部写入。评测工件与 Mission、Diagnosis、Selection、DynamicSOP 形成
Artifact Graph 父子关系；REST、MCP、导出和 Business Control Center 读取同一条
持久记录。只要评测或 holdout 不通过，Mission 不能确认，也不能执行 capability。

首轮复放还找到了实际缺陷：短词 `ai` 原先按子串判断，`constraints` 一类无关文本
会让通用任务被误路由为产品任务。selector 与 compiler 现对短 ASCII 标识使用词边界
匹配，并由回归用例固定。

验证结果：DBOS/API/MCP 相关 21 项通过，前端/API 客户端 11 项通过，`npm run check`
通过。外部 Advisor/Worker 仍未启用；出站许可、服务端密钥、预算、隔离、取消和
非生产集成证据仍是不可跳过的前置条件。
