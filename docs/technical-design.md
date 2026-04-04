# Technical Design

## 目标

当前系统的目标已经不再只是“单轮文本对辩”。它现在面向一个完整训练闭环：

1. 备赛：检索资料、整理学理、生成 preparation packet。
2. 立论：生成和打磨 opening framework 与 opening brief。
3. 对辩：进行 turn、inquiry、closing 与 clash 推进。
4. 评判：生成 coach feedback、opening brief feedback 与 timer plan。

系统仍然以本地可调试、可验证、可替换为首要原则，而不是以多租户、高并发或生产部署复杂度为优先目标。

## 系统分层

### app

负责 CLI、Web 和用例级编排入口。

核心组件：

1. DebateApplication：统一暴露 create session、process turn、prepare、opening、coach、closing、timer plan 等用例。
2. app/web.py：提供 FastAPI 路由、SSE 流式一辩稿输出、基础鉴权、限流和异常映射。
3. app/cli.py：提供本地命令行调试入口，覆盖会话创建、恢复、回合推进、教练和陈词能力。

### orchestration

负责编排业务流程，不直接处理外层协议细节。

核心组件：

1. TurnPipeline：兼容 facade，保留公共 API，内部把职责拆给更细的 engine。
2. PipelineRuntime：负责初始化 evidence service、example bank、state mutator、LLM agents 和 oversight 组件。
3. MatchEngine：负责 process_turn 与 inquiry 等比赛链路。
4. SpeechEngine：负责 opening framework、opening brief、stream opening brief、closing statement 等陈词链路。
5. ReviewEngine：负责 coach feedback、opening brief feedback、timer plan、opening framework 更新和 opening brief 注入。
6. PreparationCoordinator：负责编排资料检索与学理整合。

### retrieval

负责知识召回与证据组装。

核心组件：

1. EvidenceService：统一整合本地 dossier 和可选网页搜索。
2. Local dossier retrieval：按 topic 和 aliases 做启发式命中。
3. WebSearchRetriever：根据会话选项决定是否联网，并在异常时快速失败降级。
4. ExampleBank：为对手与教练类 prompt 提供结构参考示例。

### infrastructure

负责系统性横切能力。

核心组件：

1. DebateLLMClient：OpenAI 兼容客户端。
2. settings.py：加载环境变量并构建运行配置。
3. auth.py：Bearer API key 校验。
4. rate_limiter.py：内存型限流。
5. security_headers.py：基础安全响应头。
6. logging_config.py：日志初始化。

### domain

负责辩论语义对象和状态模型。

当前关键模型包括：

1. DebateSession
2. DebatePhase
3. SessionOptions
4. ArgumentUnit
5. ClashPoint
6. EvidenceRecord
7. OpeningFramework
8. OpeningBrief
9. PreparationPacket
10. CoachReport
11. TimerPlan

### storage

负责会话状态落盘。

当前实现：

1. JSONSessionStore：默认实现，便于调试与快照检查。
2. SQLiteSessionStore：通过配置切换，作为更稳定的本地持久化选项。

## 运行时装配

PipelineRuntime 是当前业务内核的装配中心。其职责包括：

1. 根据 settings 决定模型、网页检索开关和检索上限。
2. 初始化 opponent、coach、closing、opening、inquiry 等 Agent。
3. 初始化 DebateAndFreeDebateAgent、SpeechAndClosingAgent 与 OversightCoordinator。
4. 统一提供 state_mutator、evidence_service 与 example_bank 给上层流程复用。

这种拆分的目的，是把“对外 API 稳定性”与“内部流程继续细化”分开处理。TurnPipeline 可以保持兼容，而内部 engine 可以独立演进。

## 核心业务流

### 会话生命周期

1. 由 DebateApplication 创建会话，初始化 topic、双方立场、coach 模式、web search 开关、默认陈词方和当前 phase。
2. session 默认从 opening 阶段开始。
3. Web 和 CLI 都通过应用服务执行显式 load / mutate / save。

### 备赛链路

1. PreparationCoordinator 调用 research scout 和 theory synthesis agent。
2. 输出 preparation packet，包含 evidence records、theory points、argument seeds 和推荐框架线索。
3. packet 会写回 session，作为后续 opening、turn、coach 和 closing 的上游输入。

### 立论链路

1. SpeechEngine 先生成 opening framework。
2. 用户可在 Web 端直接编辑并保存 framework。
3. opening brief 可直接生成，也可严格基于当前 framework 扩写。
4. opening brief 支持同步生成、SSE 流式生成和人工注入。
5. ReviewEngine 可对 current opening brief 生成专门的稿件教练反馈。

### 对辩链路

当前 process_turn 的固定顺序为：

1. 接收用户发言。
2. TurnAnalyzer 抽取论点、clash 和 pending responses。
3. SessionStateMutator 更新 session 状态。
4. EvidenceService 拉取 live evidence，并与最新 preparation evidence 去重合并。
5. MatchEngine 组织 opponent prompt，生成 opponent output。
6. OversightCoordinator 生成 timer plan，并按模式决定是否追加 coach feedback。
7. 应用层持久化会话结果。

### 衍生比赛链路

1. inquiry：围绕 speaker side 和 inquiry focus 生成质询提纲。
2. closing：围绕 judge standard、clash、recent turns 和 evidence packet 生成长陈词。
3. timer plan：由确定性自动化组件生成，而不是单独依赖大模型。

## 数据流原则

1. preparation packet 是可选上游输入，不是强依赖。
2. live retrieval 与 preparation retrieval 会在 runtime 合并去重。
3. opening、turn、coach、closing 共享同一份 session state，而不是各自维护影子状态。
4. Web API 返回序列化 session 与 summary，便于前端直接刷新视图。
5. streaming opening brief 使用事件队列和 worker thread 产出 SSE 事件，并在超时或异常时返回 error event。

## 安全与韧性

当前 Web 层具备以下基础保障：

1. 可选 Bearer API key 校验；未配置 `API_KEYS` 时默认关闭鉴权。
2. 基于客户端 IP 的内存限流。
3. Security headers 中间件。
4. 对业务异常、输入错误和 LLM 错误做统一 HTTP 映射。
5. 流式接口支持 keepalive 和超时保护，避免前端长时间无反馈。
6. LLM 不可用时，系统可退回本地 fallback 以保证流程继续可测。

## 当前范围与非目标

当前纳入范围：

1. 文本模式训练。
2. Web 与 CLI 双入口。
3. opening、crossfire、closing、coach、inquiry、preparation、timer plan。
4. 本地 dossier 检索与可选网页搜索。
5. JSON 与 SQLite 两类本地存储。

当前非目标：

1. 语音输入输出。
2. 多租户权限系统。
3. 分布式任务队列与异步作业编排。
4. 完整生产级观测、审计和成本治理体系。
5. 全赛制、多角色、多人协作房间。