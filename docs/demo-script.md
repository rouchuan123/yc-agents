# YCore Demo Script

## Demo Goal

Show that `YCore` is a controllable Agent runtime for research workflows: skill selection, retrieval, tool calls, memory, trace, approval, and verification are visible engineering boundaries.

## Before Demo

- Install Python dependencies with `pip install -r requirements.txt`.
- Install desktop dependencies with `npm install` inside `desktop`.
- Run `python -m pytest -q`.
- Run `cd desktop` then `npm test -- --run`.

## Scenario 1: Skill Selection

Prompt:

```text
帮我围绕多智能体论文助手写一个开题报告大纲。
```

Show how the request enters `YCAgentRuntime`, how `SkillRuntimeAgent` selects the opening-report skill, and how the run records trace/state files.

## Scenario 2: RAG-Assisted Answer

Prompt:

```text
基于已有资料检索证据，并生成带引用的文献综述片段。
```

Show that RAG is a tool boundary rather than hidden prompt text. Current retrieval is keyword-first; later phases add hybrid retrieval, embeddings, and citation metrics.

## Scenario 3: Tool Call And Trace

Prompt:

```text
把结果写入 markdown 文件，并说明为什么需要工具调用。
```

Show that tool calls pass through `ToolGateway`, allowed-tool checks, approval checks, and trace recording.

MCP is shown as an external tool/resource protocol. In this project the filesystem MCP config is kept separate and MCP tools still pass through ToolGateway, approval, path policy, and trace.

## What To Show In Outputs

- `outputs/<run_id>/input.md`
- `outputs/<run_id>/context.json`
- `outputs/<run_id>/final_output.md`
- `outputs/<run_id>/trace.json`
- `outputs/<run_id>/state.json`
- `outputs/<run_id>/verification.json`

## Five-Minute Talk Track

YCore is a Skill-driven Research Agent for graduate research workflows. The point is not to replace a thesis writer with one prompt, but to show how a long task can be decomposed into skills, retrieval, tool calls, memory, trace, approval, and verification. In the demo I will show how a user request enters `YCAgentRuntime`, how `SkillRuntimeAgent` selects or executes a skill, how tools go through `ToolGateway`, and how the run leaves trace and state files for debugging.

## Common Interview Follow-Ups

- How is this different from a chatbot?
- How are tool calls validated and approved?
- What happens when a tool fails?
- How would you measure task success?
- How does RAG avoid unsupported claims?
- How would MCP fit behind the same ToolGateway boundary?
