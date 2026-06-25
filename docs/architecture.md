# YCore 架构

## 定位

YCore 是一个面向中文用户的本地 CLI Agent runtime。全局层保持通用：接收用户请求、选择合适的 Skill、注入工作区和记忆上下文、执行受控工具，并留下可复核的运行记录。

具体业务工作流属于 Skill。全局 prompt 不假设固定场景，也不默认承诺某一类文件处理、写作或分析任务。

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
- 将 workspace、记忆、RAG 上下文和技能说明交给 `PromptBuilder` 组装为模型消息。

`PromptBuilder` 是核心系统 prompt 的集中入口，负责 plain answer、skill selection、skill execution、retry 和 observation 协议。

## 项目指令

`ProjectInstructionLoader` 从当前 workspace 读取两层项目指令：

1. `YCORE.md`
2. `.ycore/YCORE.md`

合并顺序是内置 YCore 协议、根 `YCORE.md`、本地 `.ycore/YCORE.md`、模式协议。本地指令排在后面，因此在普通偏好冲突时优先；但项目指令不能覆盖工具 JSON 协议、真实性规则、工作区边界或 allowed tools。

## Skill 边界

`SkillLoader` 从 `skills` 目录读取：

- `SKILL.md`
- `references/`
- `scripts/`
- `assets/`

当前仓库默认发布两个中文 Skill：

- `code-review`：审查项目结构、架构、风险和测试缺口。
- `eval-writer`：设计 eval case、指标、测试数据和评估流程。

Skill 负责定义何时适用、需要哪些输入、允许哪些工具、如何解释输出和失败。

## Tool 边界

`ToolGateway` 负责工具权限、参数 schema 校验、审批策略、追踪和失败返回。

默认 CLI runtime 暴露通用工具：

- `workspace_files`
- `file_reader`
- `markdown_writer`
- `rag_search`
- `web_search`

底层 DOCX 处理包仍保留在代码库中，但它不是默认运行时工具。

## 记忆、追踪和状态

YCore 保留会话记忆、摘要记忆和用户画像记忆。每次运行会在当前 workspace 的 `.ycore/runs/` 下留下可复核产物，包括输入、输出、trace 和 state checkpoint。

## 当前限制

- 只保留 CLI 端。
- 默认发布的 Skill 仍是示例业务能力，不代表 YCore 的全局身份。
- 复杂工作流需要通过 Skill 包显式引入。
- 本地 `.ycore/YCORE.md` 是工作区私有指令层，不应提交到仓库。
