# YCore 架构

## 定位

YCore 是一个面向 code agent 的本地 Agent Harness。它面向中文用户，把本地代码证据、Skill 工作流、工具调用、trace/state、eval 和 verification 收敛到一个可复盘的 CLI runtime 中。

具体业务能力属于 Skill。当前第一条落地线是 `code-review`，第二条支撑线是 `eval-writer`。全局 prompt 不承担具体审查流程，只提供真实性、工具协议和工作区边界。

## 运行链路

```text
用户请求
  -> CLI
  -> YCAgentRuntime
  -> SkillRuntimeAgent
  -> Skill 选择
  -> 选中的 Skill
  -> ToolGateway
  -> allowed tools
  -> trace / state / output
  -> eval / verification
```

## Runtime 边界

`YCAgentRuntime` 负责编排一次运行：

- 写入 run 输入和上下文快照。
- 调用 Agent。
- 解析模型返回的 JSON 协议。
- 通过 `ToolGateway` 执行工具。
- 写入最终输出、verification、trace 和 state checkpoint。

## Agent 边界

`SkillRuntimeAgent` 负责：

- 加载 `skills` 目录下的技能。
- 用技能摘要进行候选技能发现。
- 在技能被选中后加载完整 `SKILL.md` 正文。
- 将 workspace、记忆、可选上下文和技能说明交给 `PromptBuilder` 组装为模型消息。

Skill discovery first ranks candidates through `IntentRouter`: rule matching handles explicit trigger terms, semantic matching handles text overlap, and LLM classification handles ambiguous requests. The selected candidate list is still passed to the model for final skill selection, so deterministic retrieval and model judgment stay separated.

`PromptBuilder` 是核心系统 prompt 的集中入口，负责 plain answer、skill selection、skill execution、retry 和 observation 协议。

## Skill 边界

当前仓库默认发布两个中文 Skill：

- `code-review`：项目体检和变更审查，要求读文件、追链路、找风险、看测试缺口，并在需要时运行最小验证。
- `eval-writer`：为 code agent、工具边界、trace/state、verification 和输出质量设计 eval。

Skill 负责定义触发条件、输入、允许工具、证据要求、输出结构和失败处理方式。

## Tool 边界

`ToolGateway` 负责工具权限、参数 schema 校验、审批策略、追踪和失败返回。code-agent 主线的核心工具是：

- `workspace_files`
- `file_reader`
- `code_search`
- `git_inspector`
- `verification_runner`
- `markdown_writer`

`rag_search` 是可选 context module，用于本地资料、需求 notes 或历史文档影响回答的场景，不是 code-review 默认依赖。`.docx` 通过通用文件读取工具处理，只用于读取需求或规格内容；YCore 不提供 Word 排版或格式修正能力。

## 项目指令

`ProjectInstructionLoader` 从当前 workspace 读取两层项目指令：

1. `YCORE.md`
2. `.ycore/YCORE.md`

合并顺序是内置 YCore 协议、根 `YCORE.md`、本地 `.ycore/YCORE.md`、模式协议。本地指令排在后面，因此在普通偏好冲突时优先；但项目指令不能覆盖工具 JSON 协议、真实性规则、工作区边界或 allowed tools。

## MCP 边界

当前项目保留 MCP 配置和 adapter 边界：`mcp_servers.json` 描述 server/tool 元数据，`MCPClientConfig` 负责解析配置，`MCPToolAdapter` 将 YCore 的工具调用转成 `client.call_tool(server_name, tool_name, arguments)`。

这一阶段不实现真实 stdio MCP client，因为 code-agent 第一阶段还没有必须依赖 GitHub、浏览器、数据库或知识库 MCP 的场景。真正接入生产 MCP 时，需要补充 stdio 进程生命周期、initialize/tools/list 协议、JSON-RPC 消息关联、资源 metadata、认证、超时、取消、日志脱敏和错误恢复。

## Memory 与 Context 工程

YCore 将 context 拆成 user input、workspace、memory、skills、selected skill 和 optional context results。`ContextManager` 负责组装上下文，`MemoryCompressor` 负责会话压缩，`TokenBudget` 和 context report 负责估算各部分 token 占用。

RAG 保留为可选内部上下文基础设施。它能帮助处理需求文档、历史 notes 和本地资料，但不是当前产品叙事的核心。

## 当前限制

- 只保留 CLI 端。
- 当前只落地 `code-review` 与 `eval-writer` 两个 code-agent Skill。
- bugfix、代码修改和功能实现 agent 是后续扩展方向。
- 本地 `.ycore/YCORE.md` 是工作区私有指令层，不应提交到仓库。
