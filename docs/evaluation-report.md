# YCore 评估报告

## 目的

这份报告用于跟踪 Agent 在本地 CLI runtime 中是否真正完成任务，而不只是单元测试是否通过。

## 用例集合

- 总用例数：0
- 建议类别：项目审查、Eval 方案生成、文件读取、RAG QA、工具使用、Markdown 输出、错误恢复
- 额外 RAG 专项用例：`eval/cases/rag_cases.jsonl` 中的 10 条

## 指标

- 任务成功率：人工评分前先使用基于关键词的基线。
- 工具成功率：计划在 `ToolGateway` 追踪指标扩展后统计。
- 检索命中率：计划在 RAG 元数据和引用指标扩展后统计。
- 引用精确率：计划在支持引用感知的 RAG 输出实现后统计。
- 平均延迟：由评估运行器测量。

当有内容语料库和引用抽取层接入运行器输出后，RAG 专项指标可以使用 `retrieval_hit` 和 `citation_precision`。

## 当前基线

运行：

```powershell
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output outputs/eval/baseline.json
```

第一次基线应使用有效的模型凭证生成，或使用确定性的运行时适配器进行本地验证。在基线输出经过人工检查之前，不要汇报聚合成功率数字。
