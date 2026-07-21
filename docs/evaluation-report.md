# YCore Eval 当前基线

> 当前权威基线：`20260630-211458`。
>
> 之前的 eval 记录和非正式结论都已作废，只保留为开发历史，不再代表当前质量口径。

## 目的

YCore eval 用来检查本地 Agent Harness 是否真的完成了任务，而不是只看最终回答是否流畅。具体领域与评测目标由 Skill 决定，Harness 只提供通用的执行、观测和验证能力。当前基线重点评估通用本地工作区审查链路，包括 `code-review`、`eval-writer`、ToolGateway 边界、上下文读取、trace/state 证据和 verification 诚实性。

本次基线使用的 active workspace 是：

```text
E:\code\Ycore-demo
```

这个 workspace 是一个普通源码目录，不应该默认假设它一定有 `.git`、固定测试命令或固定框架。这个设定是故意的：eval 要检查 Agent 是否会先探测事实，而不是把上一个项目的 `.git`、README 或测试命令迁移过来。

## 当前运行

当前接受的真实模型 eval 运行发生在 2026-06-30，统一时间戳是：

```text
20260630-211458
```

输出 JSON 文件：

- `outputs/eval/20260630-211458-code-review.json`
- `outputs/eval/20260630-211458-eval-writer.json`
- `outputs/eval/20260630-211458-runtime.json`
- `outputs/eval/20260630-211458-toolgateway.json`
- `outputs/eval/20260630-211458-context.json`

代表性运行证据在：

```text
E:\code\Ycore-demo\.ycore\runs\session_20260630_ea86176d\<run_id>\
```

本次运行的详细复盘见 `docs/eval-run-20260630-211458.md`。

## 这次基线说明了什么

这次运行证明真实模型 eval 链路可以端到端跑通：

- 用户的 PowerShell session 已从 `.env` 加载模型 API key。
- 五个真实 eval suite 都生成了 JSON 输出。
- trace/state/final_output 写入了 active workspace。
- 每个 case 的 Skill 选择都成功。
- 每个 case 的 state checkpoint 都成功。
- 每个 case 都没有调用被禁止的 `web_search`。

这次运行也暴露了当前质量缺口：

- required tools 的调用还不够稳定。
- 部分工具调用存在 schema 错误或依赖降级行为。
- 架构审查 case 触发了工具调用次数上限。
- 多个输出结构检查过于依赖精确标题，需要人工复核。
- 少数关键词失败只是弱匹配失败，不能直接等同于语义质量差。

## Suite 概览

| Suite | 文件 | Case 数 | 自动指标全绿 case 数 |
| --- | --- | ---: | ---: |
| code-review | `20260630-211458-code-review.json` | 6 | 0 |
| eval-writer | `20260630-211458-eval-writer.json` | 5 | 2 |
| runtime | `20260630-211458-runtime.json` | 6 | 1 |
| toolgateway | `20260630-211458-toolgateway.json` | 4 | 2 |
| context | `20260630-211458-context.json` | 3 | 1 |

不要把“自动指标全绿 case 数”包装成产品通过率。它只是 triage 信号。很多失败来自关键词和标题的弱字符串匹配，必须结合人工 rubric 判断。

## 指标含义

每个 case 会记录这些字段：

- `skill_success`：trace 中是否出现期望的 `skill_selected`。
- `tool_success`：所有 required tools 是否都出现在成功的 `tool_called` 中。
- `trace_event_success`：期望的 trace 事件是否出现。
- `state_steps_success`：期望的 state checkpoint 是否出现。
- `forbidden_tool_success`：禁止工具是否没有被调用。
- `keyword_success`：最终输出是否包含弱基线关键词。
- `output_sections_success`：最终输出是否包含期望的章节标签。
- `verification_success`：VerificationGate 是否给出通过的运行记录。

本次基线里最强的信号是 `skill_success`、`state_steps_success`、`forbidden_tool_success` 以及真实 trace/state artifact。最弱的信号是 `keyword_success` 和 `output_sections_success`，因为回答语义上可能合格，但标题或措辞不同。

## 主要失败类型

### 工具 / 协议失败

代表例子：

- `workspace-project-map-001`：`git_inspector` 调用缺少必需的 `operation` 参数，触发 `tool_validation_failed`。
- `runtime-tool-workspace-code-search-001`：`code_search` 报 `[WinError 2]`，随后 Agent 降级使用 `file_reader`。
- `toolgateway-workspace-verification-001`：Agent 没有调用 `workspace_files` 或 `verification_runner`，直接回答了。

这些是真实工程问题，指向几个改进方向：工具 schema 指导要更清楚、required tool enforcement 要更强、工具失败后的降级策略要更明确。

### 工具预算失败

代表例子：

- `workspace-architecture-chain-001`：Agent 反复读文件，最终触发 `Maximum tool calls exceeded: 12`。

这是规划问题。Agent 做架构审查时应该先用 `workspace_files` 和定向 `code_search` 收敛范围，再读关键文件，而不是无差别逐个读取。

### 输出结构弱匹配

很多 `output_sections_success=False` 是因为标题精确字符串不匹配。例如 case 期望 `已读取文件`，但回答用了语义相近的 `工作区事实探测结果`。

这类失败应当作为人工复核提示，而不是自动质量失败。后续要么让 Skill 更严格地统一标题，要么把这部分从精确字符串检查改成人工 rubric。

### 本地测试环境失败

用户 PowerShell 日志里还出现过本地 pytest 失败：

```text
PermissionError: C:\Users\32834\AppData\Local\Temp\pytest-of-admin
```

这是本机 pytest 临时目录权限问题，不是 eval runner 或模型失败。后续检查本地测试健康度时建议使用 workspace-local 临时目录：

```powershell
python -m pytest --basetemp .\.pytest-tmp -q
```

如果 active workspace 自己依赖 `.venv`，验证它的测试命令时应使用该 workspace 的解释器。

## 人工 Rubric

真实模型 smoke case 和复杂输出必须人工复核。当前通用本地工作区审查链路重点看：

| 维度 | 观察点 |
| --- | --- |
| 证据 | 是否引用真实文件、目录、配置、测试或缺失文件。 |
| 事实纪律 | 是否区分已确认事实、推断和未知事项。 |
| 工具纪律 | 是否调用必要本地工具，并避免禁止工具。 |
| 链路推理 | 是否从入口追到核心模块、IO、外部命令或 UI/output 层。 |
| 风险质量 | 发现的问题是否具体、能对应证据，而不是泛泛建议。 |
| 验证诚实性 | 是否真的运行了有效命令，或明确说明为什么不能运行。 |
| 输出可用性 | 开发者是否能根据结论继续测试、修复或验证。 |

## 复跑方式

从 `E:\code\yc-agents` 运行，并确保当前 PowerShell session 已把 `.env` 里的密钥加载到环境变量：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m yc_agents.eval.runner --cases eval/cases/code_review_cases.jsonl --output "outputs/eval/$stamp-code-review.json"
python -m yc_agents.eval.runner --cases eval/cases/eval_writer_cases.jsonl --output "outputs/eval/$stamp-eval-writer.json"
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output "outputs/eval/$stamp-runtime.json"
python -m yc_agents.eval.runner --cases eval/cases/toolgateway_cases.jsonl --output "outputs/eval/$stamp-toolgateway.json"
python -m yc_agents.eval.runner --cases eval/cases/context_cases.jsonl --output "outputs/eval/$stamp-context.json"
```

在声称本地测试健康之前，先跑：

```powershell
python -m pytest --basetemp .\.pytest-tmp -q
```

如果要验证依赖项目内虚拟环境的 workspace，用 `.venv\Scripts\python.exe` 代替全局 `python`。

## 面试讲法

这不是简单的 prompt 测试，而是 Agent 质量工程：

- deterministic/demo eval 用来检查 runner 机械闭环，不受模型发挥影响。
- real smoke eval 调用真实 runtime 和真实模型。
- trace/state/final_output 让工具调用和失败原因可检查。
- 人工 rubric 防止弱关键词检查变成虚假的质量结论。

这次基线的价值在于它同时展示了成功和失败：Harness 能跑通真实 eval；结果也明确暴露出工具协议、工具预算、verification 行为和 eval 指标脆弱性等下一步工程问题。
