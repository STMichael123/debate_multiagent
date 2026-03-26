# Technical Design

## 目标

首版只解决一个问题：让系统能够在单轮或多轮文本对辩里，像一个高水平对手那样抓核心漏洞、持续追问，并在回合后给出结构化训练反馈。

## 系统分层

### app

负责 CLI 和 Web 交互，以及用例级编排入口，不承担具体辩论生成逻辑。

当前核心组件：

1. DebateApplication：对外暴露 create session、process turn、prepare、opening、coach 等用例。
2. app/web.py：提供 FastAPI 接口与 SSE 流式输出。
3. app/cli.py：保留本地命令行调试入口。

### orchestration

负责回合编排、发言生成、评价反馈与备赛资料整理。

核心组件：

1. TurnPipeline：兼容门面，保留既有公共 API，不直接承载全部流程细节。
2. PipelineRuntime：集中初始化 evidence service、state mutator、LLM agents 与共享辅助逻辑。
3. MatchEngine：负责 process_turn 与 inquiry 等实战链路。
4. SpeechEngine：负责 opening framework、opening brief、closing statement 等陈词链路。
5. ReviewEngine：负责 coach feedback、opening brief feedback、timer plan 与手动注入 opening brief。
6. PreparationCoordinator：负责备赛资料检索、论点种子与学理整理。

### domain

负责辩论语义对象和规则。

核心服务：

1. `DebateSession`
2. `ArgumentUnit`
3. `ClashPoint`
4. `EvidenceRecord`
5. `DebateProfile`
6. `AgentOutput`
7. `CoachReport`

### prompts

负责 prompt 片段模板和模板拼装输入契约。

## 单轮主链路

当前 process_turn 由 DebateApplication 调用 TurnPipeline facade，再委托 MatchEngine 执行。顺序固定为：

1. 接收用户发言。
2. 抽取论点。
3. 更新 clash 和待回应点。
4. 检索证据。
5. 生成对手 prompt 与对手输出。
6. 生成计时规划与可选教练反馈。
7. 更新 session 状态并持久化。

说明：

1. preparation packet 会作为上游资料包参与 turn、opening 和 coach prompt 生成。
2. opening 与 closing 不再复用 process_turn，而是走独立 speech chain，避免单个 pipeline 类持续膨胀。
3. review 相关能力通过独立 engine 复用同一套 session state 与 oversight coordinator。

## 首版范围

纳入：

1. 文本模式。
2. Crossfire 单轮。
3. Review 回合点评。
4. Prompt 模板和结构化输出契约。

排除：

1. 语音。
2. 开放联网搜索。
3. 多角色完整赛制。
4. 复杂前端。

## 持久化建议

首版优先使用 JSON 或 SQLite，目标是易于调试，而不是追求分布式或高并发。

当前实现仍使用 JSONSessionStore，应用层维持显式 load / mutate / save 模式，后续若切 PostgreSQL，可优先保持 app 和 orchestration 的用例边界不变，只替换 store 与事务控制策略。