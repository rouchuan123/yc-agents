# YCore 演示脚本

## 演示目标

展示 YCore 作为面向 code agent 的本地 Agent Harness，如何把中文用户请求拆成 Skill 选择、本地代码证据、工具调用、trace/state 和结果复核，而不是只生成一段口头回复。

## 演示前准备

- 执行 `pip install -r requirements.txt` 安装依赖。
- 执行 `python -m pytest -q` 确认测试通过。
- 准备一个普通代码仓库作为 workspace。

## 可复现离线 Eval Demo

不依赖真实模型凭证时，可以先运行确定性 demo：

```powershell
python scripts/demo_eval_run.py
```

输出文件：

- `outputs/eval/demo-results.json`

这个 demo 使用固定 runtime 模拟 Skill 选择和工具调用，展示 eval runner 如何记录最终输出、trace 指标和 case 结果。真实模型 demo 仍使用 `python main.py`。

## 场景一：code-review 项目体检

用户输入：

```text
请用 code-review 审查这个项目，重点总结架构风险和测试缺口。
```

演示重点：

1. CLI 接收中文请求。
2. `SkillRuntimeAgent` 根据技能摘要选择 `code-review`。
3. `PromptBuilder` 注入 workspace、记忆、项目指令和选中 Skill。
4. 模型按 allowed tools 发起 `workspace_files`、`file_reader`、`code_search` 或 `verification_runner` 调用。
5. `ToolGateway` 校验工具权限和参数。
6. runtime 写入 `.ycore/runs/<session_id>/<run_id>/trace.json`、`state.json` 和 `final_output.md`。

## 场景二：eval-writer 设计 code-agent eval

用户输入：

```text
请用 eval-writer 为这个 code agent 设计 deterministic eval、真实模型 smoke eval 和人工 rubric。
```

演示重点：

1. Skill 把评估需求拆成目标、维度、case、指标、人工 rubric 和执行流程。
2. 解释 eval 不一定需要大模型参与：日常回归用 deterministic eval，手动演示再跑真实模型 smoke eval。
3. 输出保持中文，方便直接阅读和二次修改。
4. 如果用户要求保存，使用 `markdown_writer` 生成 Markdown 文件。

## 可以展示的文件

- `.ycore/runs/<session_id>/<run_id>/input.md`
- `.ycore/runs/<session_id>/<run_id>/context.json`
- `.ycore/runs/<session_id>/<run_id>/trace.json`
- `.ycore/runs/<session_id>/<run_id>/state.json`
- `.ycore/runs/<session_id>/<run_id>/final_output.md`

## 面试演示顺序

1. 先讲项目定位：面向 code agent 的本地 Agent Harness。
2. 跑离线 deterministic demo，展示 eval 结果。
3. 打开 trace/state 输出，解释 Skill 选择和工具调用。
4. 展示 ToolGateway、verification、memory/context 和可选 RAG 的设计点。
5. 最后说明 MCP 边界和后续扩展。

## 五分钟讲解稿

YCore 是一个面向中文用户、面向 code agent 的本地 Agent Harness。它不把具体审查流程写进全局 prompt，而是把通用运行边界做扎实：Skill 选择、工作区上下文、项目指令、工具权限、trace、state、eval 和 verification。

当前主线是 `code-review`：让 agent 基于本地代码证据做项目体检和变更审查。`eval-writer` 负责把这个能力拆成 deterministic eval、真实模型 smoke eval 和人工 rubric，说明哪些能自动回归，哪些需要人工判断质量。

## 常见追问

- Skill 如何声明 allowed tools？
- 项目根 `YCORE.md` 和本地 `.ycore/YCORE.md` 谁优先？
- 工具调用失败时 runtime 如何记录和恢复？
- eval 为什么可以不依赖大模型？
- trace 和 state 如何复核一次运行？
