# YCore 面试笔记

## 60 秒项目介绍

YCore 是一个面向中文用户的本地 CLI Agent runtime。项目重点不是把某个垂直场景写进长 prompt，而是展示 Agent 工程的关键边界：Skill 选择、项目指令注入、工具权限、工作区隔离、状态追踪和结果验证。

具体能力由 `skills/` 下的 Skill 承载。当前默认发布两个中文示例 Skill：`code-review` 用于项目审查，`eval-writer` 用于设计评估方案。

## 为什么强调 Skill 层

Skill 让具体工作流成为可维护资产：

- 触发条件和示例输入写在 `SKILL.md`。
- allowed tools 明确声明。
- 参考资料、脚本和资产跟随 Skill 管理。
- 全局 prompt 不需要为某个场景持续膨胀。

## 最难的技术点

最难的是把模型自由度控制在工程边界内。模型负责判断何时使用技能、如何解释结果；runtime 负责 JSON 协议、工具权限、工作区边界、trace 和 state。项目指令可以影响偏好和协作方式，但不能覆盖硬运行规则。

## 工具调用失败处理

`ToolGateway` 会校验工具名、参数 schema、权限和审批策略。工具失败时返回结构化错误，运行 trace 中会记录失败事件，模型可以据此解释原因或要求用户补充信息。

## 当前发布范围

- 只保留 CLI 端。
- 默认发布 `code-review` 和 `eval-writer` 两个中文示例业务 Skill。
- 支持根 `YCORE.md` 与本地 `.ycore/YCORE.md` 两层项目指令。
- 默认工具集保持通用：工作区文件、文件读取、Markdown 写入、RAG 检索和 web search。

## 工程可信度

项目有单元测试覆盖 CLI runtime、技能加载、技能发现、prompt builder、项目指令加载、工具网关、RAG、记忆和运行输出。`scripts/test.ps1` 只运行 Python 测试，和当前 CLI-only 范围保持一致。
