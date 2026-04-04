# Agent 与后端学习文档

这份文档不是产品说明书，而是学习导图。目标是帮助你把这个仓库当成一个真实项目来拆开理解，既能学到 agent 项目常见的设计方式，也能学到一个 Python 后端项目是怎么组织起来的。

如果你以前只接触过“调用一个模型接口，然后返回一段文本”的 Demo，这个仓库更接近下一层：它已经开始把模型能力放进业务流程、状态管理、存储、Web API、前端工作台和自动化测试里。因此它很适合拿来学习“agent 项目如何工程化”。

## 先建立一个正确心智模型

很多人第一次看这类项目时，会把它理解成“一个大模型 + 一堆 prompt”。这个理解只对了一小半。

在这个仓库里，真正跑起来的是一个分层系统：

1. Web 或 CLI 接收用户输入。
2. 应用服务层决定应该走哪条业务链路。
3. 编排层组织检索、状态更新、Prompt 构造、模型调用和结果整形。
4. 领域模型保存中间状态和最终结果。
5. 存储层把 session 持久化到 JSON 或 SQLite。
6. 前端根据返回的 session 和结果对象刷新工作台。

也就是说，这个项目的核心不是“让模型说话”，而是“让模型稳定地嵌入一个可测试、可迭代、可恢复的业务流程”。

## 什么是这个项目里的 Agent

在这个仓库里，agent 不是通用意义上的“自主智能体平台”，而是被约束在特定业务角色里的模型执行单元。

你可以把它理解成三层：

1. 角色层：比如 opponent、coach、opening architect、closing writer。
2. 工作流层：比如 opening framework 生成、一辩稿生成、单轮对辩、教练点评、备赛资料包生成。
3. 系统层：FastAPI、应用服务、状态存储、前端工作台、测试。

这里的 agent 更像“被系统调用的专职工种”，而不是“自由行动的万能助手”。

比如：

1. opponent agent 的任务不是陪你聊天，而是围绕当前 clash 点和证据包生成有攻击性的对手输出。
2. coach agent 的任务不是鼓励你，而是按 rubric 诊断你上一轮的结构、回应和证据问题。
3. opening framework agent 的任务不是直接写稿，而是先产出一个可编辑的框架骨架。

这就是为什么它更像一个后端系统，而不是一个 prompt 实验文件夹。

## 什么是这个项目里的后端

这里的后端，不只是“FastAPI 开接口”。

它至少包含五种责任：

1. 协议层：处理 HTTP、SSE、请求参数和错误码。
2. 用例层：组织 create session、process turn、generate opening、request coach 这类业务动作。
3. 编排层：决定检索、状态更新、Prompt 构造、模型调用的顺序。
4. 领域层：定义 DebateSession、OpeningBrief、EvidenceRecord 这些核心对象。
5. 持久化层：把内存里的 session 变成 JSON 或 SQLite 数据。

如果你把这个项目当成后端来学，最重要的不是只看 FastAPI，而是看“一个请求如何穿过这五层”。

## 仓库分层怎么读

建议把仓库分成下面几层看。

### 1. app 层

关键文件：

1. [src/debate_agent/app/service.py](../src/debate_agent/app/service.py)
2. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py)
3. [src/debate_agent/app/cli.py](../src/debate_agent/app/cli.py)

这一层负责“对外提供能力”。

你可以把 [src/debate_agent/app/service.py](../src/debate_agent/app/service.py) 看成应用服务层，它把底层编排能力包装成一组清晰用例，比如：

1. create_session
2. process_user_turn
3. generate_opening_framework
4. generate_opening_brief
5. request_coach_feedback
6. request_closing_statement
7. get_opening_history
8. pin_evidence

这层很重要，因为它把“系统内部怎么做”与“外部如何调用”隔开了。

[src/debate_agent/app/web.py](../src/debate_agent/app/web.py) 则是 HTTP 入口。它做的事情主要有：

1. 定义 FastAPI 路由。
2. 解析请求体。
3. 调用 DebateApplication。
4. 把领域对象序列化成前端可用 JSON。
5. 处理异常。
6. 提供 SSE 流式接口。

如果你想学 FastAPI 项目怎么分层，这是一个比较好的参考：路由函数本身尽量薄，业务尽量放到 service 层和 orchestration 层。

### 2. orchestration 层

关键文件：

1. [src/debate_agent/orchestration/turn_pipeline.py](../src/debate_agent/orchestration/turn_pipeline.py)
2. [src/debate_agent/orchestration/pipeline_runtime.py](../src/debate_agent/orchestration/pipeline_runtime.py)
3. [src/debate_agent/orchestration/match_engine.py](../src/debate_agent/orchestration/match_engine.py)
4. [src/debate_agent/orchestration/speech_engine.py](../src/debate_agent/orchestration/speech_engine.py)
5. [src/debate_agent/orchestration/review_engine.py](../src/debate_agent/orchestration/review_engine.py)
6. [src/debate_agent/orchestration/session_state.py](../src/debate_agent/orchestration/session_state.py)
7. [src/debate_agent/orchestration/agent_services.py](../src/debate_agent/orchestration/agent_services.py)

这一层是项目最值得学习的部分，因为它体现了 agent 项目和传统 CRUD 后端最不一样的地方。

[src/debate_agent/orchestration/turn_pipeline.py](../src/debate_agent/orchestration/turn_pipeline.py) 可以理解成编排 facade。它对外暴露统一方法，但内部再拆给不同 engine。

目前主要拆成三块：

1. MatchEngine：单轮对辩、质询等比赛推进。
2. SpeechEngine：opening framework、opening brief、closing 等偏“稿件生成”的能力。
3. ReviewEngine：coach feedback、opening brief feedback、timer plan、框架更新。

这样拆的好处是：

1. 对外接口稳定。
2. 内部职责更清楚。
3. 测试更容易写。
4. 后续扩展新的链路时，不必把 turn pipeline 变成一个巨型文件。

[src/debate_agent/orchestration/pipeline_runtime.py](../src/debate_agent/orchestration/pipeline_runtime.py) 则是装配中心。它会初始化：

1. evidence service
2. example bank
3. state mutator
4. 各类 agent service
5. oversight 协调器

你可以把它理解成“业务运行时容器”。

### 3. domain 层

关键文件：

1. [src/debate_agent/domain/models.py](../src/debate_agent/domain/models.py)

这是整个项目的状态地基。

学习这个仓库时，最建议你优先读的文件其实不是 web.py，而是 models.py。因为只要你读懂了领域对象，后面的很多代码都会顺下来。

当前最重要的对象包括：

1. DebateSession：整个会话的总状态。
2. SessionOptions：教练模式、网页检索开关、默认陈词方。
3. DebatePhase：当前是 opening 还是 crossfire 等阶段。
4. OpeningFramework：一辩框架稿。
5. OpeningFrameworkVersion：框架版本历史。
6. OpeningBrief：一辩成稿。
7. EvidenceRecord：单条证据。
8. EvidenceWorkbenchState：证据工作台状态。
9. CoachReport：教练反馈。
10. TimerPlan：计时规划。

这几个对象一起回答了一个关键问题：

“这个系统在任何时刻，究竟知道什么？”

## 最关键的领域对象怎么理解

### DebateSession

DebateSession 是整个系统的单一事实源。

如果你只记住一个对象，那就记住它。因为几乎所有功能最终都是在读写它。

它里面会包含：

1. topic、双方立场、当前 phase。
2. turns、arguments、clash_points。
3. coach_reports、closing_outputs、timer_plans。
4. current_opening_framework。
5. opening_framework_versions。
6. opening_briefs。
7. current_opening_brief_id。
8. evidence_workbench。

这是一种非常典型的 agent 工程化方式：

不是每条链路各自维护一套状态，而是尽量把所有链路挂回同一个 session。

### OpeningFramework 与 OpeningBrief

这两个对象故意分开，是因为“框架”与“成稿”不是一回事。

框架回答的是：

1. 判断标准是什么。
2. 胜利路径是什么。
3. 论点结构怎么排。

一辩稿回答的是：

1. 最终要朗读的文本是什么。
2. 这一稿是几分钟版本。
3. 是系统生成的还是人工导入的。
4. 它基于哪个旧版本继续改出来。

这个拆分对产品也很重要。你这次刚修掉的 bug，本质上就是“当前框架”和“当前一辩稿”之前的语义被混淆了。

### EvidenceWorkbenchState

这是这次新增后最值得学习的对象之一。

它说明一个 agent 项目里的“检索结果”不应该只是一次性输入，而应该变成可操作状态。

它里面保存了：

1. available_evidence：当前可用证据池。
2. pinned_evidence：用户钉住的证据。
3. user_supplied_evidence：用户手工补充的证据。
4. blacklisted_source_types：被拉黑的来源类型。
5. last_research_query：最近研究查询。

这个设计很有代表性，因为它把 RAG 从“临时上下文拼接”升级成了“有用户干预能力的工作台状态”。

## 一个请求到底怎么走

下面用三条主链路讲清楚整个系统。

### 链路一：创建会话

入口一般来自：

1. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py) 的 POST /api/sessions
2. 或 CLI 入口

执行过程大致是：

1. Web 层解析 topic、双方立场、选项。
2. 调用 DebateApplication.create_session。
3. create_session 构造 DebateSession，并初始化 options。
4. state mutator 确保 evidence workbench 存在。
5. store.save_session 落盘。
6. 返回 session 和 summary。

你会发现，这条链路里还没有模型调用。因为不是所有 agent 项目动作都需要调模型。

### 链路二：生成 opening framework

入口是：

1. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py) 的 POST /api/sessions/{session_id}/opening-framework/generate

调用路径大致是：

1. web.py 读取 session。
2. service.py 调用 generate_opening_framework。
3. turn_pipeline.py 转交给 SpeechEngine。
4. SpeechEngine 组织上游上下文、证据和 prompt。
5. agent_services.py 里的 OpeningAgent 生成框架。
6. session_state.py 把 framework 写回当前 session，并追加框架版本历史。
7. 清空 current_opening_brief_id，表示当前没有新的成稿与这个新框架绑定。
8. store 保存。
9. Web 返回 framework_result 和更新后的 session。

这个流程特别适合学习“模型能力如何被包装成一个稳定后端动作”。

### 链路三：处理一轮对辩

入口是：

1. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py) 的 POST /api/sessions/{session_id}/turns

这是最典型的 agent 编排链路。

大致顺序是：

1. 收到用户发言。
2. 分析当前发言，抽取 arguments、clash 和 pending responses。
3. 更新 session 状态。
4. 做 live retrieval。
5. 与 preparation packet 和证据工作台状态合流。
6. 组装 prompt。
7. 调用 opponent agent。
8. 生成对手输出。
9. oversight 组件生成 timer plan，必要时生成 coach feedback。
10. 持久化整个 session。
11. 返回 turn_result 给前端。

这条链路的学习价值在于：

它展示了 agent 项目不是“prompt in, text out”，而是“状态更新 + 检索合流 + 模型调用 + 结果落盘”的组合动作。

## Prompt 是怎么接进来的

关键文件：

1. [src/debate_agent/prompts/builders.py](../src/debate_agent/prompts/builders.py)
2. [src/debate_agent/prompts/templates.py](../src/debate_agent/prompts/templates.py)
3. [docs/prompts.md](prompts.md)

可以把 prompt 层看成“把领域状态翻译成模型可理解指令”的适配层。

这里有三个关键点值得学。

### 1. Prompt 不是硬编码在业务方法里的大字符串

项目把 prompt 的构造拆成了 builders 和 templates。

这种拆法的好处是：

1. 便于测试输入变量是否齐全。
2. 便于替换模板而不动业务流程。
3. 便于把同样的 state 注入不同角色的 prompt。

### 2. Prompt 输入依赖共享 session 状态

比如 opening brief、preparation packet、evidence packet、clash points，不是每条链路各自重新算一份，而是都从 session 里读。

这意味着：

1. 状态设计越清楚，prompt 越稳。
2. 状态越混乱，prompt 越容易漂。

### 3. Prompt 输出尽量结构化

这不是“为了解析方便”这么简单，更重要的是为了工程稳定性。

输出结构化后：

1. 领域层更容易接住结果。
2. 测试更容易断言。
3. 前端更容易渲染。
4. benchmark 更容易做比较。

## 检索增强是怎么做的

关键文件：

1. [src/debate_agent/retrieval/evidence_service.py](../src/debate_agent/retrieval/evidence_service.py)
2. [src/debate_agent/retrieval/local_dossier.py](../src/debate_agent/retrieval/local_dossier.py)
3. [src/debate_agent/retrieval/web_search.py](../src/debate_agent/retrieval/web_search.py)

这个项目不是单纯把网页搜索结果扔给模型，而是把检索能力抽象成 EvidenceService。

它通常会做两类来源整合：

1. 本地 dossier 检索。
2. 可选网页搜索。

然后再跟 session 里的 preparation packet 和 evidence workbench 状态做合流。

这里有两个很典型的工程思想。

### 1. 检索是后端能力，不是 prompt 小技巧

很多 Demo 里，检索只是“先搜一下，再把文本拼到 prompt 里”。

但这个仓库里，检索已经升级成一个后端子系统，因为它要考虑：

1. 来源类型。
2. 去重。
3. 可信度。
4. 是否联网。
5. 用户钉住与黑名单。
6. 与已有 state 如何合流。

### 2. 证据不是一次性耗材，而是持续状态

这正是 evidence workbench 的意义。用户可以直接影响下一次生成时证据池的结构。

## SessionStateMutator 为什么重要

关键文件：

1. [src/debate_agent/orchestration/session_state.py](../src/debate_agent/orchestration/session_state.py)

这是整个项目最像“状态中枢”的地方。

如果你要学习 agent 项目如何避免状态混乱，一定要认真读这个文件。

它负责的不是模型调用，而是状态演进规则，例如：

1. 新增 turn。
2. 追加 coach report。
3. 设置 current opening framework。
4. 追加 opening brief，并设置 current_opening_brief_id。
5. 维护 framework 版本历史。
6. 维护 evidence workbench 的 pin、blacklist、manual evidence。

为什么要有一个专门的 state mutator？

因为如果状态更新逻辑散落在 web.py、service.py、engine.py 各处，久而久之一定会出现：

1. 某条链路漏更新字段。
2. 某些字段语义不一致。
3. 前端和后端对“当前态”理解不同。

这次 opening current 语义 bug，本身就说明：

只靠前端猜“最后一条是不是当前稿”是危险的，应该由后端显式维护 current id。

## LLM 客户端层怎么理解

关键文件：

1. [src/debate_agent/infrastructure/llm_client.py](../src/debate_agent/infrastructure/llm_client.py)

这是模型调用适配层。它把上层业务和具体模型 API 隔开。

学习时重点看三个问题：

1. 它如何区分普通文本生成与流式生成。
2. 它如何处理超时、重试和 fallback。
3. 它如何让上层不用关心底层供应商细节。

这在后端里很常见：

和数据库、消息队列、第三方支付一样，模型接口也需要被隔离在 infrastructure 层，而不是散落在业务代码里。

## 存储层怎么理解

关键文件：

1. [src/debate_agent/storage/json_store.py](../src/debate_agent/storage/json_store.py)
2. [src/debate_agent/storage/sqlite_store.py](../src/debate_agent/storage/sqlite_store.py)

这个项目的存储设计很适合学习“从原型走向更稳定结构”的过渡方式。

### JSON store

优点：

1. 简单直接。
2. 可读性强。
3. 特别适合调试 session 快照。

适合学习者的原因是：

你可以直接打开 data/sessions 下的 JSON 文件，肉眼看清一次业务动作到底改了哪些字段。

### SQLite store

它代表更稳定的本地持久化方向，但项目仍然保留 JSON store 作为默认调试入口。

这是一种很实际的工程折中：

1. 原型阶段，JSON 更快更透明。
2. 稍微稳定后，SQLite 更适合长期使用。

## Web 前端为什么也值得学

关键文件：

1. [src/debate_agent/app/web_assets/index.html](../src/debate_agent/app/web_assets/index.html)
2. [src/debate_agent/app/web_assets/app.js](../src/debate_agent/app/web_assets/app.js)
3. [src/debate_agent/app/web_assets/styles.css](../src/debate_agent/app/web_assets/styles.css)

如果你想学“agent 后端如何和一个实际工作台交互”，前端这部分不要跳过。

它的价值不在于前端框架技巧，而在于你可以看到：

1. session 如何作为前端状态核心。
2. opening 与 crossfire 两个阶段如何切换。
3. SSE 如何驱动一辩稿流式展示。
4. opening history 和 evidence workbench 如何映射成 UI。

尤其是 [src/debate_agent/app/web_assets/app.js](../src/debate_agent/app/web_assets/app.js)，你会看到一个典型事实：

agent 产品的前端，很多时候不是在“渲染静态数据”，而是在处理一个不断演进的 session。

## SSE 流式输出值得单独学

关键文件：

1. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py)
2. [src/debate_agent/orchestration/agent_services.py](../src/debate_agent/orchestration/agent_services.py)
3. [src/debate_agent/app/web_assets/app.js](../src/debate_agent/app/web_assets/app.js)

opening brief 的流式生成，是这个项目里一个很典型的“后端到前端的增量协作”案例。

你可以重点观察：

1. 后端如何发送 stage、framework_ready、opening_chunk、completed、error 这类事件。
2. 前端如何消费事件流。
3. 前端如何在重新生成或切换会话时 abort 旧流。

这部分很值得学，因为很多 agent 应用最后都会面对“生成时间长，用户不能一直干等”的问题。

## 测试怎么读最有效

关键文件：

1. [tests/test_application_service.py](../tests/test_application_service.py)
2. [tests/test_web_app.py](../tests/test_web_app.py)
3. [tests/test_json_store.py](../tests/test_json_store.py)
4. [tests/test_sqlite_store.py](../tests/test_sqlite_store.py)
5. [tests/test_opening_agent.py](../tests/test_opening_agent.py)

如果你是为了学习，这些测试甚至比业务代码更容易读。

建议阅读顺序：

1. 先读 application service 测试，理解有哪些用例。
2. 再读 web app 测试，理解 API 怎么暴露这些用例。
3. 再读 store 测试，理解 session 如何落盘。
4. 最后读 opening agent 或 benchmark 测试，理解模型链路和回归策略。

为什么测试适合学习？

因为测试天然在回答三个问题：

1. 这个系统打算保证什么行为。
2. 哪些字段是关键输出。
3. 开发者认为哪些回归风险最重要。

## 一套推荐的读代码顺序

如果你准备系统学习，建议不要顺着文件夹一个一个扫，而按下面顺序：

1. [README.md](../README.md)
2. [docs/technical-design.md](technical-design.md)
3. [src/debate_agent/domain/models.py](../src/debate_agent/domain/models.py)
4. [src/debate_agent/app/service.py](../src/debate_agent/app/service.py)
5. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py)
6. [src/debate_agent/orchestration/turn_pipeline.py](../src/debate_agent/orchestration/turn_pipeline.py)
7. [src/debate_agent/orchestration/match_engine.py](../src/debate_agent/orchestration/match_engine.py)
8. [src/debate_agent/orchestration/speech_engine.py](../src/debate_agent/orchestration/speech_engine.py)
9. [src/debate_agent/orchestration/review_engine.py](../src/debate_agent/orchestration/review_engine.py)
10. [src/debate_agent/orchestration/session_state.py](../src/debate_agent/orchestration/session_state.py)
11. [src/debate_agent/prompts/builders.py](../src/debate_agent/prompts/builders.py)
12. [src/debate_agent/orchestration/agent_services.py](../src/debate_agent/orchestration/agent_services.py)
13. [src/debate_agent/retrieval/evidence_service.py](../src/debate_agent/retrieval/evidence_service.py)
14. [src/debate_agent/storage/json_store.py](../src/debate_agent/storage/json_store.py)
15. [tests/test_application_service.py](../tests/test_application_service.py)

这个顺序的核心思想是：

先看状态和用例，再看 HTTP，再看内部编排，再看 prompt 和检索，最后看测试。

## 你能从这个项目学到哪些 agent 工程经验

### 1. Agent 最终要落回显式状态

如果系统不维护显式状态，很多能力就只能靠 prompt 猜。

这个项目现在把 opening current id、framework 版本历史、evidence workbench 都显式化了，这就是工程化进步。

### 2. 不要把所有逻辑塞进一个“大总管函数”

TurnPipeline 继续保留统一入口，但内部已经拆成 engine。这是非常典型也非常正确的演进路径。

### 3. 检索不该只是字符串拼接

真正有产品价值的 RAG，需要来源类型、可信度、去重、用户干预和后续复用。

### 4. Prompt 不是系统边界，领域模型才是

Prompt 会变，模型会变，但 DebateSession、OpeningBrief、EvidenceRecord 这种领域对象才是系统长期稳定的部分。

### 5. 前端不能自己发明后端语义

旧 opening bug 的教训就是：当前稿应该由后端显式声明，而不是前端用数组最后一项猜出来。

## 如果你想自己动手改，最适合的练习题

下面这些练习很适合用来理解项目。

### 练习一：给 session 增加一个新字段

比如新增“学习标签”或“训练目标”。

你需要改的通常包括：

1. [src/debate_agent/domain/models.py](../src/debate_agent/domain/models.py)
2. [src/debate_agent/storage/json_store.py](../src/debate_agent/storage/json_store.py)
3. [src/debate_agent/app/service.py](../src/debate_agent/app/service.py)
4. [src/debate_agent/app/web.py](../src/debate_agent/app/web.py)
5. 对应测试文件

这是学习全链路修改最好的入口。

### 练习二：新增一个只读诊断接口

比如新增“最近一次 opening 生成使用了哪些证据”的诊断接口。

这个练习会帮助你理解：

1. Web 路由如何组织。
2. service 层如何暴露只读用例。
3. session 数据如何被安全序列化。

### 练习三：新增一个新的 review 动作

比如新增“closing 自检报告”。

这个练习会帮助你理解：

1. ReviewEngine 的职责边界。
2. Prompt 模板如何新增。
3. 输出结构如何落回 domain model。

### 练习四：给前端加一个新的工作台面板

比如加一个“Preparation Packet 浏览器”。

这会迫使你真正理解：

1. session 返回结构。
2. 前端状态管理。
3. 页面如何围绕当前会话刷新。

## 常见坑位

### 1. 状态重复存两份

这是 agent 项目里最常见的问题。

如果一个字段既存在 session，又存在临时结果对象，又存在前端独立缓存，而且三者缺少统一语义，很快就会错。

### 2. 让 Web 路由承担太多业务逻辑

如果 web.py 里直接拼 prompt、直接更新十几个字段，后面会很难测。

### 3. 让 Prompt 直接决定业务规则

业务规则应该先在后端定清楚，例如当前稿如何判定、哪些来源被拉黑、哪些字段必须返回。Prompt 只能在这些规则内工作。

### 4. 忽视存储兼容性

领域模型一改，JSON 旧文件能否继续加载就会变成真实问题。

这就是为什么 json_store 里会有一些向后兼容逻辑。

### 5. 只看 happy path，不看回归测试

agent 项目很容易“看起来能跑”，但一改结构就破。测试是你理解系统真实约束的最快方式。

## 如果你是为了学后端，建议重点关注什么

1. FastAPI 路由如何保持薄。
2. 应用服务层如何定义用例边界。
3. 编排层如何调用多个子组件。
4. 领域模型如何承接复杂状态。
5. 存储层如何做序列化和向后兼容。
6. 测试如何覆盖 service、web、store 三层。

## 如果你是为了学 agent，建议重点关注什么

1. agent 在这里被定义成什么业务角色。
2. retrieval 和 prompt 如何接进工作流。
3. 结构化输出为什么重要。
4. 为什么要把状态显式建模。
5. 为什么 evidence workbench 这种“用户可干预状态”比一次性 RAG 更接近真实产品。

## 一个简化的全局图

你可以把整个系统先粗略记成下面这张图：

1. 输入层：Web / CLI
2. 应用层：DebateApplication
3. 编排层：TurnPipeline + Engines
4. 能力层：Prompt builders、Agent services、Evidence service、Oversight
5. 状态层：DebateSession + 相关 domain models
6. 持久化层：JSON / SQLite store
7. 输出层：HTTP JSON、SSE、CLI 文本、Web 工作台

如果你能把这七层对应到具体文件上，这个仓库你基本就入门了。

## 最后给学习者的建议

不要急着一上来就改 prompt，也不要急着替换模型。

更好的学习顺序是：

1. 先读清状态对象。
2. 再读一条完整链路。
3. 再看 Prompt 如何被组装进去。
4. 再看前端如何消费结果。
5. 最后再自己加一个小功能。

如果你真的想学到 agent 项目和后端项目的交叉地带，这个仓库最值得你体会的一点是：

真正让系统稳定的，往往不是模型有多聪明，而是分层、状态、契约、测试和持久化有没有站稳。