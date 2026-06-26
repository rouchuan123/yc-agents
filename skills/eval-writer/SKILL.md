---
name: eval-writer
description: 当用户需要为 Agent、RAG、工具调用、Skill、Harness、trace/state、回归测试、自动化指标、人工 rubric、LLM-as-Judge 或面试可讲的评测体系设计 eval 时使用。
triggers:
  - eval
  - 评估
  - 评测
  - Agent 评测
  - RAG 评估
  - 工具调用评估
  - trace 评估
  - LLM-as-Judge
  - 回归测试
  - 自动化指标
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
allowed_tools:
  - workspace_files
  - file_reader
  - markdown_writer
  - rag_search
examples:
  - 帮我给这个 Agent 写 eval
  - 为这个功能设计评估用例和指标
  - 设计一套 RAG 评估方案
  - 看看这个 Agent 还缺哪些评测
  - 生成一份面试能讲清楚的 Agent eval 方案
---

# Eval Writer

这个 Skill 面向中文用户，用于把 Agent、RAG、工具链、Skill 或功能需求转化为可复盘、可回归、可面试讲清楚的评估方案。

## 核心原则

默认先输出中文评估方案。只有用户明确要求时，才生成 JSONL、写入 `eval/cases/*.jsonl`、修改测试、改 runner/report 或创建文件。不要默认写文件。

先定义失败模式，再设计用例；先绑定可观察证据，再谈成功率。Agent eval 不能只看最终回答是否顺眼，还要看 Skill 选择、工具调用、trace、state、RAG 证据、错误恢复和人工兜底。

## 工作流程

1. 明确被评估对象：Agent、Skill、RAG、工具调用、runtime、单个功能或整条任务链路。
2. 阅读项目上下文：优先看 `README.md`、`docs/architecture.md`、`docs/evaluation-report.md`、`yc_agents/eval/*`、`eval/cases/*`、相关 `tests/*` 和目标模块。
3. 说明当前项目已有评测资产和缺口；区分已确认事实、基于代码的推断、未确认事项。
4. 设计评估维度：任务成功、Skill 选择、allowed tools、ToolGateway、trace/state、RAG 命中、引用可靠性、输出格式、错误恢复、延迟、回归风险。
5. 为每个维度设计少量高价值 case：覆盖正例、边界、反例、权限/安全边界、工具失败、检索噪声、幻觉、上下文污染和回归场景。
6. 映射判定方式：自动化指标优先，复杂质量用人工复核 rubric；不要把关键词命中包装成完整语义正确。
7. 给出面试讲法：说明为什么这样评、能证明什么、不能证明什么、下一步如何升级到 A/B、LLM-as-Judge 或线上指标。

## 默认输出结构

```markdown
## 评估目标

## 已有上下文与当前项目缺口

## 评估维度

## 建议 Eval Cases

## 指标与判定方式

## 自动化指标

## 人工复核 Rubric

## 执行与复盘流程

## 面试讲法

## 后续可落地文件
```

## Case 设计字段

默认用中文表格或列表描述 case，不直接生成 JSONL。每个 case 至少包含：

- `id`：稳定、可读、按类别命名。
- `category`：如 `skill_selection`、`tool_use`、`rag_qa`、`trace_state`、`error_recovery`、`output_quality`。
- `input`：用户输入。
- `expected_behavior`：期望行为，不只写关键词。
- `observable_evidence`：从最终输出、工具调用、trace、state、检索结果或写入文件中看什么。
- `judge_method`：关键词、结构字段、工具调用、trace 事件、RAG source、人工 rubric 或 LLM-as-Judge。
- `risk`：这个 case 能防什么回归。
- `interview_value`：面试时能引出哪个技术点。

## YCore 评估重点

针对本项目，优先覆盖：

- Skill 选择：是否能在 `code-review`、`eval-writer` 等 Skill 中选对。
- 工具边界：是否遵守 allowed tools，是否经过 `ToolGateway`。
- trace 评估：是否记录 `tool_called`、`tool_failed`、`tool_denied`、`tool_retry` 等关键事件。
- state 评估：是否留下可复核状态，是否支持恢复和复盘。
- RAG 评估：是否调用 `rag_search`，是否命中 reference source，回答是否受材料约束。
- 输出评估：是否中文、结构清楚、不编造运行结果。
- 错误恢复：工具参数错、权限拒绝、检索无结果、重复调用时如何处理。
- 回归测试：Skill、prompt、工具 schema、RAG 策略或模型变化后如何比较。

## 指标分层

| 层级 | 指标 | 判定方式 |
| --- | --- | --- |
| 任务结果 | task success、关键词覆盖、结构完整性 | 自动 + 人工 |
| 工具调用 | required tools、forbidden tools、调用次数、失败恢复 | trace 自动检查 |
| RAG | retrieval_hit、citation_precision、材料一致性 | 自动 + 人工 |
| 运行过程 | latency、tool_retry、tool_denied、loop stopped | trace/state |
| 质量 | 有用性、事实性、解释力、面试可讲性 | 人工 rubric 或 LLM-as-Judge |

## JSONL 与文件写入门槛

只有当用户明确说“生成 JSONL”“写入 `eval/cases/...`”“补测试”“改 runner”“直接落地”时，才输出可写入文件的 JSONL 或修改项目文件。

如果需要生成 JSONL，优先兼容当前 `EvalCase` schema：

```json
{"id":"case-id","category":"rag_qa","input":"用户输入","expected_keywords":["关键词"],"required_tools":["rag_search"],"reference_sources":["demo-research-notes.md"]}
```

如果评估方案需要更丰富字段，先说明当前 runner 不支持这些字段，再建议作为后续 schema 升级，不要悄悄生成无法执行的 case。

## 真实性要求

- 没运行 eval 或测试，就不要说已通过。
- 没看到 trace/state，就不要假设工具调用成功。
- 没有 reference source，就不要声称 RAG 答案有依据。
- 自动化指标和人工判断必须分开写。
- 如果发现文档、case、runner 或工具暴露范围不一致，要列入当前项目缺口。
