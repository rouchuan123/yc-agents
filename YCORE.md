# YCore 项目指令

YCore 是一个面向中文用户、面向 code agent 的本地 Agent Harness。当前主线是让 agent 基于本地代码证据完成项目审查、工具边界验证、trace/state 复盘和 eval 设计。

## 面试主线

一句话讲法：YCore 是一个可观测、可评测、可验证的 code-agent 运行时。它通过 Skill 组织能力，通过 ToolGateway 管控工具，通过 trace/state 记录过程，通过 eval 和 VerificationGate 判断任务是否真的完成。

## 行为要求

- 优先读取本地代码、配置、测试和文档证据，不凭印象下结论。
- 让选中的 Skill 定义具体工作流；全局层只负责运行边界。
- 使用工具后要尊重 trace、state 和 verification 输出。
- 工作区文件访问必须限制在 active workspace 内。
- 不要编造文件、路径、命令输出、测试结果或项目事实。
- 做实现变更后，运行与变更范围匹配的 focused tests。
- 面向用户的说明、文档和默认回复优先使用中文；代码标识、命令、API 名称和必要术语保留英文。
