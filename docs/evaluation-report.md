# YCore 评估报告

## 目的

这份报告用于跟踪 Agent 在通用本地 Agent Harness 中是否真正完成任务，而不只是单元测试是否通过或回答看起来顺眼。具体评测对象由 Skill 决定；当前 case 先覆盖 `code-review` 和 `eval-writer` 这两个验证 Skill。

## 用例集合

- Runtime 主线用例：`eval/cases/runtime_cases.jsonl`
- ToolGateway 边界用例：`eval/cases/toolgateway_cases.jsonl`
- code-review 用例：`eval/cases/code_review_cases.jsonl`
- eval-writer 用例：`eval/cases/eval_writer_cases.jsonl`
- 可选上下文用例：`eval/cases/context_cases.jsonl`

当前覆盖项目体检、变更审查、测试缺口、Skill 选择、工具边界、trace/state、verification、输出质量和可选上下文检索。后续新增其他领域 Skill 时，新增对应 eval cases 即可复用同一套 runner 和 metrics。

## Eval 是否需要大模型

YCore 的默认 eval 不依赖大模型。deterministic eval 用固定 runtime、fake trace 或已有 trace 字段验证工程闭环：Skill 是否选对、工具是否被调用、禁止工具是否没用、trace 是否完整、verification 是否通过。

真实模型 smoke eval 只作为手动验证和面试演示：少量 case 调真实模型，重点用人工 rubric 评估当前 Skill 的输出质量。关键词命中只能做弱基线，不能代表语义质量。

## 指标

- Skill 选择成功率：检查是否选中期望 Skill。
- 工具成功率：检查必要工具是否真的出现在 trace 的 `tool_called` 事件中。
- Trace 事件成功率：检查运行过程是否出现预期事件，例如 `tool_called` 或 `skill_selected`。
- 禁止工具成功率：检查 `web_search` 等禁止工具没有被调用。
- Verification 成功率：检查最小验证命令是否被选择、运行或诚实说明未运行原因。
- 输出质量：人工 rubric 判断证据充分性、风险真实性、建议可执行性和中文结构清晰度。
- 可选上下文命中率：仅在 case 明确依赖本地上下文时检查 retrieval hit。

## ToolGateway 可观测性

ToolGateway 评测不只看回答内容，也统计 trace 中的工具事件：

- `tool_called`：工具成功执行。
- `tool_denied`：策略拒绝，说明权限边界生效。
- `tool_validation_failed`：参数 schema 校验失败。
- `tool_retry`：重试触发。
- `tool_failed`：工具执行异常或超时。
- `tool_needs_approval`：需要人工审批。

这些事件会汇总为 `tool_event_totals` 和 `tool_failure_labels`，用于解释一次 Agent 运行失败到底是策略、参数、工具实现还是外部环境问题。

## Verification Gate

VerificationGate 把“任务完成”拆成可检查证据：

- final output 非空。
- JSON message type 合法。
- 目标文件存在。
- 工具结果存在。
- 必要关键词或 checklist 项已覆盖。
- 命令结果 exit code 为 0。

报告中只要有一个 check 失败，整体 verification report 就失败。这样可以避免 Agent 用自然语言声称完成，但没有证据。

## 人工 Rubric

真实模型 smoke eval 或复杂输出用人工 rubric 判断。不同领域 Skill 可以有不同 rubric；当前 `code-review` 样例重点看：

| 维度 | 观察点 |
| --- | --- |
| 证据 | 是否读取关键文件，是否给出路径或明确证据来源 |
| 链路 | 是否追到入口、核心逻辑、工具/状态和测试 |
| 风险 | 是否指出真实风险，而不是泛泛建议 |
| 测试 | 是否识别已有覆盖和关键缺口 |
| 诚实性 | 是否区分已确认事实、推断和未确认事项 |
| 可执行性 | 建议是否能转成测试、修复或验证命令 |

## 当前基线

运行：

```powershell
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output outputs/eval/baseline.json
```

也可以运行离线 demo：

```powershell
python scripts/demo_eval_run.py
```

在基线输出经过人工检查之前，不要汇报聚合成功率数字。
