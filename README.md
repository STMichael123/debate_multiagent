# Debate Project

这是一个面向辩论训练场景的多阶段 Agent 项目。当前仓库已经具备完整的本地开发闭环，包括 CLI、Web 工作台、自动化测试、容器化启动、会话持久化以及多条业务链路，但产品定位仍然是可持续迭代的训练原型，而不是面向生产环境的大规模服务。

## 当前产品状态

当前版本已经形成三条可协作的业务链路：

1. 备赛链路：检索资料、整理学理、生成 argument seeds 和 preparation packet。
2. 立论链路：先生成 opening framework，再扩写或流式生成 opening brief，并支持人工导入与稿件点评。
3. 对辩链路：围绕 current phase、clash、证据和 preparation packet 进行 turn、inquiry、closing、coach 和 timer plan。

项目当前可作为一个完整工程仓库使用，适合本地训练、提示词迭代、流程验证和 benchmark 回归。

## 核心能力

1. Web 工作台：支持从首页创建或恢复会话，并在“立论打磨”和“对辩检验”两个阶段之间切换。
2. CLI 调试入口：支持新建会话、恢复历史、逐轮输入、自动保存、查看状态、请求教练和陈词。
3. Opening 工作流：支持生成框架稿、编辑框架、基于框架生成一辩稿、SSE 流式生成、人工注入稿件、稿件教练点评。
4. Match 工作流：支持 turn、inquiry、closing、coach、clash 跟踪和计时规划。
5. Preparation 工作流：支持独立备赛资料包生成，并作为比赛链路的上游输入参与证据合流。
6. 检索增强：本地 dossier 检索为基础，可选追加网页搜索，并对 preparation evidence 与 live evidence 去重合并。
7. 状态持久化：默认使用 JSONSessionStore，配置后可切换到 SQLiteSessionStore。
8. 安全与韧性：Web API 包含 API key 校验、基础限流、安全响应头和流式超时保护。
9. 自动化保障：仓库包含 pytest、ruff、mypy、GitHub Actions CI 和 benchmark 构建/评分脚本。

## 仓库结构

```text
docs/
  agent-backend-learning.md
  technical-design.md
  prompts.md
  evaluation.md
src/
  debate_agent/
    app/
    domain/
    evaluation/
    infrastructure/
    orchestration/
    prompts/
    retrieval/
    storage/
data/
  benchmarks/
  dossiers/
  sessions/
scripts/
tests/
```

## 快速开始

建议使用 Python 3.11+。

安装依赖：

```bash
pip install -e ".[dev]"
```

如需真实 LLM，先复制并填写 `.env.example`。如果没有配置 `OPENAI_API_KEY`，应用会自动回退到本地 fallback 输出，便于继续调试业务流程。

启动 CLI：

```bash
set PYTHONPATH=src
python -m debate_agent.app.cli
```

直接启动 Web：

```bash
set PYTHONPATH=src
uvicorn debate_agent.app.web:app --reload
```

Windows 下更推荐使用仓库脚本，它会先清理旧的 8000 端口和残留 uvicorn 子进程：

```powershell
.\scripts\start_web.ps1
```

无热重载启动：

```powershell
.\scripts\start_web.ps1 -NoReload
```

容器运行：

```bash
docker build -t debate-project .
docker run --rm -p 8000:8000 debate-project
```

启动后打开 http://127.0.0.1:8000。

## 学习入口

如果你想把这个仓库当成一个 agent 项目和 Python 后端项目来学习，建议按下面顺序阅读：

1. [docs/agent-backend-learning.md](docs/agent-backend-learning.md)：面向学习者的详细导读，解释 agent、分层、请求链路、状态管理、存储、测试和扩展方式。
2. [docs/technical-design.md](docs/technical-design.md)：系统设计总览。
3. [docs/prompts.md](docs/prompts.md)：Prompt 体系设计。
4. [src/debate_agent/app/service.py](src/debate_agent/app/service.py)：应用服务层。
5. [src/debate_agent/orchestration/turn_pipeline.py](src/debate_agent/orchestration/turn_pipeline.py)：业务编排总入口。

## 运行模式

CLI 常用命令：

1. `/help` 查看帮助
2. `/state` 查看当前会话状态摘要
3. `/clash` 查看当前 clash
4. `/coach` 请求最新回合教练反馈
5. `/coach auto` 或 `/coach manual` 切换教练模式
6. `/closing` 生成默认陈词方长陈词
7. `/closing me` 或 `/closing opponent` 指定陈词方
8. `/history` 查看最近几轮发言
9. `/save` 手动保存
10. `/exit` 保存并退出

Web 工作台当前支持：

1. 创建、恢复、删除会话
2. 直接编辑辩题与双方立场
3. 切换 opening 和 crossfire 阶段
4. 生成、编辑、保存和导入 opening framework
5. 生成、流式生成、保存和点评 opening brief
6. 发起 turn、coach、inquiry、closing 和 timer plan
7. 查看 timeline、clash board、证据卡片和结果面板
8. 修改教练模式、默认陈词方和网页检索开关

## Web API 概览

基础接口：

1. `GET /api/health`
2. `GET /api/sessions`
3. `POST /api/sessions`
4. `GET /api/sessions/{session_id}`
5. `DELETE /api/sessions/{session_id}`
6. `GET /api/sessions/{session_id}/usage`

会话编辑接口：

1. `PATCH /api/sessions/{session_id}/options`
2. `PATCH /api/sessions/{session_id}/metadata`
3. `PATCH /api/sessions/{session_id}/phase`

比赛与评判接口：

1. `POST /api/sessions/{session_id}/turns`
2. `POST /api/sessions/{session_id}/coach`
3. `POST /api/sessions/{session_id}/closing`
4. `POST /api/sessions/{session_id}/inquiry`
5. `POST /api/sessions/{session_id}/timer-plan`

备赛与立论接口：

1. `POST /api/sessions/{session_id}/preparation`
2. `POST /api/sessions/{session_id}/opening-framework/generate`
3. `PATCH /api/sessions/{session_id}/opening-framework`
4. `POST /api/sessions/{session_id}/opening-briefs/generate`
5. `POST /api/sessions/{session_id}/opening-briefs/stream`
6. `POST /api/sessions/{session_id}/opening-briefs/import`
7. `POST /api/sessions/{session_id}/opening-briefs/coach`

说明：turn、opening、inquiry、closing 等结果会返回 `master_plan`，便于观测当前由哪类比赛 Agent 执行。

## 检索与持久化

本地知识源：

1. `data/dossiers` 中每个 JSON 文件对应一个辩题资料包。
2. EvidenceService 会先做本地 dossier 检索，再按配置决定是否补充网页搜索。
3. 如果 session 中已存在 preparation packet，比赛链路会优先复用其中的 evidence、theory points 和 argument seeds。

会话存储：

1. 默认使用 JSON 文件落在 `data/sessions/{session_id}.json`。
2. 配置 `SESSION_STORE_TYPE=sqlite` 后，可切到 SQLite store。
3. 应用层保持显式 load / mutate / save 方式，便于调试和替换底层存储。

## 环境变量

核心 LLM 配置：

1. `OPENAI_BASE_URL`：OpenAI 兼容接口地址，默认 `https://api.openai.com/v1`
2. `OPENAI_API_KEY`：真实模型调用所需密钥；缺失时会退回本地 fallback
3. `OPENAI_MODEL`：默认模型，默认 `gpt-5.4`
4. `OPENAI_TIMEOUT_SECONDS`：请求超时，默认 `90`
5. `OPENAI_OPPONENT_MODEL`：可选，单独指定对手模型
6. `OPENAI_COACH_MODEL`：可选，单独指定教练模型
7. `OPENAI_CLOSING_MODEL`：可选，单独指定陈词模型
8. `LLM_MAX_RETRIES`：失败重试次数，默认 `3`

产品配置：

1. `WEB_SEARCH_ENABLED`：是否默认启用网页检索，默认开启
2. `WEB_SEARCH_LIMIT`：每次网页检索的补充条数，默认 `3`
3. `APP_ENV`：`development` 或 `production`
4. `CORS_ALLOWED_ORIGINS`：生产环境可配置允许的来源，逗号分隔
5. `API_KEYS`：可选，逗号分隔；配置后 Web API 需使用 Bearer Token
6. `SESSION_STORE_TYPE`：`json` 或 `sqlite`
7. `DATABASE_URL`：SQLite store 的数据库路径

## 质量保障

本仓库当前具备以下质量保障能力：

1. 自动化测试：当前测试覆盖 CLI / app service / web / storage / benchmark / retrieval 等关键路径。
2. CI：push 和 pull request 会运行 ruff、mypy、pytest 与最低覆盖率检查。
3. benchmark 工具：支持构建 seed、初始化 submission、运行 scorer。

本地常用命令：

```bash
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy src/ --ignore-missing-imports
```

## 当前边界

目前仍建议把它视为训练原型，而不是生产服务，原因主要包括：

1. 默认存储仍偏向本地调试场景。
2. Web 限流和鉴权能力是基础版，不含完整租户、审计和权限体系。
3. benchmark 主要覆盖结构化抽取和攻防对齐任务，还未覆盖全部端到端体验指标。
4. 复杂多角色赛制、分布式任务队列和长期观测体系仍未完备。