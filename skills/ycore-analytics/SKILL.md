---
name: ycore-analytics
description: 当用户询问 YCore 当前工作区的运行情况、工具失败、verification、eval 通过率、Skill 使用分布、denied/forbidden 工具事件或 Agent 可观测性统计时使用。
triggers:
  - 运行情况
  - 工具失败
  - eval 通过率
  - verification
  - 可观测性
  - 最近失败
  - denied 工具
  - forbidden 工具
  - Skill 使用
  - analytics
inputs:
  - workspace_analytics
  - sqlite_mcp
outputs:
  - analytics_summary
  - failure_analysis
  - eval_summary
allowed_tools:
  - mcp_sqlite_list_tables
  - mcp_sqlite_describe_table
  - mcp_sqlite_query_readonly
examples:
  - 最近 20 次 Agent 运行情况怎么样？
  - 哪些工具最近最容易失败？
  - 最近 eval case 通过率如何？
  - 有没有工具被拒绝调用？
---

# YCore Analytics Skill

这个 Skill 面向中文用户，用于查询当前 workspace 的 YCore analytics SQLite 数据库。它只做只读分析，不修改数据，不生成写 SQL，不假装查询未启用的数据源。

## 工作流程

1. 先调用 `mcp_sqlite_list_tables` 查看可用表。
2. 再按需调用 `mcp_sqlite_describe_table` 查看 `agent_runs`、`trace_events`、`verification_checks`、`eval_results` 的列。
3. 使用 `mcp_sqlite_query_readonly` 执行只读 `SELECT` 或 `WITH ... SELECT` 查询。
4. 默认限制最近数据，例如 `ORDER BY started_at DESC LIMIT 20`。
5. 输出中文结论，区分已查询事实、基于数据的推断、未开启 SQLite MCP、数据库为空和查询失败。

## 推荐查询方向

- 最近运行概览：查 `agent_runs`。
- 失败运行分析：查 `agent_runs.status`、`error_type`、`error_message`。
- 工具失败统计：查 `trace_events` 中 `tool_failed`、`tool_denied`、`tool_validation_failed`。
- verification 通过率：查 `agent_runs.verification_passed` 和 `verification_checks`。
- eval case 通过率：查 `eval_results`。
- Skill 使用分布：查 `agent_runs.selected_skill`。
- denied/forbidden 工具事件：查 `trace_events.event_type = 'tool_denied'`。

## 输出要求

- 先给高信号结论，再给关键数据。
- 不要输出大段原始 SQL 结果。
- 如果工具返回 `ok=false`，说明错误原因，并给出用户可执行的下一步。
- 如果没有数据，说明 analytics 可能未开启或当前 workspace 还没有记录。
- 不要编造表、列、统计数字或查询结果。
