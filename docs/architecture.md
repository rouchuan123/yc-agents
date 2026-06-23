# YCore 架构

## 运行时边界

`YCAgentRuntime` 负责一次运行的整体编排。它接收用户输入，调用 Agent，处理 JSON 协议，通过 `ToolGateway` 分发工具调用，写入运行输出，记录追踪事件，并持久化状态检查点。

## Agent 边界

`SkillRuntimeAgent` 决定用户输入如何映射到某个 skill，并准备执行所需的提示词上下文。在请求 LLM 给出最终回答或工具调用之前，它会注入会话记忆、摘要上下文、用户画像上下文和 RAG 片段。

## Skill 系统

`SkillLoader` 从 `skills` 目录读取 `SKILL.md`、扩展元数据、引用资料、脚本和资源文件。`SkillRegistry` 保存加载后的 `SkillDefinition` 对象，并通过 `SkillDiscoveryIndex` 支持 top-k 检索。

skill 选择阶段只使用摘要信息：名称、描述、触发条件、输入、输出和允许使用的工具。完整的 skill 正文会在某个 skill 被选中之后再使用。

## Tool 系统

`ToolGateway` 是工具执行的控制边界。它检查工具是否被允许，校验基于 schema 的参数，应用最大调用次数和重复调用策略，询问 `HumanApprovalGate` 是否需要人工确认，按超时和重试策略执行工具，返回结构化失败信息，并记录追踪事件。现有工具包括 Markdown 写入、DOCX 读取和 RAG 搜索。

## RAG 系统

当前 RAG 组件包括 `DocumentChunker`、`DocumentChunk`、文档加载器、`KeywordIndex`、`VectorStore`、`HybridRetriever`、`QueryTermReranker`、embedding 提供方接口和 `RAGCitationFormatter`。

RAG 流水线：文档加载器 -> 元数据分块器 -> 关键词索引 -> embedding 提供方 -> 向量存储 -> 混合检索 -> 重排序 -> 引用格式化器 -> Agent 上下文。

默认的本地测试路径使用确定性 embeddings，因此单元测试不需要网络访问。API embedding 提供方和本地 HTTP embedding 提供方是通过依赖注入接入的边界，可用于兼容 OpenAI 风格 API 或未来的本地 embedding 服务。

## Memory 系统

Agent 可以使用会话记忆、摘要记忆、用户画像记忆和 `MemoryCompressor`。这样可以把短期对话上下文、压缩摘要，以及长期保存的用户/研究画像笔记分开管理。

## Trace 与状态

`TraceRecorder` 记录运行时行为的结构化事件。`StateStore` 持久化检查点状态，使每次运行都能在 `outputs/runs/<run_id>` 下留下可检查的产物。运行时检查点会保存用户输入，`YCAgentRuntime.resume_from_state` 则基于已保存输入和可选的重定向指令提供保守的重放能力。

## Desktop 边界

`yc_agents/desktop` 中的桌面端后端通过 FastAPI 暴露运行时操作。`desktop` app 是一个基于 Electron 和 React 的外壳，用来启动运行并查看运行产物。桌面端 UI 是观察状态、追踪、工具调用和审批的可观测性界面，不是核心 Agent 智能本身。

## MCP 边界

MCP 被视为外部工具/资源的协议边界。Function Calling 是模型请求调用工具的方式；`ToolGateway` 是校验和控制该调用的控制层；MCP 则是 gateway 后方可能的工具来源之一。

仓库包含用于文件系统 MCP 服务端演示的 `mcp_servers.json`，以及可测试的 `MCPClientConfig`/`StaticMCPClient` 边界。单元测试不会启动 `npx` 或外部 MCP 子进程。

## 失败处理模型

当前失败处理包括 JSON 协议兜底事件、允许工具检查、schema 校验、审批状态追踪、超时、重试、重复调用检测、最大调用次数控制、结构化工具失败，以及输出持久化。工具失败会作为观察结果返回给 Agent，使模型能够解释失败原因或调整策略。

## 当前限制

- 默认 runtime 在文档加载之前只有一个空的内存 RAG 索引。
- RAG 评估用例已经存在，但聚合检索指标需要在有语料的情况下运行评估框架。
- ToolGateway 策略是每个运行时 gateway 实例内存级别的；尚未实现分布式或持久化的工具预算。
- Resume 是保守的用户输入重放，不是完整 VM 风格的中间帧续跑。
- MCP 配置和适配器边界已经存在；生产级子进程生命周期管理有意放在这个原型之外。

## 面试讲解映射

- 运行时边界：`YCAgentRuntime`。
- Agent 边界：`SkillRuntimeAgent`。
- Skill 加载：`SkillLoader` 和 `SkillRegistry`。
- 工具安全边界：`ToolGateway` 和 `HumanApprovalGate`。
- 可观测性：`TraceRecorder`、`StateStore` 和桌面端运行视图。
- RAG 边界：分块器、索引/存储、搜索工具和引用格式化器。
