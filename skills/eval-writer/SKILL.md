---
name: eval-writer
description: 当用户需要为项目、Agent、工具链或功能设计评估方案、eval case、指标、测试数据、验收标准或评估报告模板时使用。
triggers:
  - eval
  - 评估
  - 评测
  - 用例设计
  - 指标设计
  - 测试数据
inputs:
  - product_context
  - expected_behavior
outputs:
  - eval_plan
allowed_tools:
  - workspace_files
  - file_reader
  - markdown_writer
  - rag_search
examples:
  - 帮我给这个 Agent 写 eval
  - 为这个功能设计评估用例和指标
  - 生成一份验收测试数据清单
---

# Eval 编写 Skill

这个 Skill 面向中文用户，用于把一个项目、Agent、工具或功能转化为可执行的评估方案。

## 工作流程

1. 先明确被评估对象：功能目标、用户场景、成功标准、失败模式和可观察输出。
2. 如需了解项目上下文，使用 `workspace_files` 和 `file_reader` 阅读 README、测试、入口和相关模块。
3. 设计 eval 时覆盖正例、边界条件、错误输入、权限/安全边界、恢复路径和回归风险。
4. 指标要可判定：优先使用通过/失败、关键词命中、结构字段、工具调用轨迹、人工评分 rubric 等。
5. 测试数据要小而代表性强，避免一次性生成过多重复样例。
6. 用户要求保存时，用 `markdown_writer` 写出中文 eval 方案或用例文件。

## 输出要求

- 默认用中文回答。
- 每个 eval case 都要包含输入、期望行为、判定方法和风险说明。
- 明确哪些指标可以自动化，哪些需要人工复核。
- 不要编造已经存在的测试结果；没运行就不要说已通过。
- 对 Agent/工具评估，要把工具调用、状态记录和最终输出都纳入检查面。

## 推荐结构

```markdown
## 评估目标

## 评估维度

## Eval Cases

## 指标与判定

## 测试数据

## 执行与复盘流程
```
