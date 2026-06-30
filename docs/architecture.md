# YCore 架构

## 定位

YCore 是一个通用的 skill-driven 本地 Agent Harness。它面向中文用户，把 Skill workflow、工具调用、workspace/context、memory、trace/state、eval 和 verification 收敛到一个可复盘的 CLI runtime 中。

具体业务能力由 Skill 决定。当前第一批验证 Skill 是 `code-review`、`eval-writer` 和 `ycore-analytics`；它们用于证明 Harness 能支撑本地项目审查、eval 设计和运行可观测性查询 workflow，但不代表 YCore 被固定成某个单一领域产品。

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

Skill discovery 会先通过 `IntentRouter` 对候选 Skill 排序：规则匹配处理明确触发词，语义匹配处理文本重叠，LLM classification 处理模糊请求。排序后的候选列表仍会交给模型做最终 Skill 选择，因此 deterministic retrieval 和模型判断保持分离。

`PromptBuilder` 是核心系统 prompt 的集中入口，负责 plain answer、skill selection、skill execution、retry 和 observation 协议。

## Skill 边界

当前仓库默认发布三个中文示例业务 Skill：

- `code-review`：项目体检和变更审查，要求读文件、追链路、找风险、看测试缺口，并在需要时运行最小验证。
- `eval-writer`：为 Agent workflow、工具边界、trace/state、verification 和输出质量设计 eval。
- `ycore-analytics`：通过只读 SQLite MCP 工具查询当前 workspace 的运行元数据、工具事件、verification 和 eval 结果。

Skill 负责定义触发条件、输入、允许工具、证据要求、输出结构和失败处理方式。新增其他领域 Skill 时，运行时边界不需要重写，只需要新增 Skill、相关工具边界和对应 eval cases。

## Tool 边界

`ToolGateway` 负责工具权限、参数 schema 校验、审批策略、追踪和失败返回。默认工具集保持通用，具体是否使用由 Skill 决定：

- `workspace_files`
- `file_reader`
- `code_search`
- `git_inspector`
- `verification_runner`
- `markdown_writer`
- `rag_search`
- `web_search`

`.docx` 通过通用文件读取工具处理，只用于读取需求或规格内容；YCore 不提供 Word 排版或格式修正能力。

## Eval 与运行证据

YCore 的 eval 不只检查最终文本，也检查 trace、state、工具事件和 verification。当前有效真实 eval 基线是 `20260630-211458`，详见 `docs/evaluation-report.md` 和 `docs/eval-run-20260630-211458.md`。旧 eval 记录只作为开发历史，不再代表当前质量口径。

这次基线说明了架构上的一个核心点：YCore 的价值不在于让模型一次性给出完美回答，而在于把 Skill 选择、工具调用、工具失败、checkpoint 和最终输出全部落成可复盘证据。失败 case 能被定位到工具协议、工具预算、环境问题或指标脆弱性，而不是被笼统归因成“模型不行”。

## 项目指令

`ProjectInstructionLoader` 从当前 workspace 读取两层项目指令：

1. `YCORE.md`
2. `.ycore/YCORE.md`

合并顺序是内置 YCore 协议、根 `YCORE.md`、本地 `.ycore/YCORE.md`、模式协议。本地指令排在后面，因此在普通偏好冲突时优先；但项目指令不能覆盖工具 JSON 协议、真实性规则、工作区边界或 allowed tools。

## MCP 边界

当前项目保留 MCP 配置和 adapter 边界：`mcp_servers.json` 描述 server/tool 元数据，`MCPClientConfig` 负责解析配置，`MCPToolAdapter` 将 YCore 的工具调用转成 `client.call_tool(server_name, tool_name, arguments)`。

第一条真实 stdio MCP 链路是 SQLite analytics MCP。YCore 在当前 workspace 启动一个 stdio SQLite MCP server，暴露 `sqlite.list_tables`、`sqlite.describe_table` 和 `sqlite.query_readonly`。这些工具通过 `ToolGateway` 注册为 `mcp_sqlite_*`，只允许 `ycore-analytics` Skill 使用，并且 SQL 层只接受只读查询。

真正接入更多生产 MCP 时，还需要继续补充更完整的 capability negotiation、资源 metadata、认证、取消、日志脱敏、错误恢复和并发请求管理。

## Memory 与 Context 工程

YCore 将 context 拆成 user input、workspace、memory、skills、selected skill 和 optional context results。`ContextManager` 负责组装上下文，`MemoryCompressor` 负责会话压缩，`TokenBudget` 和 context report 负责估算各部分 token 占用。

RAG 保留为可选内部上下文基础设施。它能帮助处理需求文档、历史 notes 和本地资料，但不是固定产品故事；是否使用取决于 Skill 和用户任务。

## 当前限制

- 只保留 CLI 端。
- 当前只发布 `code-review`、`eval-writer` 与 `ycore-analytics` 三个示例业务 Skill。
- 新领域能力需要通过新增 Skill、工具权限和 eval cases 引入。
- 本地 `.ycore/YCORE.md` 是工作区私有指令层，不应提交到仓库。
