# YCore 项目指令

YCore 是一个面向中文用户的通用 skill-driven 本地 Agent Harness。它的领域能力由 Skill 决定；全局层只负责 Skill 选择、工具边界、上下文注入、trace/state、eval 和 verification。

## 面试主线

一句话讲法：YCore 是一个可观测、可评测、可验证的通用 Agent 运行时。当前用 `code-review` 和 `eval-writer` 作为第一批验证 Skill，但未来可以继续加入其他领域 Skill，用同一套 Harness 验证新的 workflow。

## 行为要求

- 不要把 YCore 写成某个固定领域 Agent；具体工作流取决于 Skill。
- 优先读取本地证据，不凭印象下结论。
- 让选中的 Skill 定义具体工作流；全局层只负责运行边界。
- 使用工具后要尊重 trace、state 和 verification 输出。
- 工作区文件访问必须限制在 active workspace 内。
- 不要编造文件、路径、命令输出、测试结果或项目事实。
- 做实现变更后，运行与变更范围匹配的 focused tests。
- 面向用户的说明、文档和默认回复优先使用中文；代码标识、命令、API 名称和必要术语保留英文。
