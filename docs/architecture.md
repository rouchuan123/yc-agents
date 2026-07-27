# YCore 架构

## 定位

YCore 是一个通用的 skill-driven 本地 Agent Harness。它面向中文用户，把 Skill workflow、工具调用、workspace/context、memory、trace/state、eval 和 verification 收敛到一个可复盘的 CLI runtime 中。

具体业务能力由 Skill 决定。`docx-template-authoring` 是当前重点业务落地点，用于证明 Harness 能支撑从需求确认、来源管理、内容生成到 DOCX 验证发布的完整业务闭环；`code-review` 展示同一套基座还可以扩展到其他领域。文档流程由 Skill 与受控工具实现，不写死在通用 Runtime 中。

## 运行链路

```text
用户请求
  -> CLI
  -> YCAgentRuntime
  -> SkillRuntimeAgent
  -> Skill 选择
  -> 选中的 Skill
  -> ToolGateway
  -> ycore.json enabled tools
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

当前仓库默认发布两个中文业务 Skill：

- `docx-template-authoring`：读取成品 Word 模板，完成需求与来源确认、内容生成、不可变 DOCX 版本、连续修订、确定性 QA、MiMo 逐页视觉 QA 和发布安全门。
- `code-review`：项目体检和变更审查，要求读文件、追链路、找风险、看测试缺口，并在需要时运行最小验证。

Skill 负责定义触发条件、输入、证据要求、输出结构和失败处理方式，不声明工具权限。新增其他领域 Skill 时，运行时边界不需要重写；Agent 会从 `ycore.json` 已启用的全局工具中自行选择。

### 文档业务子链路

```text
用户需求与 Word 模板
  -> docx-template-authoring
  -> 模板分析与语义契约
  -> 需求、来源与提纲确认
  -> 分章内容生成
  -> DOCX 不可变版本
  -> deterministic QA
  -> Word/PDF/PNG 渲染
  -> MiMo 逐页视觉 QA
  -> Verification 发布安全门
  -> outputs/ 正式交付
```

DeepSeek 负责文本、推理和工具流程，MiMo 只负责视觉 QA。成功页面写入视觉缓存，失败页面不缓存；视觉模型最终失败时产生环境阻断，只有用户明确同意环境豁免后才能降级发布。字体缺失 warning 只在交付时披露，不阻断发布。

## Tool 边界

`ToolGateway` 负责工具启用状态、参数 schema 校验、审批策略、追踪和失败返回。所有工具都是全局工具，`tools.entries.<name>.enabled` 是唯一启用来源，具体是否调用由 Agent 决定：

- `workspace_files`
- `file_reader`
- `code_search`
- `git_inspector`
- `verification_runner`
- `markdown_writer`
- `rag_search`
- `web_search`
- 文档任务工具组：`document_job`、`docx_template_analyzer`、`docx_template_query`、`document_source`、`document_content`、`docx_generate`、`docx_edit` 和 `docx_verify`

通用 `file_reader` 可以读取 `.docx` 文本；成品 Word 生成、排版复用、连续修订和视觉验收由文档任务工具组提供。工具实现仍受 `ToolGateway` 和 `ycore.json` 开关约束。

## Eval 与运行证据

YCore 的 eval 不只检查最终文本，也检查 trace、state、工具事件和 verification。当前用例覆盖文档工作流、代码审查、Runtime、ToolGateway 和 Context，详见 `docs/evaluation-report.md`。

YCore 的价值不在于让模型一次性给出完美回答，而在于把 Skill 选择、工具调用、工具失败、checkpoint 和最终输出全部落成可复盘证据。失败 case 能被定位到工具协议、工具预算、环境问题或指标脆弱性，而不是被笼统归因成“模型不行”。

## 项目指令

`ProjectInstructionLoader` 从当前 workspace 读取两层项目指令：

1. `YCORE.md`
2. `.ycore/YCORE.md`

合并顺序是内置 YCore 协议、根 `YCORE.md`、本地 `.ycore/YCORE.md`、模式协议。本地指令排在后面，因此在普通偏好冲突时优先；但项目指令不能覆盖工具 JSON 协议、真实性规则、工作区边界或 `ycore.json` 工具开关。

## MCP 边界

当前项目保留 MCP 配置和 adapter 边界：`mcp_servers.json` 描述 server/tool 元数据，`MCPClientConfig` 负责解析配置，`MCPToolAdapter` 将 YCore 的工具调用转成 `client.call_tool(server_name, tool_name, arguments)`。

第一条真实 stdio MCP 链路是 SQLite analytics MCP。YCore 在当前 workspace 启动一个 stdio SQLite MCP server，暴露 `sqlite.list_tables`、`sqlite.describe_table` 和 `sqlite.query_readonly`。这些工具通过 `ToolGateway` 注册为 `mcp_sqlite_*`，是否启用由 `tools.entries` 决定，并且 SQL 层只接受只读查询。

真正接入更多生产 MCP 时，还需要继续补充更完整的 capability negotiation、资源 metadata、认证、取消、日志脱敏、错误恢复和并发请求管理。

## Memory 与 Context 工程

YCore 将 context 拆成 user input、workspace、memory、skills、selected skill 和 optional context results。`ContextManager` 负责组装上下文，`MemoryCompressor` 负责会话压缩，`TokenBudget` 和 context report 负责估算各部分 token 占用。

RAG 保留为可选内部上下文基础设施。它能帮助处理需求文档、历史 notes 和本地资料，但不是固定产品故事；是否使用取决于 Skill 和用户任务。

## 当前限制

- 只保留 CLI 端。
- 当前发布 `docx-template-authoring` 与 `code-review` 两个业务 Skill，其中前者是重点落地点。
- 新领域能力可以通过新增 Skill、全局工具实现和 eval cases 引入；工具启用统一由 `ycore.json` 管理。
- 本地 `.ycore/YCORE.md` 是工作区私有指令层，不应提交到仓库。
