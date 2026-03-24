# Technical Design

## 目标

首版只解决一个问题：让系统能够在单轮或多轮文本对辩里，像一个高水平对手那样抓核心漏洞、持续追问，并在回合后给出结构化训练反馈。

## 系统分层

### app

负责 CLI 或后续 Web 交互，不承担辩论逻辑。

### orchestration

负责回合编排。

核心组件：

1. `SessionOrchestrator`：管理整场生命周期。
2. `TurnPipeline`：执行单轮管线。
3. `PhaseController`：控制阶段切换。
4. `ContextCompressor`：长对话摘要与压缩。

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

`process_turn` 建议固定为以下顺序：

1. 接收用户发言。
2. 抽取论点。
3. 更新 clash 和待回应点。
4. 检索证据。
5. 生成对手 prompt。
6. 生成对手输出。
7. 校验输出结构与证据引用。
8. 更新 session 状态。
9. 生成教练反馈。

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