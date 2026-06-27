# YCore 面试笔记

## 60 秒项目介绍

YCore 是一个面向中文用户、面向 code agent 的本地 Agent Harness。项目重点不是做聊天界面，而是展示 Agent 工程的关键边界：Skill 选择、本地代码证据、ToolGateway 工具治理、工作区隔离、trace/state、eval 和 VerificationGate。

当前第一条落地能力是 `code-review`：让 agent 做项目体检和变更审查。`eval-writer` 用来为这个 code agent 设计 deterministic eval、真实模型 smoke eval 和人工 rubric。

## 90 秒项目介绍

YCore 是一个本地 Agent Harness。我重点做的不是让模型自由聊天，而是把 code agent 的工程闭环做出来：Skill 选择负责能力路由，ToolGateway 负责工具治理，trace/state 负责过程可观测，eval runner 负责行为评测，VerificationGate 负责完成校验。当前主线是代码审查，后续可以扩展到 bugfix、代码修改和功能实现 agent。这个项目的价值在于它能解释 Agent 为什么选某个 Skill、为什么调用某个工具、失败怎么定位、结果怎么评测。

## 为什么强调 Skill 层

Skill 让具体工作流成为可维护资产：

- 触发条件和示例输入写在 `SKILL.md`。
- allowed tools 明确声明。
- 参考资料、脚本和资产跟随 Skill 管理。
- 全局 prompt 不需要为某个场景持续膨胀。

## Eval 不一定需要大模型参与

我会把 eval 分成两层讲：

- deterministic eval：日常回归使用固定 runtime、fake trace 或已记录 trace，检查 Skill 是否选对、工具是否按预期调用、禁止工具是否没用、verification 是否通过。这部分不需要大模型。
- 真实模型 smoke eval：面试演示或手动验收时跑少量真实模型 case，再用人工 rubric 判断输出质量，比如是否读了证据、是否指出真实风险、建议是否可执行。

关键词命中只能做弱基线，不能代表语义质量。复杂质量可以人工评，也可以后续接可选 LLM-as-Judge。

## 最难的技术点

最难的是把模型自由度控制在工程边界内。模型负责判断何时使用技能、如何解释结果；runtime 负责 JSON 协议、工具权限、工作区边界、trace 和 state。项目指令可以影响偏好和协作方式，但不能覆盖硬运行规则。

## 工具调用失败处理

`ToolGateway` 会校验工具名、参数 schema、权限和审批策略。工具失败时返回结构化错误，运行 trace 中会记录失败事件，模型可以据此解释原因或要求用户补充信息。

## ToolGateway 可观测性讲法

我把工具调用都收敛到 ToolGateway，所以可以统一做权限、schema 校验、超时、重试、approval 和 trace 记录。面试里我会强调：Agent 不是“调用工具就结束”，而是要能解释工具为什么被允许、为什么失败、失败后有没有重试，以及这些信息如何进入 eval 报告。

## RAG 讲法

RAG 现在不是核心产品故事，而是可选上下文模块。它适合在读取需求文档、历史 notes 或本地资料时辅助回答；code-review 的主线仍然是本地代码证据、调用链和 verification。

## Memory / Context 讲法

我会把长上下文问题拆成三个层次：短期 session 保留最近关键对话，summary 承接被压缩的历史，profile 保存稳定偏好。然后用 context report 统计每部分 token 预算。这样面试官问上下文溢出、记忆污染、历史信息丢失时，我能解释具体策略和权衡。

## VerificationGate 讲法

YCore 里“完成”不是模型自己说了算，而是要通过 VerificationGate。它可以检查输出、文件、工具结果、JSON 协议、checklist 和命令结果。这个设计和 eval 结合后，可以回答“Agent 怎么知道自己真的做完了”这个常见面试问题。

## MCP 讲法

我不会把现在的项目包装成“已经完整支持 MCP”。更准确的说法是：YCore 已经保留了 MCP adapter/config 边界，当前用静态 client 和测试验证调用形状；等真的需要 GitHub、浏览器、数据库或知识库 MCP 时，再补真实 stdio client。这样做的性价比更高，也避免为了简历关键词写一大段没有真实场景的协议代码。

## Skill Discovery

YCore 不会把所有 Skill 正文都塞进上下文。它先用 rule、semantic 和 LLM 得分构造候选集，再让模型在缩小后的候选列表里做最终选择。这样既节省上下文，也能解释为什么某个 Skill 被排到前面。

## 当前发布范围

- 只保留 CLI 端。
- 默认发布 `code-review` 和 `eval-writer` 两个 code-agent Skill。
- 支持根 `YCORE.md` 与本地 `.ycore/YCORE.md` 两层项目指令。
- 默认工具集以本地代码证据为核心：工作区文件、文件读取、代码搜索、Git 只读检查、最小验证和 Markdown 写入。
- RAG 只作为可选上下文，不是核心主线。

## 可演示闭环

我准备了两类演示：离线 deterministic demo 用于稳定展示 eval harness；真实 CLI demo 用于展示模型驱动的 Skill 选择和工具调用。这样面试现场即使没有模型 key，也能讲清楚评测闭环。

## 工程可信度

项目有单元测试覆盖 CLI runtime、技能加载、技能发现、prompt builder、项目指令加载、工具网关、RAG、记忆和运行输出。`scripts/test.ps1` 只运行 Python 测试，和当前 CLI-only 范围保持一致。
