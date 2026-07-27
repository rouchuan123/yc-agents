# YCore Eval 与验证说明

## 定位

YCore Eval 用来检查通用 Agent Harness 是否真的完成了任务，而不是只判断最终回答是否流畅。具体评测目标由 Skill 决定，Harness 负责提供统一的用例结构、运行证据和判定机制。

当前重点业务落地点是 `docx-template-authoring`，同时保留 `code-review` 用例验证同一套 Harness 对其他领域的扩展能力。

## 当前用例

| 用例文件 | 关注范围 |
| --- | --- |
| `eval/cases/docx_template_authoring_cases.jsonl` | Word 模板、需求、来源、生成、修订、QA 和发布门 |
| `eval/cases/code_review_cases.jsonl` | 工作区事实、代码证据、风险与测试缺口 |
| `eval/cases/runtime_cases.jsonl` | Skill 选择、普通对话边界和工具使用 |
| `eval/cases/toolgateway_cases.jsonl` | 工具参数、权限、失败标签和条件化工具 |
| `eval/cases/context_cases.jsonl` | Workspace、Memory 和上下文事实 |

## 判定信号

YCore 不只检查关键词，还检查：

- `skill_success`：是否选择期望 Skill。
- `tool_success`：是否调用必要工具。
- `forbidden_tool_success`：是否避免禁止工具。
- `trace_event_success`：Trace 中是否出现要求的事件。
- `state_steps_success`：State checkpoint 是否完整。
- `output_sections_success`：最终输出是否包含必要交付信息。
- `verification_success`：Verification 是否给出真实通过结果。

真实模型 Smoke Eval 仍然需要人工复核。关键词和标题匹配只能作为弱信号，不能替代对事实、来源、工具结果和交付物的检查。

## DOCX 交付验证

文档工作流在通用 Eval 之外还有专门质量门：

1. 模板与 DOCX 结构检查。
2. 必需章节、表格和来源检查。
3. Word 渲染为 PDF。
4. PDF 逐页转换为 PNG。
5. MiMo 逐页视觉 QA。
6. blocking finding 清零。
7. 发布状态、版本和输出路径检查。

缺失模板字体属于非阻断 warning。Word 渲染、PyMuPDF 或视觉模型最终失败属于环境 blocking；只有用户明确同意后，才能通过 `waive_environment=true` 降级发布。

## 运行方式

运行完整单元测试：

```powershell
python -m pytest --basetemp .\.pytest-tmp -q
```

运行离线 Eval Demo：

```powershell
python scripts/demo_eval_run.py
```

运行单个用例集：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python -m yc_agents.eval.runner --cases eval/cases/docx_template_authoring_cases.jsonl --output "outputs/eval/$stamp-docx-template-authoring.json"
python -m yc_agents.eval.runner --cases eval/cases/code_review_cases.jsonl --output "outputs/eval/$stamp-code-review.json"
python -m yc_agents.eval.runner --cases eval/cases/runtime_cases.jsonl --output "outputs/eval/$stamp-runtime.json"
python -m yc_agents.eval.runner --cases eval/cases/toolgateway_cases.jsonl --output "outputs/eval/$stamp-toolgateway.json"
python -m yc_agents.eval.runner --cases eval/cases/context_cases.jsonl --output "outputs/eval/$stamp-context.json"
```

## 证据位置

- Eval 输出：`outputs/eval/`
- 运行 Trace 与 State：`<workspace>/.ycore/runs/`
- 文档版本：`<workspace>/.ycore/document-jobs/<job_id>/revisions/`
- 文档 QA：`<workspace>/.ycore/document-jobs/<job_id>/qa/`

评测报告不得记录 API Key、完整模型请求正文或服务端敏感响应。
