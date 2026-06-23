# YCore 演示脚本

## 演示目标

展示 `YCore` 是一个面向科研工作流的可控 Agent 运行时：skill 选择、检索、工具调用、记忆、追踪、审批和验证都是可见、可解释的工程边界。

## 演示前准备

- 使用 `pip install -r requirements.txt` 安装 Python 依赖。
- 在 `desktop` 目录内执行 `npm install` 安装 desktop 依赖。
- 运行 `python -m pytest -q`。
- 先运行 `cd desktop`，再运行 `npm test -- --run`。

## 场景 1：Skill 选择

提示词：

```text
帮我围绕多智能体论文助手写一个开题报告大纲。
```

展示请求如何进入 `YCAgentRuntime`，`SkillRuntimeAgent` 如何选择开题报告 skill，以及一次运行如何记录追踪/状态文件。

## 场景 2：RAG 辅助回答

提示词：

```text
基于已有资料检索证据，并生成带引用的文献综述片段。
```

展示 RAG 是一个工具边界，而不是藏在提示词里的文本拼接。当前检索以关键词优先；后续阶段会加入混合检索、embeddings 和引用指标。

## 场景 3：工具调用与追踪

提示词：

```text
把结果写入 markdown 文件，并说明为什么需要工具调用。
```

展示工具调用会经过 `ToolGateway`、允许工具检查、审批检查和追踪记录。

MCP 作为外部工具/资源协议展示。在本项目中，文件系统 MCP 配置独立保存，MCP 工具仍然要经过 ToolGateway、审批、路径策略和追踪。

## 输出中要展示的内容

- `outputs/<run_id>/input.md`
- `outputs/<run_id>/context.json`
- `outputs/<run_id>/final_output.md`
- `outputs/<run_id>/trace.json`
- `outputs/<run_id>/state.json`
- `outputs/<run_id>/verification.json`

## 五分钟讲解稿

YCore 是一个面向研究生科研工作流的技能驱动科研 Agent。它的重点不是用一句提示词替代论文写作者，而是展示一个长任务如何被拆解为 skills、检索、工具调用、记忆、追踪、审批和验证。在演示中，我会展示用户请求如何进入 `YCAgentRuntime`，`SkillRuntimeAgent` 如何选择或执行 skill，工具如何通过 `ToolGateway`，以及一次运行如何留下用于调试的追踪和状态文件。

## 常见面试追问

- 它和普通 chatbot 有什么区别？
- 工具调用如何校验和审批？
- 工具失败时会发生什么？
- 如何衡量任务是否成功？
- RAG 如何避免没有证据支撑的结论？
- MCP 如何接入同一个 ToolGateway 边界？
