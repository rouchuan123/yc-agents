# YCore 评估报告

## 目的

这份报告用于跟踪 Agent 在通用本地 Agent Harness 中是否真正完成任务，而不只是单元测试是否通过或回答看起来顺眼。具体评测对象由 Skill 决定，并受当前 workspace 影响；当前 case 重点评估“通用本地工作区审查”能力，要求 Agent 先探测事实，再决定是否读取文档、使用 Git 证据、推断测试命令，并通过 trace/state/verification 复盘运行过程。

## 用例集合

- Runtime 主线用例：`eval/cases/runtime_cases.jsonl`
- ToolGateway 边界用例：`eval/cases/toolgateway_cases.jsonl`
- code-review 用例：`eval/cases/code_review_cases.jsonl`
- eval-writer 用例：`eval/cases/eval_writer_cases.jsonl`
- 可选上下文用例：`eval/cases/context_cases.jsonl`

当前覆盖通用工作区的项目体检、变更审查、测试缺口、Skill 选择、工具边界、trace/state、verification、输出质量和文档上下文读取。case 不假设工作区一定有 `.git`、README、测试目录或固定语言框架；后续新增其他 demo 工作区或领域 Skill 时，新增对应 eval cases 即可复用同一套 runner 和 metrics。

当前 case 采用 Eval Case 2.0 分层：

- `real_smoke`：调用真实模型，验证 Skill 选择、业务 workflow、证据链和输出结构。适合面试演示和发布前抽样。
- `deterministic`：优先用固定 runtime、fake trace、工具 fixture 或本地状态检查。适合日常回归，不依赖模型发挥。
- `manual_rubric`：自动指标只做弱基线，最终由人工 rubric 判断复杂质量，例如诚实性、风险真实性和上下文解释质量。

## Eval 是否需要大模型

YCore 的默认 eval 不依赖大模型。deterministic eval 用固定 runtime、fake trace 或已有 trace 字段验证工程闭环：Skill 是否选对、工具是否被调用、禁止工具是否没用、trace 是否完整、verification 是否通过。

真实模型 smoke eval 只作为手动验证和面试演示：少量 case 调真实模型，重点用人工 rubric 评估当前 Skill 的输出质量。关键词命中只能做弱基线，不能代表语义质量。

## 指标

- Skill 选择成功率：检查 `skill_selected` trace 中是否出现 `expected_skill`。
- 工具成功率：检查必要工具是否真的出现在 trace 的 `tool_called` 事件中。
- Trace 事件成功率：检查运行过程是否出现预期事件，例如 `tool_called` 或 `skill_selected`。
- State 步骤成功率：检查 `state.json` 的 checkpoint history 是否包含 `expected_state_steps`。
- 禁止工具成功率：检查 `web_search` 等禁止工具没有被调用。
- Verification 成功率：检查最小验证命令是否被选择、运行，且 state checkpoint 中的 verification 与 `expected_verification` 一致；人工复盘时仍要看未运行或失败原因是否诚实。
- 输出结构：检查 `expected_output_sections` 是否出现在最终输出中。
- 输出质量：人工 rubric 判断证据充分性、风险真实性、建议可执行性和中文结构清晰度。
- 可选上下文命中率：仅在 case 明确依赖本地上下文时检查 retrieval hit。

## Case 字段

每行 JSONL 是一个独立 eval case。当前 runner 支持：

| 字段 | 用途 |
| --- | --- |
| `id` | 稳定 case 标识，用于报告和失败定位。 |
| `category` | 评测类别，例如 `project_audit`、`tool_gateway`、`verification`。 |
| `judge_mode` | `real_smoke`、`deterministic` 或 `manual_rubric`。 |
| `input` | 真实喂给 Agent 的中文请求。 |
| `expected_skill` | 期望选中的 Skill，来自 `skill_selected` trace。 |
| `expected_keywords` | 最终输出必须包含的弱基线关键词。 |
| `expected_output_sections` | 最终输出必须包含的章节或结构标签。 |
| `required_tools` | 必须出现在 `tool_called` trace 中的工具。 |
| `expected_trace_events` | 必须出现的 trace 事件，例如 `skill_selected`、`tool_called`。 |
| `expected_state_steps` | 必须出现在 `state.json` history 中的 checkpoint。 |
| `expected_verification` | 期望 verification 是否通过；省略则不检查。 |
| `forbidden_tools` | 不允许调用的工具。 |
| `reference_sources` | RAG / context case 的期望来源。 |
| `failure_notes` | 失败时优先排查什么，方便报告解释。 |

## ToolGateway 可观测性

ToolGateway 评测不只看回答内容，也统计 trace 中的工具事件：

- `tool_called`：工具成功执行。
- `tool_denied`：策略拒绝，说明权限边界生效。
- `tool_validation_failed`：参数 schema 校验失败。
- `tool_retry`：重试触发。
- `tool_failed`：工具执行异常或超时。
- `tool_needs_approval`：需要人工审批。

这些事件会汇总为 `tool_event_totals` 和 `tool_failure_labels`，用于解释一次 Agent 运行失败到底是策略、参数、工具实现还是外部环境问题。

当 `YCORE_ANALYTICS_ENABLED=true` 时，YCore 会把运行事件实时写入 workspace-local SQLite。运行 eval cases 时，`eval_results` 额外记录 case 级判定结果，便于后续通过 `ycore-analytics` 查询通过率、失败原因和工具边界回归情况。

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

真实模型 smoke eval 或复杂输出用人工 rubric 判断。不同领域 Skill 可以有不同 rubric；当前通用工作区 `code-review` 样例重点看：

| 维度 | 观察点 |
| --- | --- |
| 证据 | 是否先列出工作区文件事实，是否说明 README、docs、配置、源码目录、测试目录、`.git` 是否存在，是否给出路径或明确证据来源 |
| 链路 | 是否从已确认入口追到核心模块、外部命令/API/文件 IO 和输出层；没有入口时是否诚实说明无法确认 |
| 风险 | 是否指出真实风险，而不是泛泛建议 |
| 测试 | 是否从真实存在的测试目录、配置或脚本推断验证方式；没有测试线索时是否说明不能假设 |
| 诚实性 | 是否区分已确认事实、推断和未确认事项，是否避免把上一个项目的 `.git`、README 或测试命令迁移过来 |
| 可执行性 | 建议是否能转成测试、修复或验证命令 |

## 当前基线

运行真实 eval 前，先确认活动 workspace 指向你想评测的本地项目，或用显式 workspace wrapper 构造 runtime。`E:\code\Ycore-demo` 可作为一个普通源码目录样本：它没有 `.git`，因此特别适合验证 Agent 是否会先检查事实、不会假设当前工作区一定是 Git 仓库。直接在 `yc-agents` 根目录跑 runner 时，会读取 `data/workspaces.json` 中的 current workspace。

运行全部真实 runtime eval：

```powershell
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output outputs/eval/baseline.json
```

面试前推荐先跑：

```powershell
python -m yc_agents.eval.runner --cases eval/cases/code_review_cases.jsonl --output outputs/eval/real-code-review.json
python -m yc_agents.eval.runner --cases eval/cases/eval_writer_cases.jsonl --output outputs/eval/real-eval-writer.json
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output outputs/eval/real-runtime.json
```

`toolgateway_cases.jsonl` 更适合 deterministic 回归；`context_cases.jsonl` 会要求 Agent 机会式读取实际存在的 README、docs、配置、脚本或测试文件，并包含 `docs/requirements.md` 缺失时的诚实性 case。

也可以运行离线 demo：

```powershell
python scripts/demo_eval_run.py
```

在基线输出经过人工检查之前，不要汇报聚合成功率数字。
