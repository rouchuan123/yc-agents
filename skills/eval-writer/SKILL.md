---
name: eval-writer
description: 当用户需要为 Agent workflow、Skill、ToolGateway 工具边界、trace/state、verification、deterministic regression、人工 rubric、真实模型 smoke eval 或可选 LLM-as-Judge 设计 eval 时使用。
triggers:
  - eval
  - 评估
  - 评测
  - Agent eval
  - Skill eval
  - code review eval
  - 工具调用评估
  - trace 评估
  - LLM-as-Judge
  - 回归测试
  - deterministic eval
  - smoke eval
  - 人工 rubric
  - 测试数据
  - 用例设计
inputs:
  - product_context
  - expected_behavior
  - target_agent_or_feature
outputs:
  - eval_plan
  - metric_mapping
  - manual_rubric
  - interview_talking_points
  - gap_analysis
examples:
  - 帮我给这个 Agent workflow 写 eval
  - 为 code-review 设计 deterministic eval cases
  - 设计一套真实模型 smoke eval 和人工 rubric
  - 看看 ToolGateway 工具边界还缺哪些评测
---

# Eval Writer

这个 Skill 面向中文用户，用于为 Agent workflow、具体 Skill 和 YCore Agent Harness 设计可回归、可解释、可面试讲清楚的评测方案。默认先输出中文评估方案；只有用户明确要求落地时，才生成 JSONL、写入 `eval/cases/*.jsonl`、修改测试、改 runner/report 或创建文件。

## 核心原则

deterministic eval 是默认路径。它用固定 runtime、fake trace、已有 trace/state 字段或受控 fixture 验证工程闭环：Skill 选择是否正确、ToolGateway 是否拦住边界、required tools 是否调用、forbidden tools 是否未用、trace 是否完整、verification 是否被记录。

真实模型 smoke eval 面向手动验证和面试演示，只跑少量高价值 case。它不追求每日回归稳定性，而是用人工 rubric 判断当前 Skill 的输出质量：是否使用必要证据、是否遵守工具边界、是否完成关键步骤、建议是否可执行、是否诚实区分已确认事实和未确认事项。

不要把关键词命中包装成完整语义正确。关键词、字段和 trace 检查只能作为弱基线；输出质量、风险判断、证据充分性和建议可执行性必须交给人工 rubric 或可选 LLM-as-Judge。

RAG 只作为可选上下文，不是主要评测目标。只有当任务明确依赖本地资料检索时，才把 context retrieval 纳入 case；否则优先评测 Skill 选择、工具边界、trace/state 和 verification。不同领域 Skill 可以拥有不同 rubric，但复用同一套 eval runner 和 metrics。

## 工作流程

1. 明确被评估对象：Agent workflow、具体 Skill、ToolGateway、runtime、trace/state、verification 或某个具体工具链。
2. 阅读项目上下文：优先看 `README.md`、`docs/architecture.md`、`docs/evaluation-report.md`、`yc_agents/eval/*`、`eval/cases/*`、相关 `tests/*` 和目标模块。
3. 说明已有评测资产和缺口；区分已确认事实、基于代码的推断、未确认事项。
4. 设计维度：Skill 选择、工具边界、required/forbidden tools、trace 事件、state 输出、verification、错误恢复、输出质量、人工 rubric、可选 LLM-as-Judge。
5. 为每个维度设计少量高价值 case：覆盖正例、边界、反例、权限/安全边界、工具失败、上下文污染和回归场景。
6. 映射判定方式：deterministic 自动检查优先，复杂语义质量用人工 rubric；真实模型 smoke eval 单独标注为手动/面试路径。
7. 给出面试讲法：说明为什么 eval 不一定需要大模型参与、deterministic 能证明什么、smoke eval 能补什么、不能证明什么。

## 默认输出结构

```markdown
## 评估目标

## 已有上下文与当前项目缺口

## deterministic eval 设计

## 真实模型 smoke eval 设计

## 指标与判定方式

## 人工 rubric

## ToolGateway / trace / verification 覆盖

## 执行与复盘流程

## 面试讲法

## 后续可落地文件
```

## Case 设计字段

默认用中文表格或列表描述 case，不直接生成 JSONL。每个 case 至少包含：

- `id`：稳定、可读、按类别命名。
- `category`：如 `skill_selection`、`tool_use`、`tool_gateway`、`project_audit`、`change_review`、`verification`、`output_quality`。
- `input`：用户输入。
- `expected_behavior`：期望行为，不只写关键词。
- `observable_evidence`：从最终输出、工具调用、trace、state、verification 或写入文件中看什么。
- `judge_method`：关键词、结构字段、工具调用、trace 事件、人工 rubric 或 LLM-as-Judge。
- `risk`：这个 case 能防什么回归。
- `interview_value`：面试时能引出哪个技术点。

## YCore 评估重点

针对本项目，优先覆盖：

- Skill 选择：是否能在 `code-review`、`eval-writer` 等 Skill 中选对。
- 工具边界：是否只调用 `ycore.json` 已启用工具，是否经过 `ToolGateway`，是否误用已关闭工具。
- trace 评估：是否记录 `skill_selected`、`tool_called`、`tool_failed`、`tool_denied`、`tool_retry` 等关键事件。
- state 评估：是否留下可复核状态，是否支持恢复和复盘。
- verification 评估：是否选择最小验证命令，是否诚实报告未运行或失败。
- 输出质量：是否中文、结构清楚、证据充分、不编造运行结果。
- 错误恢复：工具参数错、权限拒绝、检索无结果、重复调用时如何处理。
- 回归测试：Skill、prompt、工具 schema、trace 字段或模型变化后如何比较。
- 可选上下文：RAG 只作为可选上下文，用于需求文档、历史 notes 或本地资料影响回答的场景。

## 指标分层

| 层级 | 指标 | 判定方式 |
| --- | --- | --- |
| 工程闭环 | Skill 选择、required tools、forbidden tools、trace/state、verification | deterministic 自动检查 |
| 工具调用 | ToolGateway 边界、调用次数、失败恢复、权限拒绝 | trace 自动检查 |
| 输出结构 | 中文、字段完整、结论/证据/建议齐全 | 自动 + 人工 |
| 分析质量 | 风险真实性、链路追踪、证据充分、建议可执行 | 人工 rubric 或 LLM-as-Judge |
| 演示可信度 | 少量真实模型 smoke eval 是否能稳定讲清楚 | 手动复盘 |

## JSONL 与文件写入门槛

只有当用户明确说“生成 JSONL”“写入 `eval/cases/...`”“补测试”“改 runner”“直接落地”时，才输出可写入文件的 JSONL 或修改项目文件。

如果需要生成 JSONL，优先兼容当前 `EvalCase` schema：

```json
{"id":"code-review-project-map-001","category":"project_audit","input":"请审查当前仓库，先给出项目地图和入口链路。","expected_keywords":["项目地图","入口"],"required_tools":["workspace_files","file_reader","code_search"],"expected_trace_events":["tool_called"],"forbidden_tools":["web_search"]}
```

如果评估方案需要更丰富字段，先说明当前 runner 不支持这些字段，再建议作为后续 schema 升级，不要悄悄生成无法执行的 case。

## 真实性要求

- 没运行 eval 或测试，就不要说已通过。
- 没看到 trace/state，就不要假设工具调用成功。
- 没看到 verification 输出，就不要声称验证通过。
- 自动化指标、人工 rubric 和可选 LLM-as-Judge 必须分开写。
- 如果发现文档、case、runner 或工具暴露范围不一致，要列入当前项目缺口。
