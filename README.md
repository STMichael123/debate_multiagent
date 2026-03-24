# Debate Project

这是一个面向资深辩手训练场景的模拟辩论 Agent 原型仓库。

当前阶段目标：

1. 搭建本地文本原型，而不是完整产品。
2. 固化双 Agent 架构：对手 Agent 负责高压对辩，教练 Agent 负责诊断与复盘。
3. 优先打通 crossfire 单轮模式，再扩展多轮状态持久化、检索增强和更完整赛制。
4. 支持通过 OpenAI 兼容接口接入真实 LLM。

## 当前仓库结构

```text
docs/
  technical-design.md
  prompts.md
  evaluation.md
src/
  debate_agent/
    app/
    domain/
    orchestration/
    prompts/
    retrieval/
    storage/
data/
  dossiers/
  sessions/
pyproject.toml
```

## 已落地内容

1. 技术设计文档：模块边界、数据结构、回合主链路。
2. Prompt 文档：对手 Agent 和教练 Agent 的分层模板草稿。
3. 领域模型：会话、回合、论点、争议点、证据、策略、输出对象。
4. 交互式 CLI：支持新建会话、恢复会话、逐轮输入、自动保存和状态查看。
5. OpenAI 兼容客户端：通过本地 `.env` 读取 base URL、API key 和 model。
6. 多轮状态累积：session 会累计双方回合、论点列表、clash 列表和教练报告。
7. 本地 dossier 检索：根据辩题从 `data/dossiers` 召回证据片段。
8. JSON session 持久化：会话可保存到 `data/sessions` 并重新加载。
9. 按需教练反馈：只有在用户主动请求时才生成教练 Agent 输出。
10. 陈词 Agent：可根据当前交锋状态生成一篇长陈词稿。
11. 多源检索：除本地 dossier 外，还可追加网页搜索结果作为候选资料。
12. 应用服务层：CLI 通过统一应用服务调用对辩、教练、陈词与会话配置能力。
13. Web 工作台：支持在浏览器中创建会话、发起回合、查看 clash、请求教练反馈和生成陈词稿。
14. Web 会话编辑：支持在前端直接修改当前辩题和双方立场。

## 下一阶段建议

1. 增加可视化 clash board。
2. 强化对手论点抽取与长期复盘能力。
3. 为 dossier 检索增加按立场和 clash 的筛选。
4. 视规模再考虑从 JSON 升级到 SQLite。

## 本地资料库

当前采用本地 dossier 作为第一版知识源：

1. 每个辩题一个 JSON 文件，放在 `data/dossiers`。
2. 文件包含 `topic`、`aliases` 和 `evidence` 列表。
3. 检索层会根据当前辩题选择最匹配的 dossier，并返回若干 `EvidenceRecord`。

## 会话持久化

当前采用 JSON 文件保存会话：

1. 每个 session 对应 `data/sessions/{session_id}.json`。
2. 文件保存 turns、arguments、clash_points、coach_reports 等完整状态。
3. CLI 已支持直接继续已有会话，并在每轮后自动保存。

## 运行方式

建议使用 Python 3.11+。

```bash
python -m debate_agent.app.cli
```

如果使用 src 布局，可先设置：

```bash
set PYTHONPATH=src
python -m debate_agent.app.cli
```

Web 界面运行方式：

```bash
set PYTHONPATH=src
uvicorn debate_agent.app.web:app --reload
```

Windows 下更推荐使用仓库自带的安全启动脚本。它会先清理旧的 8000 端口监听进程和残留的 uvicorn 子进程，再启动开发服务器，避免 `--reload` 在 PowerShell 里留下孤儿进程：

```powershell
.\scripts\start_web.ps1
```

如果你不需要热重载：

```powershell
.\scripts\start_web.ps1 -NoReload
```

启动后打开 http://127.0.0.1:8000 即可使用浏览器工作台。

交互命令：

1. `/help` 查看帮助
2. `/state` 查看当前状态摘要
3. `/clash` 查看当前 clash
4. `/coach` 按需生成当前最新一轮教练反馈
5. `/coach auto` 或 `/coach manual` 切换教练模式
6. `/closing` 生成默认陈词方的长陈词稿
7. `/closing me` 或 `/closing opponent` 指定陈词方
8. `/history` 查看最近几轮发言
9. `/save` 手动保存
10. `/exit` 保存并退出

Web 工作台当前支持：

1. 创建和恢复会话
2. 单轮对辩输入
3. 手动或自动教练模式
4. 我方或对方陈词生成
5. clash board、时间线和证据卡片展示
6. 当前辩题与双方立场的直接编辑

## LLM 配置

本地调用通过 `.env` 读取：

1. `OPENAI_BASE_URL`
2. `OPENAI_API_KEY`
3. `OPENAI_MODEL`，默认 `gpt-5.4`
4. `OPENAI_TIMEOUT_SECONDS`

如果配置存在，CLI 会优先调用真实 LLM；如果缺失，则回退到 mock 输出。

对手、教练、陈词等多 Agent 默认都会跟随 `OPENAI_MODEL`；如果你的 OpenAI 代理支持，也可以单独覆写 `OPENAI_OPPONENT_MODEL`、`OPENAI_COACH_MODEL`、`OPENAI_CLOSING_MODEL`。

可选网页检索配置：

1. `WEB_SEARCH_ENABLED` 控制是否启用网页搜索补充资料，默认开启。
2. `WEB_SEARCH_LIMIT` 控制每次最多补充多少条网页结果，默认 3。